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
    # Comments are invisible to the reader but their text leaks into the body
    # (marketing emails ship long build notes and MSO conditionals inside them).
    html_text = re.sub(r"<!--.*?-->", " ", html_text, flags=re.IGNORECASE | re.DOTALL)
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


# A raw MIME message starts with a header block. The pattern is anchored so a
# header-looking line *inside* an HTML document (a table cell reading
# "Date: 25-11-2026" is common in bank alerts) is never mistaken for one.
_RAW_MIME_HEADER_RE = re.compile(
    r"(?im)\A[ \t>]*(from|to|subject|date|message-id|content-type|mime-version):"
)

# Innermost tables only: the negative lookahead rejects any chunk containing a
# nested <table>, so layout wrappers are skipped instead of swallowing the
# real data table that lives inside them.
_INNERMOST_TABLE_RE = re.compile(r"(?is)<table\b[^>]*>(?:(?!</?table\b).)*?</table>")
_ROW_RE = re.compile(r"(?is)<tr\b.*?</tr>")
_CELL_RE = re.compile(r"(?is)<t[dh]\b[^>]*>(.*?)</t[dh]>")
_STRIP_STYLE_RE = re.compile(r"(?is)<(script|style)\b.*?</\1>")
_STRIP_COMMENT_RE = re.compile(r"(?s)<!--.*?-->")
_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")

# Header cells longer than this (or ending in a full stop) mean the first row is
# prose, not a column header -- typical of bullet-list layout tables.
_MAX_HEADER_CELL_LEN = 40


def _cell_text(fragment: str) -> str:
    """Visible text of one table cell, whitespace-collapsed."""
    fragment = _STRIP_COMMENT_RE.sub(" ", fragment)
    fragment = _STRIP_STYLE_RE.sub(" ", fragment)
    fragment = unescape(_TAG_RE.sub(" ", fragment))
    return _SPACE_RE.sub(" ", fragment).strip()


def _looks_like_header(cells: list[str]) -> bool:
    if len(cells) < 2 or not all(cells):
        return False
    for cell in cells:
        if len(cell) > _MAX_HEADER_CELL_LEN or cell.endswith("."):
            return False
    # A header row must contain at least one label that is not purely numeric.
    return any(re.search(r"[A-Za-z]", cell) for cell in cells)


def tables_to_keyed_rows(html_text: str) -> str:
    """Render HTML tables as one `key=value | key=value` line per data row.

    The flattened body text loses cell boundaries, which makes header-based
    extraction guesswork. Each data row of a table whose first row looks like a
    header is emitted as its own line, preserving the header cell text as the
    key, for example::

        table: Date=25-11-2026 | Particulars=UPIOUT/221312989137/x@y | Withdrawals=100

    Rows keep source order, so a regex can either anchor on a key
    (``Withdrawals=(?P<amount>[\\d.,]+)``) or walk the row. Tables whose first
    row is prose (bullet lists rendered in a table) are skipped.
    """
    if not html_text or "<table" not in html_text.lower():
        return ""

    lines: list[str] = []
    seen: set[str] = set()
    for table in _INNERMOST_TABLE_RE.findall(html_text):
        grid = [[_cell_text(cell) for cell in _CELL_RE.findall(row)] for row in _ROW_RE.findall(table)]
        grid = [row for row in grid if any(row)]
        if len(grid) < 2 or not _looks_like_header(grid[0]):
            continue

        header = grid[0]
        for row in grid[1:]:
            if len(row) != len(header) or not any(row):
                continue
            line = "table: " + " | ".join(f"{key}={value}" for key, value in zip(header, row))
            if line not in seen:
                seen.add(line)
                lines.append(line)

    return "\n".join(lines)


def coerce_text_content(raw_text: str) -> str:
    """Normalise raw content: HTML document, full MIME message, or plain text."""
    if not raw_text:
        return ""

    head = raw_text.lstrip()[:512].lower()
    if "<!doctype" in head or "<html" in head or "<body" in head:
        return strip_html(raw_text)

    if _RAW_MIME_HEADER_RE.match(raw_text.lstrip()):
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

    When the HTML part contains a table with a header row, each data row is
    appended as a `key=value | key=value` line (see `tables_to_keyed_rows`), so
    rules can extract by column name instead of column position. The flattened
    text is never altered, so existing patterns keep working.

    Returns an empty string when the message has neither part.
    """
    body_parts: list[str] = []
    text_part = getattr(msg, "text", None)
    html_part = getattr(msg, "html", None)
    if text_part:
        body_parts.append(coerce_text_content(str(text_part)))
    if html_part:
        body_parts.append(coerce_text_content(str(html_part)))
    body = "\n".join(part for part in body_parts if part)

    table_block = tables_to_keyed_rows(str(html_part)) if html_part else ""
    if table_block:
        body = f"{body}\n{table_block}" if body else table_block
    return body


def body_parts_from_message(msg) -> list[str]:
    """Names of the parts that contribute to `body_text_from_message()`."""
    parts: list[str] = []
    if getattr(msg, "text", None):
        parts.append("text")
    if getattr(msg, "html", None):
        parts.append("html")
    return parts
