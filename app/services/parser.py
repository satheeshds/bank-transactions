from __future__ import annotations

from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
import logging
import os
from pathlib import Path
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


from app.config import build_transaction_patterns
from app.models import TransactionDetails
from app.services.email_body import (
    body_text_from_message,
    coerce_text_content,
    extract_text_from_message,
    strip_html,
)


logger = logging.getLogger(__name__)
log_level = os.getenv("MAIL2FIREFLY_LOG_LEVEL", "INFO").upper()
level = getattr(logging, log_level, logging.INFO)
logging.basicConfig(level=level)
logging.getLogger("app.services.parser").setLevel(level)

# Body extraction lives in app.services.email_body so the parser, the mailbox
# sample endpoint and the transaction log all agree on what the parser sees.
# Thin aliases are kept for backwards compatibility with existing imports.
_strip_html = strip_html
_extract_text_from_message = extract_text_from_message
_coerce_text_content = coerce_text_content


def _body_text_from_source(source: object) -> str:
    """Build the body text the patterns are matched against from any source."""
    if isinstance(source, bytes):
        message = BytesParser(policy=policy.default).parsebytes(source)
        return extract_text_from_message(message)

    if isinstance(source, (str, Path)):
        path = source if isinstance(source, Path) else Path(source)
        try:
            exists = path.exists()
        except OSError:
            exists = False
        if exists:
            raw_email = path.read_bytes()
            message = BytesParser(policy=policy.default).parsebytes(raw_email)
            return extract_text_from_message(message)
        return coerce_text_content(str(source))

    if hasattr(source, "text") or hasattr(source, "html"):
        return body_text_from_message(source)

    raise TypeError("source must be a path, string, bytes, or mailbox-like message")


def _normalize_date(date_text: str) -> str:
    if not date_text:
        return ""
    for fmt in ("%d-%m-%y", "%d-%m-%Y"):
        try:
            return datetime.strptime(date_text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return date_text


def _get_match_group(match: re.Match[str], group_name: str | None, default: object = None) -> object:
    if not group_name:
        return default
    try:
        return match.group(group_name)
    except IndexError:
        return default


def convert_to_timezone(value: datetime | None, tz_name: str = "Asia/Kolkata") -> datetime | None:
    if value is None:
        return None

    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo("UTC"))

    try:
        target_tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        return value.astimezone(timezone.utc)

    return value.astimezone(target_tz)


def extract_transaction(source: str | Path | bytes | object, config: dict | None = None) -> TransactionDetails:
    body_text = _body_text_from_source(source)

    logger.debug("extract_transaction: body_text extracted: %s", body_text)

    patterns = build_transaction_patterns(config)
    if not patterns:
        raise ValueError("No transaction patterns were configured")

    logger.debug("extract_transaction: built %d transaction patterns: %s", len(patterns), [p.get("name") for p in patterns])

    for pattern in patterns:
        match = pattern["compiled"].search(body_text)
        logger.debug("extract_transaction: trying pattern %s, match=%s, groups=%s, groupdict=%s", pattern.get("name"), match, match.groups() if match else None, match.groupdict() if match else None)
        if not match:
            continue

        field_mapping = pattern.get("field_mapping", {})
        defaults = pattern.get("defaults", {}) or {}
        amount_group = field_mapping.get("amount", "amount")
        merchant_group = field_mapping.get("merchant", "merchant")
        description_group = field_mapping.get("description", "description")
        card_group = field_mapping.get("card_last4", "card_last4")
        date_group = field_mapping.get("transaction_date", "date")
        reference_group = field_mapping.get("reference_no", "reference_no")
        channel_group = field_mapping.get("channel", "channel")
        currency_group = field_mapping.get("currency", "currency")
        vpa_group = field_mapping.get("vpa", "vpa")

        amount_value = _get_match_group(match, amount_group)
        if amount_value is None:
            continue
        amount_text = str(amount_value).replace(",", "")
        currency_value = match.groupdict().get(currency_group)
        currency = "INR" if currency_value in {"Rs.", "₹"} else "INR"

        merchant_value = _get_match_group(match, merchant_group, "") or ""
        description_value = _get_match_group(match, description_group, "") or ""
        card_value = _get_match_group(match, card_group)
        date_value = _get_match_group(match, date_group)
        reference_value = _get_match_group(match, reference_group)
        channel_value = _get_match_group(match, channel_group, "") or ""
        vpa_value = _get_match_group(match, vpa_group, "") or ""

        return TransactionDetails(
            amount=float(amount_text),
            currency=currency,
            merchant=str(merchant_value).strip(),
            description=str(description_value).strip() or str(merchant_value).strip(),
            card_last4=str(card_value) if card_value is not None else None,
            transaction_date=_normalize_date(str(date_value) if date_value is not None else ""),
            reference_no=str(reference_value) if reference_value is not None else None,
            channel=str(channel_value).strip(),
            firefly=pattern.get("firefly_mapping", pattern.get("firefly", {})),
            vpa=str(vpa_value).strip() if vpa_value else None,
        )

    raise ValueError("Could not find a supported transaction pattern in the email")


def extract_transaction_details(source: str | Path | bytes | object, config: dict | None = None) -> dict:
    # Return the same TransactionDetails as a dict but include regex groups
    # so mapping resolvers can consume `regex_group` mappings.
    tx = extract_transaction(source, config=config)
    base = tx.as_dict()

    # attempt to find the matching pattern again to capture groups
    try:
        body_text = _body_text_from_source(source)
    except TypeError:
        body_text = None

    patterns = build_transaction_patterns(config)
    if body_text is not None and patterns:
        for pattern in patterns:
            m = pattern["compiled"].search(body_text)
            if not m:
                continue
            # attach positional groups and named groupdict
            base["groups"] = list(m.groups())
            base["groupdict"] = m.groupdict()
            break

    return base
