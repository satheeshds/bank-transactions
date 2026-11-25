"""Shared email body extraction helpers.

This module is the single source of truth for turning an email into the plain
text that the transaction parser matches against. It is intentionally free of
FastAPI/imap_tools dependencies so it can be reused by the parser service, the
mailbox API endpoints and the sync worker.

Invariant: `body_text_from_message()` returns exactly the text that
`app.services.parser.extract_transaction()` matches its regexes against. The
rule-creation wizard's "Sample Text" box shows the same string, so what the
operator writes a regex against is what the parser will see at sync time.
"""
from __future__ import annotations

from email import policy
from email.parser import BytesParser
from html import unescape
import re


def strip_html(html_text: str) -> str:
    """Convert an HTML fragment to whitespace-collapsed plain text."""
    if not html_text:
        return ""
    html_text = unescape(html_text)
    html_text = re.sub(r"<style.*?</style>", " ", html_text, flags=re.IGNORECASE | re.DOTALL)
    html_text = re.sub(r"<script.*?</script>", " ", html_text, flags=re.IGNORECASE | re.DOTALL)
    html_text = re.sub(r"<[^>]+>", " ", html_text)
    html_text = re.sub(r"\s+", " ", html_text)
    return html_text.strip()


def extract_text_from_message(message) -> str:
    """Walk a parsed MIME message and join every text part (HTML stripped)."""
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
            text = strip_html(text)

        parts.append(text)

    return "\n".join(parts)


def coerce_text_content(raw_text: str) -> str:
    """Normalise raw content: full MIME message, HTML document, or plain text."""
    if not raw_text:
        return ""

    if re.search(r"(?im)^(from|to|subject|date|message-id|content-type):", raw_text):
        message = BytesParser(policy=policy.default).parsebytes(raw_text.encode("utf-8", errors="ignore"))
        return extract_text_from_message(message)

    if "<html" in raw_text.lower() or "<body" in raw_text.lower():
        return strip_html(raw_text)

    return raw_text


def body_text_from_message(msg) -> str:
    """Build the parser body text from an imap_tools-like message object.

    `msg.text` (text/plain part) and `msg.html` (text/html part) are both
    coerced and joined with a newline, mirroring
    `app.services.parser.extract_transaction()`. Both parts matter: bank alerts
    often carry the real transaction content only in the HTML part while the
    plain part is a "please use an HTML enabled email client" notice.

    Returns an empty string when the message has neither part.
    """
    body_parts: list[str] = []
    text_part = getattr(msg, "text", None)
    html_part = getattr(msg, "html", None)
    if text_part:
        body_parts.append(coerce_text_content(str(text_part)))
    if html_part:
        body_parts.append(coerce_text_content(str(html_part)))
    return "\n".join(part for part in body_parts if part)


def body_parts_from_message(msg) -> list[str]:
    """Names of the parts that contribute to `body_text_from_message()`."""
    parts: list[str] = []
    if getattr(msg, "text", None):
        parts.append("text")
    if getattr(msg, "html", None):
        parts.append("html")
    return parts
