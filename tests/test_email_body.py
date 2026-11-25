"""Tests for the shared email body extraction helpers."""
import unittest
from email import policy
from email.parser import BytesParser

from app.services.email_body import (
    body_parts_from_message,
    body_text_from_message,
    coerce_text_content,
    extract_text_from_message,
    strip_html,
    tables_to_keyed_rows,
)

BOILERPLATE_NOTICE = (
    "For easy reading and better experience, this email is sent in HTML format. "
    "Please use HTML enabled email client to view this email."
)

TRANSACTION_HTML = (
    "<html><head><style>.x{color:red}</style></head><body>"
    "<p>Dear Customer,</p>"
    "<p>Rs. 78.00 spent on your SBI Credit Card ending with 4465 at SUBEESHW "
    "on 26-06-26 via UPI (Ref No. 309259409044).</p>"
    "</body></html>"
)

RAW_MULTIPART_EMAIL = """\
From: alerts@sbi.co.in
To: customer@example.com
Subject: Transaction Alert from SBI Card
MIME-Version: 1.0
Content-Type: multipart/alternative; boundary="BOUNDARY"

--BOUNDARY
Content-Type: text/plain; charset="utf-8"

{notice}
--BOUNDARY
Content-Type: text/html; charset="utf-8"

{html}
--BOUNDARY--
""".format(notice=BOILERPLATE_NOTICE, html=TRANSACTION_HTML)


# Modelled on the Federal Bank debit alert: an 11-column transaction table, a
# marketing comment that itself contains a '>' character, a cell whose text
# starts with "Date:" (which used to fool the raw-MIME detector) and a bullet
# list rendered as a layout table whose first row is prose.
FEDERAL_BANK_HTML = """<html><head><title>Transaction Alert</title>
<style>td { border: 1px solid #ddd; }</style></head><body>
<!-- Fixed-width canvas: width=<canvas px>, NO initial-scale, so mobile clients
     scale the whole 600px email to fit instead of squishing the 11 columns. -->
<div style="display:none">Federal Bank Transaction Alert</div>
<table role="presentation"><tr><td>
<table align="right"><tr><td>Date: <span id="mxb-bm-csv-header_date">25-11-2026</span></td></tr></table>
</td></tr></table>
<p>The below transaction has been done in your account
<span id="mxb-bm-csv-account_no">2039xxxxxx0838</span>.</p>
<table>
<tr>
  <td>Date</td><td>Value Date</td><td>Time</td><td>Particulars</td><td>Tran Type</td>
  <td>Tran ID</td><td>Cheque Details</td><td>Withdrawals</td><td>Deposits</td>
  <td>Effective Available Balance</td><td>Dr/Cr</td>
</tr>
<tr>
  <td><span id="mxb-bm-csv-date">25-11-2026</span></td>
  <td>25-11-2026</td><td>09:28:15</td>
  <td>UPIOUT/221312989137/customer@ptyes/N/0000</td>
  <td>Debit</td><td>S16449515</td><td></td>
  <td>100</td><td></td><td>141915.26</td><td>Cr</td>
</tr>
</table>
<table>
<tr>
  <td>&bull;</td>
  <td>If this transaction has not been done by you, call 1800 425 1199 immediately.</td>
</tr>
<tr>
  <td>&bull;</td>
  <td>For non-digital transactions, call 1800 425 1199</td>
</tr>
</table>
</body></html>"""

FEDERAL_BANK_KEYED_ROW = (
    "table: Date=25-11-2026 | Value Date=25-11-2026 | Time=09:28:15 | "
    "Particulars=UPIOUT/221312989137/customer@ptyes/N/0000 | Tran Type=Debit | "
    "Tran ID=S16449515 | Cheque Details= | Withdrawals=100 | Deposits= | "
    "Effective Available Balance=141915.26 | Dr/Cr=Cr"
)


class FakeMailMessage:
    """Stand-in for imap_tools.MailMessage exposing only .text / .html."""

    def __init__(self, text=None, html=None):
        self.text = text
        self.html = html


