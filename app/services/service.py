from __future__ import annotations

from typing import Any

from app.config import build_firefly_config, build_source_models
from app.db import session as database
from app.services.firefly_builder import _build_firefly_transaction
from app.services.firefly_client import FireflyClientError, build_firefly_client
from app.services.imap import build_query, get_mailbox_client, is_message_processed, mark_message_processed
from app.models import SourceDefinition
from app.services.parser import convert_to_timezone, extract_transaction


class TransactionImportService:
    def __init__(
        self,
        config: dict[str, Any],
        sources: list[SourceDefinition],
        firefly_client: Any | None = None,
        run_id: int | None = None,
    ) -> None:
        self.config = config
        self.sources = sources
        self.firefly_client = firefly_client
        self.fetch_config = config.get("fetch", {})
        dev_config = config.get("dev", {})
        self.enable_processed_tagging = dev_config.get("enable_processed_tagging", True)
        self.run_id = run_id
        self.parsed_count = 0
        self.error_count = 0
        self.unprocessed_emails = 0

    @classmethod
    def from_config(cls, config: dict[str, Any], run_id: int | None = None) -> "TransactionImportService":
        sources = build_source_models(config)

        # If there are parsing rules stored in the DB, prefer those per-source.
        try:
            db_rules = database.get_parsing_rules()
            if db_rules:
                # Group rules by source_name
                rules_by_source: dict[str, list[dict]] = {}
                for r in db_rules:
                    key = r.get("source_name") or ""
                    rules_by_source.setdefault(key, []).append(r)

                for src in sources:
                    name = src.name or ""
                    patterns = rules_by_source.get(name) or rules_by_source.get("")
                    if patterns:
                        # Convert DB rule shape to expected transaction_patterns shape (regex + name)
                        src.transaction_patterns = [
                            {"name": p.get("rule_name"), "regex": p.get("regex"), "defaults": {}, "flags": []}
                            for p in patterns
                        ]
        except Exception:
            # If DB access fails, fall back to configured patterns
            pass

        firefly_client = None
        firefly_config = build_firefly_config(config)
        if firefly_config.get("base_url") and firefly_config.get("token"):
            try:
                firefly_client = build_firefly_client(firefly_config)
            except ValueError:
                firefly_client = None

        return cls(config=config, sources=sources, firefly_client=firefly_client, run_id=run_id)

    def log(self, message: str, level: str = "INFO") -> None:
        print(f"[{level}] {message}")
        from app.db.session import log_sync_message
        log_sync_message(self.run_id, level, message)

    def run(self) -> None:
        self.log("Hello from Mail2Firefly sync service!")
        for source in self.sources:
            try:
                self._process_source(source)
            except Exception as e:
                self.log(f"Failed to process source '{source.name or 'default'}': {e}", "ERROR")

    def _process_source(self, source: SourceDefinition) -> None:
        mailbox_config = source.mailbox
        if mailbox_config is None:
            raise KeyError("mailbox configuration is required for each source")

        with get_mailbox_client(mailbox_config) as mailbox:
            for query_filter in source.query:
                processed_tag = source.processed_tag if self.enable_processed_tagging else None
                query = build_query(query_filter, processed_tag=processed_tag)
                
                self.log(f"Fetching messages for query: {query_filter} with tag {processed_tag}")
                messages = list(mailbox.fetch(
                    query,
                    reverse=self.fetch_config.get("reverse", True),
                    limit=self.fetch_config.get("limit", 15),
                ))
                
                self.unprocessed_emails += len(messages)
                self.log(f"Fetched {len(messages)} messages to process.")

                for msg in messages:
                    self._process_message(mailbox, msg, source)

    def _process_message(self, mailbox: Any, message: Any, source: SourceDefinition) -> None:
        if self.enable_processed_tagging and is_message_processed(message, source.processed_tag):
            self.log(f"Skipping already processed message: {message.subject}")
            return

        self.log(f"Processing message: {message.subject} ({convert_to_timezone(message.date)})")

        try:
            details = extract_transaction(
                message,
                config={
                    **self.config,
                    "transaction_patterns": source.transaction_patterns,
                },
            )
        except Exception as exc:
            self.log(f"Parser failed for '{message.subject}': {exc}", "ERROR")
            self.error_count += 1
            from app.db.session import log_transaction
            log_transaction(
                transaction_date=None,
                merchant=None,
                amount=None,
                currency=None,
                status="error",
                error_message=f"Parser exception: {exc}",
                source_name=source.name,
                email_subject=message.subject,
            )
            return

        if details is None:
            self.log(f"No transaction details matched in email: {message.subject}", "WARNING")
            self.error_count += 1
            from app.db.session import log_transaction
            log_transaction(
                transaction_date=None,
                merchant=None,
                amount=None,
                currency=None,
                status="error",
                error_message="No matching transaction pattern",
                source_name=source.name,
                email_subject=message.subject,
            )
            return

        status = "pending"
        error_msg = None

        if self.firefly_client is not None:
            try:
                payload = _build_firefly_transaction(details, message.date, {"firefly": source.firefly})
                self.firefly_client.create_transaction(payload)
                self.log(f"Posted transaction to Firefly: {payload}")
                status = "synced"
                self.parsed_count += 1
                if self.enable_processed_tagging:
                    mark_message_processed(mailbox, message, source.processed_tag)
            except FireflyClientError as exc:
                self.log(f"Firefly post failed: {exc}", "ERROR")
                status = "error"
                error_msg = str(exc)
                self.error_count += 1
        else:
            self.log(f"Firefly client not configured. Transaction parsed: {details.as_dict()}", "WARNING")
            status = "pending"
            self.parsed_count += 1

        from app.db.session import log_transaction
        log_transaction(
            transaction_date=details.transaction_date,
            merchant=details.merchant,
            amount=details.amount,
            currency=details.currency,
            status=status,
            error_message=error_msg,
            source_name=source.name,
            email_subject=message.subject,
            reference_no=details.reference_no,
        )
