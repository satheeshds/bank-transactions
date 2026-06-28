from __future__ import annotations

from config import build_firefly_config, build_statement_definitions, load_config
from firefly_client import FireflyClientError, build_firefly_client
from imap_client import build_query, get_mailbox_client
from parser import convert_to_timezone, extract_transaction_details


def _is_message_processed(message: object, tag: str | None = None) -> bool:
    if not tag:
        return False

    flags = getattr(message, "flags", None) or []
    if not isinstance(flags, (list, tuple, set)):
        return False

    tag_lower = str(tag).strip().lower()
    return any(str(flag).strip().lower() == tag_lower for flag in flags)


def _mark_message_processed(mailbox: object, message: object, tag: str | None = None) -> None:
    if not tag:
        return

    message_uid = getattr(message, "uid", None)
    if message_uid in (None, ""):
        return

    mailbox.flag(message_uid, tag, True)


def _build_firefly_transaction(
    details: dict,
    message_date: object | None = None,
    statement_config: dict | None = None,
) -> dict:
    amount = float(details.get("amount", 0))
    transaction_date = message_date
    statement_firefly = (statement_config or {}).get("firefly") or {}
    source_id = str(statement_firefly.get("source_id", "") or "")
    merchant_name = str(details.get("merchant") or "Bank transaction")
    destination_name = merchant_name
    if transaction_date is None:
        transaction_date = details.get("transaction_date") or details.get("date") or ""
    if hasattr(transaction_date, "strftime"):
        transaction_date = transaction_date.strftime("%Y-%m-%d %H:%M:%S%z")
    return {
        "error_if_duplicate_hash": False,
        "apply_rules": False,
        "fire_webhooks": True,
        "transactions": [
            {
                "type": "withdrawal",
                "date": transaction_date if transaction_date else "",
                "amount": str(abs(amount)),
                "description": merchant_name,
                "order": 0,
                "currency_code": details.get("currency") or "INR",
                "source_id": source_id,
                "destination_name": destination_name,
                "notes": (
                    f"channel={details.get('channel', '')}; ref={details.get('reference_no', '')}".strip("; ")
                ),
                "reconciled": False,
                "tags": None,
                "internal_reference": "",
                "external_id": "",
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


def main():
    config = load_config()
    fetch_config = config.get("fetch", {})
    statements = build_statement_definitions(config)

    firefly_client = None
    firefly_config = build_firefly_config(config)
    if firefly_config.get("base_url") and firefly_config.get("token"):
        try:
            firefly_client = build_firefly_client(firefly_config)
        except ValueError:
            firefly_client = None

    print("Hello from bank-transactions!")
    for statement in statements:
        mailbox_config = statement.get("mailbox")
        if mailbox_config is None:
            raise KeyError("mailbox configuration is required for each statement")

        with get_mailbox_client(mailbox_config) as mailbox:
            for query_filter in statement.get("query", []):
                query = build_query(query_filter, processed_tag=statement.get("processed_tag"))
                for msg in mailbox.fetch(
                    query,
                    reverse=fetch_config.get("reverse", True),
                    limit=fetch_config.get("limit", 15),
                ):
                    processed_tag = statement.get("processed_tag")
                    if _is_message_processed(msg, processed_tag):
                        print("Skipping already processed message:", msg.subject)
                        continue

                    try:
                        details = extract_transaction_details(
                            msg,
                            config={**config, "transaction_patterns": statement.get("transaction_patterns")},
                        )
                    except ValueError:
                        details = None

                    if details and firefly_client is not None:
                        try:
                            payload = _build_firefly_transaction(details, msg.date, statement)
                            firefly_client.create_transaction(payload)
                            print("Posted to Firefly:", payload)
                            _mark_message_processed(mailbox, msg, processed_tag)
                        except FireflyClientError as exc:
                            print("Firefly post failed:", exc)

                    print(convert_to_timezone(msg.date), msg.subject, details)


if __name__ == "__main__":
    main()