class StripHtmlTests(unittest.TestCase):
    def test_removes_markup_and_collapses_whitespace(self):
        self.assertEqual(strip_html("<p>Rs. 78.00 spent</p>"), "Rs. 78.00 spent")

    def test_removes_style_and_script_blocks(self):
        self.assertEqual(strip_html("<style>.a{color:red}</style><b>hello</b>"), "hello")

    def test_empty_input(self):
        self.assertEqual(strip_html(""), "")


class ExtractTextFromMessageTests(unittest.TestCase):
    def test_collects_text_and_stripped_html_parts(self):
        message = BytesParser(policy=policy.default).parsebytes(
            RAW_MULTIPART_EMAIL.encode("utf-8")
        )
        body = extract_text_from_message(message)
        self.assertIn(BOILERPLATE_NOTICE, body)
        self.assertIn("Rs. 78.00 spent on your SBI Credit Card ending with 4465", body)
        self.assertNotIn("<p>", body)


class CoerceTextContentTests(unittest.TestCase):
    def test_passes_through_plain_text(self):
        self.assertEqual(coerce_text_content("Rs. 10 spent"), "Rs. 10 spent")

    def test_strips_html_documents(self):
        self.assertEqual(coerce_text_content(TRANSACTION_HTML).startswith("Dear Customer"), True)

    def test_parses_raw_mime(self):
        body = coerce_text_content(RAW_MULTIPART_EMAIL)
        self.assertIn(BOILERPLATE_NOTICE, body)
        self.assertIn("Rs. 78.00", body)

    def test_empty_input(self):
        self.assertEqual(coerce_text_content(""), "")

    def test_html_with_a_date_label_line_is_not_treated_as_mime(self):
        """Regression: a cell reading 'Date: 25-11-2026' used to be parsed as a
        MIME header, so the whole HTML document (tags and CSS included) leaked
        into the body text."""
        body = coerce_text_content(FEDERAL_BANK_HTML)
        self.assertNotIn("<td", body)
        self.assertNotIn("<style", body)
        self.assertIn("2039xxxxxx0838", body)

    def test_html_comments_are_removed(self):
        self.assertNotIn("initial-scale", coerce_text_content(FEDERAL_BANK_HTML))


class TableExtractionTests(unittest.TestCase):
    def test_renders_one_keyed_line_per_data_row(self):
        block = tables_to_keyed_rows(FEDERAL_BANK_HTML)
        self.assertEqual(block, FEDERAL_BANK_KEYED_ROW)

    def test_layout_table_with_prose_first_row_is_skipped(self):
        block = tables_to_keyed_rows(FEDERAL_BANK_HTML)
        self.assertNotIn("1800 425 1199", block)
        self.assertEqual(block.count("table: "), 1)

    def test_tables_without_a_header_row_are_ignored(self):
        html = "<table><tr><td>Rs. 5 spent</td><td>today</td></tr></table>"
        self.assertEqual(tables_to_keyed_rows(html), "")

    def test_no_tables(self):
        self.assertEqual(tables_to_keyed_rows("<p>plain</p>"), "")
        self.assertEqual(tables_to_keyed_rows(""), "")

    def test_nested_tables_only_emit_the_data_table(self):
        html = (
            "<table><tr><td><table>"
            "<tr><td>Amount</td><td>Label</td></tr>"
            "<tr><td>100</td><td>Debit</td></tr>"
            "</table></td></tr></table>"
        )
        self.assertEqual(tables_to_keyed_rows(html), "table: Amount=100 | Label=Debit")

    def test_body_appends_keyed_rows_after_the_flat_text(self):
        body = body_text_from_message(FakeMailMessage(text=BOILERPLATE_NOTICE, html=FEDERAL_BANK_HTML))
        self.assertTrue(body.startswith(BOILERPLATE_NOTICE))
        self.assertIn(FEDERAL_BANK_KEYED_ROW, body)
        self.assertTrue(body.rstrip().endswith("Dr/Cr=Cr"))
        # flattened text is still present, so existing patterns keep matching
        self.assertIn("Date Value Date Time Particulars", body)


