from __future__ import annotations

from app.models import TransactionDetails
from app.services.mapping_resolvers import apply_mappings
from pathlib import Path
import json

# cached firefly fields loaded from shared data file
_FIREFLY_FIELDS: list[dict] | None = None


def _load_firefly_fields() -> list[dict]:
    global _FIREFLY_FIELDS
    if _FIREFLY_FIELDS is not None:
        return _FIREFLY_FIELDS
    try:
        base = Path(__file__).resolve().parents[2]
        p = base / "static"/ "dist" / "firefly_fields.json"
        if p.exists():
            with p.open("r", encoding="utf-8") as fh:
                _FIREFLY_FIELDS = json.load(fh)
        else:
            _FIREFLY_FIELDS = []
    except Exception:
        _FIREFLY_FIELDS = []
    return _FIREFLY_FIELDS
import logging

logger = logging.getLogger(__name__)


def _coerce_details(details: dict | TransactionDetails) -> dict:
    if isinstance(details, TransactionDetails):
        return details.as_dict()
    return details


# firefly mapping resolution inlined into payload builder; helper removed


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


def _build_firefly_payload(details: dict, statement_config: dict | None = None, message: object | None = None) -> dict:
    details = _coerce_details(details)
    logger.debug("build_firefly_payload start - details: %s, statement_config: %s", details, statement_config)
    # apply parsing-rule mappings if present on details
    mappings = details.get("mappings") or details.get("mappings_json") or None
    logger.debug("mappings: %s", mappings)
    if isinstance(mappings, list):
        logger.debug("applying mappings: %s", mappings)
        details = apply_mappings(details, mappings, message)
        logger.debug("details after mappings: %s", details)
    statement_firefly = (statement_config or {}).get("firefly") or {}
    configured_account_id = str(statement_firefly.get("account_id", "") or "")
    merchant_name = str(details.get("merchant") or "Bank transaction")
    # resolve pattern-specific firefly mapping: details.firefly -> details.firefly_mapping -> statement_config.firefly
    pattern_firefly = (details.get("firefly") or {}) if isinstance(details.get("firefly"), dict) else {}
    if not pattern_firefly:
        pattern_firefly = (details.get("firefly_mapping") or {}) if isinstance(details.get("firefly_mapping"), dict) else {}
    if not pattern_firefly:
        pattern_firefly = (statement_config or {}).get("firefly") or {}
    logger.debug("resolved pattern_firefly: %s", pattern_firefly)

    
    
    pattern_source_value = _resolve_mapping_value(pattern_firefly.get("source_value"), details, statement_config)
    pattern_destination_value = _resolve_mapping_value(pattern_firefly.get("destination_value"), details, statement_config)
    logger.debug("pattern_source_value=%s pattern_destination_value=%s", pattern_source_value, pattern_destination_value)
    transaction_type = str(details.get("transaction_type") or details.get("type") or "").strip().lower() or "withdrawal"
    if not isinstance(transaction_type, str) or not transaction_type.strip():
        transaction_type = "withdrawal"
    payload = {} 
    # Add any explicit Firefly fields present in details to the payload (single source list)
    try:
        ff_fields = _load_firefly_fields()
        for f in ff_fields:
            key = f.get("key")
            if not key:
                continue
            # don't overwrite fields already set (pattern fields)
            if key in payload:
                continue
            if key in details and details.get(key) is not None:
                v = details.get(key)
                # stringify datetime-like objects to avoid JSON serialization errors
                try:
                    if not isinstance(v, str) and hasattr(v, "strftime"):
                        v = v.strftime("%Y-%m-%d %H:%M:%S%z")  # type: ignore
                except Exception:
                    pass
                payload[key] = v
    except Exception:
        logger.debug("failed to apply explicit firefly fields from shared list", exc_info=True)
    logger.debug("final firefly payload: %s", payload)
    return payload


def _build_firefly_transaction(
    details: dict | TransactionDetails,
    message_date: object | None = None,
    statement_config: dict | None = None,
    message: object | None = None,
) -> dict:
    details = _coerce_details(details)
    amount = float(details.get("amount", 0))
    transaction_date = message_date
    description_value = str(details.get("description") or details.get("merchant") or "Bank transaction")
    if transaction_date is None:
        transaction_date = details.get("transaction_date") or details.get("date") or ""
    if hasattr(transaction_date, "strftime"):
        transaction_date = transaction_date.strftime("%Y-%m-%d %H:%M:%S%z")  # type: ignore

    payload = _build_firefly_payload(details, statement_config, message)

    return {
        "error_if_duplicate_hash": False,
        "apply_rules": True,
        "fire_webhooks": True,
        "transactions": [
            {
                **payload,
                "notes": (
                    f"channel={details.get('channel', '')}; ref={details.get('reference_no', '')}".strip("; ")
                ),
                
            }
        ],
    }
