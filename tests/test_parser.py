import unittest
from datetime import datetime, timezone
from pathlib import Path

from main import build_statement_definitions, convert_to_timezone, extract_transaction_details


class TransactionParsingTests(unittest.TestCase):
    def test_extracts_sbi_card_transaction_details_from_sample_email(self):
        sample_email_path = (
            Path(__file__).resolve().parents[1]
            / "sample-data"
            / "Transaction Alert from SBI Card.eml"
        )

        details = extract_transaction_details(sample_email_path)

        self.assertEqual(details["amount"], 78.0)
        self.assertEqual(details["currency"], "INR")
        self.assertEqual(details["merchant"], "SUBEESHW")
        self.assertEqual(details["card_last4"], "4465")
        self.assertEqual(details["transaction_date"], "2026-06-26")
        self.assertEqual(details["reference_no"], "309259409044")
        self.assertEqual(details["channel"], "UPI")

    def test_converts_datetime_to_asia_kolkata(self):
        value = datetime(2026, 6, 26, 3, 19, 31, tzinfo=timezone.utc)

        converted = convert_to_timezone(value)

        self.assertEqual(converted.strftime("%Y-%m-%d %H:%M:%S"), "2026-06-26 08:49:31")

    def test_extracts_transaction_details_with_comma_separated_amount(self):
        sample_text = (
            "Rs.4,012.44 spent on your SBI Credit Card ending with 4465 "
            "at LuluTrivandrum on 24-06-26 via UPI (Ref No. 609118054276)"
        )

        details = extract_transaction_details(sample_text)

        self.assertEqual(details["amount"], 4012.44)
        self.assertEqual(details["merchant"], "LuluTrivandrum")
        self.assertEqual(details["reference_no"], "609118054276")

    def test_extracts_transaction_details_from_mailbox_message_object(self):
        class MailboxMessageStub:
            def __init__(self, html_body: str):
                self.text = None
                self.html = html_body

        with open(
            Path(__file__).resolve().parents[1]
            / "sample-data"
            / "Transaction Alert from SBI Card.eml",
            "rb",
        ) as handle:
            raw_email = handle.read()

        html_body = raw_email.decode("utf-8", errors="ignore")
        message = MailboxMessageStub(html_body)

        details = extract_transaction_details(message)

        self.assertEqual(details["amount"], 78.0)
        self.assertEqual(details["merchant"], "SUBEESHW")
        self.assertEqual(details["reference_no"], "309259409044")

    def test_uses_configured_transaction_patterns(self):
        config = {
            "transaction_patterns": [
                {
                    "name": "sbi_card",
                    "regex": (
                        r"(?P<currency>Rs\.|₹)\s*(?P<amount>[\d,]+(?:\.\d+)?)\s*spent on your\s+"
                        r"SBI Credit Card\s+ending with\s+(?P<card_last4>\d{4})\s+"
                        r"at\s+(?P<merchant>.+?)\s+on\s+(?P<date>\d{1,2}-\d{1,2}-\d{2,4})\s+"
                        r"via\s+(?P<channel>.+?)\s*\(Ref No\.\s*(?P<reference_no>\d+)\)"
                    ),
                }
            ]
        }

        details = extract_transaction_details(
            "Rs.4,012.44 spent on your SBI Credit Card ending with 4465 at LuluTrivandrum on 24-06-26 via UPI (Ref No. 609118054276)",
            config=config,
        )

        self.assertEqual(details["amount"], 4012.44)
        self.assertEqual(details["merchant"], "LuluTrivandrum")
        self.assertEqual(details["reference_no"], "609118054276")

    def test_builds_statement_definitions_for_multiple_statements(self):
        config = {
            "mailbox": {
                "host": "mail.example.com",
                "username": "u",
                "password": "p",
                "statements": [
                    {
                        "name": "sbi",
                        "query": [{"name": "alerts", "from_": "alerts@example.com", "subject": "Alert"}],
                        "transaction_patterns": [{"name": "sbi", "regex": "pattern"}],
                    },
                    {
                        "name": "other",
                        "query": [{"name": "statements", "from_": "statements@example.com", "subject": "Statement"}],
                        "transaction_patterns": [{"name": "other", "regex": "pattern"}],
                    },
                ],
            }
        }

        definitions = build_statement_definitions(config)

        self.assertEqual(len(definitions), 2)
        self.assertEqual(definitions[0]["name"], "sbi")
        self.assertEqual(definitions[1]["query"][0]["subject"], "Statement")

    def test_uses_configured_field_mapping_for_transaction_patterns(self):
        config = {
            "transaction_patterns": [
                {
                    "name": "custom",
                    "regex": r"Amount (?P<total>[\d,]+(?:\.\d+)?) at (?P<vendor>.+)",
                    "field_mapping": {"amount": "total", "merchant": "vendor"},
                }
            ]
        }

        details = extract_transaction_details(
            "Amount 1,234.56 at Example Store",
            config=config,
        )

        self.assertEqual(details["amount"], 1234.56)
        self.assertEqual(details["merchant"], "Example Store")

    def test_extracts_hdfc_details_with_vpa_and_merchant(self):
        config = {
            "transaction_patterns": [
                {
                    "name": "hdfc_card",
                    "regex": (
                        r"(?P<currency>Rs\.|₹)\s*(?P<amount>[\d,]+(?:\.\d+)?)\s+"
                        r"is debited from your account ending\s+(?P<card_last4>\d{4})\s+"
                        r"towards(?:\s+VPA)?\s+(?P<vpa>[^\s]+)\s+\((?P<merchant>[^)]+)\)\s+"
                        r"on\s+(?P<date>\d{1,2}-\d{1,2}-\d{2,4})\.\s*"
                        r"(?P<channel>UPI)\s+transaction reference no\.\s*:\s*(?P<reference_no>\d+)"
                    ),
                    "field_mapping": {
                        "amount": "amount",
                        "merchant": "merchant",
                        "card_last4": "card_last4",
                        "transaction_date": "date",
                        "reference_no": "reference_no",
                        "channel": "channel",
                        "currency": "currency",
                        "vpa": "vpa",
                    },
                }
            ]
        }

        sample_text = (
            "Dear Customer,\n\nGreetings from HDFC Bank!\n\n"
            "Rs.250.00 is debited from your account ending 8367 towards VPA "
            "bharatpe.9t0z0f0c3c975442@unitype (Santhosh) on 26-06-26.\n\n"
            "UPI transaction reference no.: 209335242963."
        )

        details = extract_transaction_details(sample_text, config=config)

        self.assertEqual(details["amount"], 250.0)
        self.assertEqual(details["merchant"], "Santhosh")
        self.assertEqual(details["vpa"], "bharatpe.9t0z0f0c3c975442@unitype")


if __name__ == "__main__":
    unittest.main()