class BodyTextFromMessageTests(unittest.TestCase):
    def test_includes_html_content_when_plain_part_is_only_boilerplate(self):
        """Regression: the wizard used to show only the boilerplate notice."""
        msg = FakeMailMessage(text=BOILERPLATE_NOTICE, html=TRANSACTION_HTML)
        body = body_text_from_message(msg)
        self.assertIn(BOILERPLATE_NOTICE, body)
        self.assertIn("Rs. 78.00 spent on your SBI Credit Card ending with 4465", body)
        self.assertIn("309259409044", body)

    def test_matches_parser_body_for_equivalent_mime_message(self):
        """Same content as a parsed MIME message must produce the same body text."""
        from app.services.parser import _body_text_from_source

        msg = FakeMailMessage(text=BOILERPLATE_NOTICE, html=TRANSACTION_HTML)
        parsed = BytesParser(policy=policy.default).parsebytes(RAW_MULTIPART_EMAIL.encode("utf-8"))
        self.assertEqual(body_text_from_message(msg), extract_text_from_message(parsed))
        self.assertEqual(_body_text_from_source(msg), body_text_from_message(msg))
        self.assertEqual(_body_text_from_source(RAW_MULTIPART_EMAIL.encode("utf-8")), body_text_from_message(msg))

    def test_html_only_message(self):
        body = body_text_from_message(FakeMailMessage(html=TRANSACTION_HTML))
        self.assertIn("SUBEESHW", body)
        self.assertNotIn("<p>", body)

    def test_text_only_message_is_returned_unchanged(self):
        self.assertEqual(body_text_from_message(FakeMailMessage(text="Rs. 5 spent")), "Rs. 5 spent")

    def test_empty_message(self):
        self.assertEqual(body_text_from_message(FakeMailMessage()), "")

    def test_parts_reported(self):
        self.assertEqual(body_parts_from_message(FakeMailMessage(text="a", html="<p>b</p>")), ["text", "html"])
        self.assertEqual(body_parts_from_message(FakeMailMessage(text="a")), ["text"])
        self.assertEqual(body_parts_from_message(FakeMailMessage()), [])


class ParserStillMatchesTests(unittest.TestCase):
    FEDERAL_BANK_REGEX = (
        r"table: Date=(?P<date>\d{2}-\d{2}-\d{4})\s*\|.*?"
        r"Particulars=(?P<merchant>[^|]+).*?"
        r"Tran Type=(?P<channel>[A-Za-z]+)\s*\|.*?"
        r"Tran ID=(?P<reference_no>[A-Za-z0-9]+).*?"
        r"Withdrawals=(?P<amount>[\d.,]+)"
    )

    def test_extract_transaction_details_reads_html_only_body(self):
        from app.services.parser import extract_transaction_details

        msg = FakeMailMessage(text=BOILERPLATE_NOTICE, html=TRANSACTION_HTML)
        details = extract_transaction_details(msg)
        self.assertEqual(details["amount"], 78.0)
        self.assertEqual(details["currency"], "INR")
        self.assertEqual(details["merchant"], "SUBEESHW")
        self.assertEqual(details["card_last4"], "4465")
        self.assertEqual(details["transaction_date"], "2026-06-26")
        self.assertEqual(details["reference_no"], "309259409044")
        self.assertEqual(details["groupdict"]["amount"], "78.00")

    def test_extracts_from_keyed_table_row(self):
        """A table-only alert can be matched by column name instead of position."""
        from app.services.parser import extract_transaction_details

        msg = FakeMailMessage(text=BOILERPLATE_NOTICE, html=FEDERAL_BANK_HTML)
        details = extract_transaction_details(
            msg,
            config={"transaction_patterns": [{"name": "federal_bank", "regex": self.FEDERAL_BANK_REGEX}]},
        )
        self.assertEqual(details["amount"], 100.0)
        self.assertEqual(details["merchant"], "UPIOUT/221312989137/customer@ptyes/N/0000")
        self.assertEqual(details["transaction_date"], "2026-11-25")
        self.assertEqual(details["reference_no"], "S16449515")
        self.assertEqual(details["channel"], "Debit")


if __name__ == "__main__":
    unittest.main()
