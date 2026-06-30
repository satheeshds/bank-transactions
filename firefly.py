from __future__ import annotations

from models import TransactionDetails


def _coerce_details(details: dict | TransactionDetails) -> dict:
    if isinstance(details, TransactionDetails):
        return details.as_dict()
    return details


def _get_firefly_mapping(details: dict, statement_config: dict | None = None) -> dict:
    details = _coerce_details(details)
    statement_firefly = (statement_config or {}).get("firefly") or {}
    details_firefly = (details.get("firefly") or {}) if isinstance(details.get("firefly"), dict) else {}
    if details_firefly:
        return details_firefly

    details_firefly_mapping = (
        details.get("firefly_mapping") or {}
    ) if isinstance(details.get("firefly_mapping"), dict) else {}
    if details_firefly_mapping:
        return details_firefly_mapping

    return statement_firefly


def _resolve_mapping_value(value: object, details: dict | None = None, statement_config: dict | None = None) -> object:
    if not isinstance(value, str):
        return value

    account_id = str((statement_config or {}).get("firefly", {}).get("account_id", "") or "")
    if value.strip() == "{account_id}":
        return account_id

    if details is None:
        return value.replace("{account_id}", account_id)

    resolved = value
    for key, item in details.items():
        if isinstance(item, (str, int, float, bool)):
            resolved = resolved.replace("{" + str(key) + "}", str(item))
    return resolved.replace("{account_id}", account_id)


def _build_firefly_payload(details: dict, statement_config: dict | None = None) -> dict:
    details = _coerce_details(details)
    statement_firefly = (statement_config or {}).get("firefly") or {}
    configured_account_id = str(statement_firefly.get("account_id", "") or "")
    merchant_name = str(details.get("merchant") or "Bank transaction")
    pattern_firefly = _get_firefly_mapping(details, statement_config)

    pattern_source_field = str(
        _resolve_mapping_value(
            pattern_firefly.get("source_field", statement_firefly.get("source_field", "source_id")),
            details,
            statement_config,
        )
        or "source_id"
    )
    pattern_destination_field = str(
        _resolve_mapping_value(
            pattern_firefly.get("destination_field", statement_firefly.get("destination_field", "destination_name")),
            details,
            statement_config,
        )
        or "destination_name"
    )
    pattern_source_value = _resolve_mapping_value(pattern_firefly.get("source_value"), details, statement_config)
    pattern_destination_value = _resolve_mapping_value(pattern_firefly.get("destination_value"), details, statement_config)
    transaction_type = pattern_firefly.get("transaction_type")
    if not isinstance(transaction_type, str) or not transaction_type.strip():
        transaction_type = str(details.get("transaction_type") or "").strip().lower() or "withdrawal"

    return {
        "type": transaction_type.strip(),
        pattern_source_field: merchant_name if pattern_source_value is None else pattern_source_value,
        pattern_destination_field: (
            configured_account_id if pattern_destination_value is None else pattern_destination_value
        ),
    }


def _build_firefly_transaction(
    details: dict | TransactionDetails,
    message_date: object | None = None,
    statement_config: dict | None = None,
) -> dict:
    details = _coerce_details(details)
    amount = float(details.get("amount", 0))
    transaction_date = message_date
    description_value = str(details.get("description") or details.get("merchant") or "Bank transaction")
    if transaction_date is None:
        transaction_date = details.get("transaction_date") or details.get("date") or ""
    if hasattr(transaction_date, "strftime"):
        transaction_date = transaction_date.strftime("%Y-%m-%d %H:%M:%S%z")  # type: ignore

    payload = _build_firefly_payload(details, statement_config)

    return {
        "error_if_duplicate_hash": False,
        "apply_rules": True,
        "fire_webhooks": True,
        "transactions": [
            {
                "date": transaction_date if transaction_date else "",
                "amount": str(abs(amount)),
                "description": description_value,
                "order": 0,
                "currency_code": details.get("currency") or "INR",
                **payload,
                "notes": (
                    f"channel={details.get('channel', '')}; ref={details.get('reference_no', '')}".strip("; ")
                ),
                "reconciled": False,
                "tags": None,
                "internal_reference": "",
                "external_id": details.get("vpa") or "",
                "external_url": "",
                "sepa_cc": "",
                "sepa_ct_op": "",
                "sepa_ct_id": "",
                "sepa_db": "",
                "sepa_country": "",
                "sepa_ep": "",
                "sepa_ci": "",
                "sepa_batch_id": "",
                "interest_date": "",
                "book_date": "",
                "process_date": "",
                "due_date": "",
                "payment_date": "",
                "invoice_date": "",
            }
        ],
    }
