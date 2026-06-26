from __future__ import annotations

from datetime import datetime
from email import policy
from email.parser import BytesParser
from html import unescape
from pathlib import Path
import re
from zoneinfo import ZoneInfo

from config import build_transaction_patterns


def _extract_text_from_message(message) -> str:
    parts: list[str] = []
    for part in message.walk():
        if part.get_content_maintype() == "multipart":
            continue
        if part.get_content_maintype() != "text":
            continue

        payload = part.get_payload(decode=True)
        if payload is None:
            continue

        charset = part.get_content_charset() or "utf-8"
        try:
            text = payload.decode(charset, errors="ignore")
        except LookupError:
            text = payload.decode("utf-8", errors="ignore")

        if part.get_content_type() == "text/html":
            text = _strip_html(text)

        parts.append(text)

    return "\n".join(parts)


def _strip_html(html_text: str) -> str:
    html_text = unescape(html_text)
    html_text = re.sub(r"<style.*?</style>", " ", html_text, flags=re.IGNORECASE | re.DOTALL)
    html_text = re.sub(r"<script.*?</script>", " ", html_text, flags=re.IGNORECASE | re.DOTALL)
    html_text = re.sub(r"<[^>]+>", " ", html_text)
    html_text = re.sub(r"\s+", " ", html_text)
    return html_text.strip()


def _coerce_text_content(raw_text: str) -> str:
    if not raw_text:
        return ""

    if re.search(r"(?im)^(from|to|subject|date|message-id|content-type):", raw_text):
        message = BytesParser(policy=policy.default).parsebytes(raw_text.encode("utf-8", errors="ignore"))
        return _extract_text_from_message(message)

    if "<html" in raw_text.lower() or "<body" in raw_text.lower():
        return _strip_html(raw_text)

    return raw_text


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
    return value.astimezone(ZoneInfo(tz_name))


def extract_transaction_details(source: str | Path | bytes | object, config: dict | None = None) -> dict:
    if isinstance(source, bytes):
        raw_email = source
        message = BytesParser(policy=policy.default).parsebytes(raw_email)
        body_text = _extract_text_from_message(message)
    elif isinstance(source, (str, Path)):
        path = None
        if isinstance(source, Path):
            path = source
        else:
            try:
                path = Path(source)
            except OSError:
                path = None

        if path is not None and path.exists():
            raw_email = path.read_bytes()
            message = BytesParser(policy=policy.default).parsebytes(raw_email)
            body_text = _extract_text_from_message(message)
        else:
            body_text = _coerce_text_content(str(source))
    elif hasattr(source, "text") or hasattr(source, "html"):
        body_parts: list[str] = []
        if getattr(source, "text", None):
            body_parts.append(_coerce_text_content(str(source.text)))
        if getattr(source, "html", None):
            body_parts.append(_coerce_text_content(str(source.html)))
        body_text = "\n".join(part for part in body_parts if part)
    else:
        raise TypeError("source must be a path, string, bytes, or mailbox-like message")

    patterns = build_transaction_patterns(config)
    if not patterns:
        raise ValueError("No transaction patterns were configured")

    for pattern in patterns:
        match = pattern["compiled"].search(body_text)
        if not match:
            continue

        field_mapping = pattern.get("field_mapping", {})
        amount_group = field_mapping.get("amount", "amount")
        merchant_group = field_mapping.get("merchant", "merchant")
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
        card_value = _get_match_group(match, card_group)
        date_value = _get_match_group(match, date_group)
        reference_value = _get_match_group(match, reference_group)
        channel_value = _get_match_group(match, channel_group, "") or ""
        vpa_value = _get_match_group(match, vpa_group, "") or ""

        details = {
            "amount": float(amount_text),
            "currency": currency,
            "merchant": merchant_value.strip(),
            "card_last4": card_value,
            "transaction_date": _normalize_date(str(date_value) if date_value is not None else ""),
            "reference_no": reference_value,
            "channel": channel_value.strip(),
        }
        if vpa_value:
            details["vpa"] = vpa_value.strip()

        return details

    raise ValueError("Could not find a supported transaction pattern in the email")
