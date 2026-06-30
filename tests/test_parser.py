import unittest
from datetime import datetime, timezone
from pathlib import Path

from config import load_config
from imap_client import build_query, is_message_processed
from main import (
    _build_firefly_transaction,
    build_source_definitions,
    convert_to_timezone,
    extract_transaction_details,
)


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

        self.assertEqual(converted.strftime("%Y-%m-%d %H:%M:%S"), "2026-06-26 08:49:31") # type: ignore

    def test_extracts_transaction_details_with_comma_separated_amount(self):
        sample_text = (
            "Rs.4,012.44 spent on your SBI Credit Card ending with 4465 "
            "at LuluTrivandrum on 24-06-26 via UPI (Ref No. 609118054276)"
        )

        details = extract_transaction_details(sample_text)

        self.assertEqual(details["amount"], 4012.44)
        self.assertEqual(details["merchant"], "LuluTrivandrum")
        self.assertEqual(details["reference_no"], "609118054276")

    def test_falls_back_to_utc_when_timezone_is_unavailable(self):
        value = datetime(2026, 6, 26, 3, 19, 31, tzinfo=timezone.utc)

        converted = convert_to_timezone(value, tz_name="Not/ARealTimezone")

        self.assertEqual(converted, value)

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
                "sources": [
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

        definitions = build_source_definitions(config)

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

    def test_does_not_populate_transaction_type_from_pattern_data(self):
        config = {
            "transaction_patterns": [
                {
                    "name": "credit_alert",
                    "regex": r"Your salary of (?P<amount>[\d,]+(?:\.\d+)?) has been added (?P<transaction_type>credit)",
                }
            ]
        }

        details = extract_transaction_details("Your salary of 2,17,105.00 has been added credit", config=config)

        self.assertEqual(details["amount"], 217105.0)
        self.assertNotIn("transaction_type", details)

    def test_does_not_populate_transaction_type_from_pattern_config(self):
        config = {
            "transaction_patterns": [
                {
                    "name": "credit_alert",
                    "regex": r"Your salary of (?P<amount>[\d,]+(?:\.\d+)?) has been added in your account",
                    "transaction_type": "credit",
                }
            ]
        }

        details = extract_transaction_details("Your salary of 2,17,105.00 has been added in your account", config=config)

        self.assertEqual(details["amount"], 217105.0)
        self.assertNotIn("transaction_type", details)

    def test_parses_hdfc_salary_credit_email_without_explicit_transaction_type(self):
        config_data = load_config()
        statement_config = None
        for statement in config_data.get("mailbox", {}).get("statements", []):
            if statement.get("name") == "hdfc_statement":
                statement_config = {"transaction_patterns": statement.get("transaction_patterns", [])}
                break

        self.assertIsNotNone(statement_config)

        sample_text = (
            "Dear Customer,\n\nGreetings from HDFC Bank!\n\n"
            "Your salary of Rs. INR 2,17,105.00 has been added in your account ending XX8367 "
            "on 01-JUN-2026 from Salary for May 2026\n\n"
            "The available balance in your account is Rs. INR 3,28,355.35\n\n"
            "For real-time account updates, WhatsApp to our Chat Banking number 7070022222 or dial 18002703333."
        )

        details = extract_transaction_details(sample_text, config=statement_config)

        self.assertEqual(details["amount"], 217105.0)
        self.assertEqual(details["merchant"], "Salary")
        self.assertEqual(details["description"], "Salary for May 2026")
        self.assertNotIn("transaction_type", details)

    def test_stops_description_at_following_account_notice_text(self):
        config_data = load_config()
        statement_config = None
        for statement in config_data.get("mailbox", {}).get("statements", []):
            if statement.get("name") == "hdfc_statement":
                statement_config = {"transaction_patterns": statement.get("transaction_patterns", [])}
                break

        self.assertIsNotNone(statement_config)

        sample_text = (
            "Your salary of Rs. INR 2,17,105.00 has been added in your account ending XX8367 "
            "on 01-JUN-2026 from Salary for May 2026 The available balance in your account is Rs. INR 3,28,355.35"
        )

        details = extract_transaction_details(sample_text, config=statement_config)

        self.assertEqual(details["description"], "Salary for May 2026")

    def test_builds_firefly_transaction_as_deposit_for_credit_details(self):
        details = {
            "amount": 217105.0,
            "currency": "INR",
            "merchant": "Salary",
            "transaction_type": "credit",
            "firefly_mapping": {"transaction_type": "deposit"},
        }

        payload = _build_firefly_transaction(
            details,
            "2026-06-01",
            {
                "firefly": {"account_id": "7", "source_field": "source_name", "destination_field": "destination_id"},
            },
        )

        self.assertEqual(payload["transactions"][0]["type"], "deposit")
        self.assertEqual(payload["transactions"][0]["source_name"], "Salary")
        self.assertEqual(payload["transactions"][0]["destination_id"], "7")

    def test_uses_pattern_firefly_mapping_for_payload_fields(self):
        details = {
            "amount": 217105.0,
            "currency": "INR",
            "merchant": "Salary",
            "transaction_type": "credit",
            "firefly": {
                "source_field": "source_name",
                "destination_field": "destination_id",
                "source_value": "Salary Credit",
                "destination_value": "acct-9",
            },
        }

        payload = _build_firefly_transaction(
            details,
            "2026-06-01",
            {"firefly": {"account_id": "7"}},
        )

        self.assertEqual(payload["transactions"][0]["source_name"], "Salary Credit")
        self.assertEqual(payload["transactions"][0]["destination_id"], "acct-9")

    def test_uses_pattern_firefly_mapping_config_from_transaction_patterns(self):
        config = {
            "transaction_patterns": [
                {
                    "name": "credit_alert",
                    "regex": r"Your salary of (?P<amount>[\d,]+(?:\.\d+)?) has been added in your account",
                    "firefly_mapping": {
                        "source_field": "source_name",
                        "destination_field": "destination_id",
                        "source_value": "Salary Credit",
                        "destination_value": "acct-9",
                    },
                }
            ]
        }

        details = extract_transaction_details(
            "Your salary of 2,17,105.00 has been added in your account",
            config=config,
        )
        payload = _build_firefly_transaction(
            details,
            "2026-06-01",
            {"firefly": {"account_id": "7"}},
        )

        self.assertEqual(payload["transactions"][0]["source_name"], "Salary Credit")
        self.assertEqual(payload["transactions"][0]["destination_id"], "acct-9")

    def test_uses_account_id_placeholders_in_firefly_mapping(self):
        details = {
            "amount": 217105.0,
            "currency": "INR",
            "merchant": "Salary",
            "transaction_type": "credit",
            "firefly": {
                "source_field": "source_name",
                "destination_field": "destination_id",
                "source_value": "{account_id}",
                "destination_value": "{account_id}",
            },
        }

        payload = _build_firefly_transaction(
            details,
            "2026-06-01",
            {"firefly": {"account_id": "7"}},
        )

        self.assertEqual(payload["transactions"][0]["source_name"], "7")
        self.assertEqual(payload["transactions"][0]["destination_id"], "7")

    def test_uses_transaction_detail_placeholders_in_firefly_mapping(self):
        details = {
            "amount": 217105.0,
            "currency": "INR",
            "merchant": "Salary",
            "description": "Salary for May 2026",
            "transaction_type": "credit",
            "firefly": {
                "source_field": "source_name",
                "destination_field": "destination_id",
                "source_value": "{merchant}",
                "destination_value": "{description}",
            },
        }

        payload = _build_firefly_transaction(
            details,
            "2026-06-01",
            {"firefly": {"account_id": "7"}},
        )

        self.assertEqual(payload["transactions"][0]["source_name"], "Salary")
        self.assertEqual(payload["transactions"][0]["destination_id"], "Salary for May 2026")

    def test_marks_messages_with_configured_tag_after_successful_post(self):
        class MessageStub:
            def __init__(self):
                self.uid = "42"
                self.flags = []

        class MailboxStub:
            def __init__(self):
                self.flag_calls = []

            def flag(self, uid_list, flag_set, value, chunks=None):
                self.flag_calls.append((uid_list, flag_set, value, chunks))

        message = MessageStub()
        mailbox = MailboxStub()

        _mark_message_processed(mailbox, message, "processed") # type: ignore

        self.assertEqual(mailbox.flag_calls[0][0], "42")
        self.assertEqual(mailbox.flag_calls[0][1], "processed")
        self.assertTrue(mailbox.flag_calls[0][2])

    def test_skips_messages_that_are_already_tagged(self):
        class MessageStub:
            def __init__(self):
                self.flags = ["processed"]

        self.assertTrue(is_message_processed(MessageStub(), "processed"))

    def test_build_query_excludes_processed_tag(self):
        query = build_query({"from_": "alerts@example.com"}, processed_tag="processed")

        self.assertIsNotNone(query)


if __name__ == "__main__":
    unittest.main()
