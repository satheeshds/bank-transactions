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


if __name__ == "__main__":
    unittest.main()
