from __future__ import annotations

from typing import Any

from config import build_firefly_config, build_source_models
from firefly import _build_firefly_transaction
from firefly_client import FireflyClientError, build_firefly_client
from imap_client import build_query, get_mailbox_client, is_message_processed, mark_message_processed
from models import SourceDefinition
from parser import convert_to_timezone, extract_transaction


class TransactionImportService:
    def __init__(
        self,
        config: dict[str, Any],
        sources: list[SourceDefinition],
        firefly_client: Any | None = None,
    ) -> None:
        self.config = config
        self.sources = sources
        self.firefly_client = firefly_client
        self.fetch_config = config.get("fetch", {})
        dev_config = config.get("dev", {})
        self.enable_processed_tagging = dev_config.get("enable_processed_tagging", True)

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "TransactionImportService":
        sources = build_source_models(config)

        firefly_client = None
        firefly_config = build_firefly_config(config)
        if firefly_config.get("base_url") and firefly_config.get("token"):
            try:
                firefly_client = build_firefly_client(firefly_config)
            except ValueError:
                firefly_client = None

        return cls(config=config, sources=sources, firefly_client=firefly_client)

    def run(self) -> None:
        print("Hello from bank-transactions!")
        for source in self.sources:
            self._process_source(source)

    def _process_source(self, source: SourceDefinition) -> None:
        mailbox_config = source.mailbox
        if mailbox_config is None:
            raise KeyError("mailbox configuration is required for each source")

        with get_mailbox_client(mailbox_config) as mailbox:
            for query_filter in source.query:
                processed_tag = source.processed_tag if self.enable_processed_tagging else None
                query = build_query(query_filter, processed_tag=processed_tag)
                for msg in mailbox.fetch(
                    query,
                    reverse=self.fetch_config.get("reverse", True),
                    limit=self.fetch_config.get("limit", 15),
                ):
                    self._process_message(mailbox, msg, source)

    def _process_message(self, mailbox: Any, message: Any, source: SourceDefinition) -> None:
        if self.enable_processed_tagging and is_message_processed(message, source.processed_tag):
            print("Skipping already processed message:", message.subject)
            return

        try:
            details = extract_transaction(
                message,
                config={
                    **self.config,
                    "transaction_patterns": source.transaction_patterns,
                },
            )
        except ValueError:
            details = None

        if details and self.firefly_client is not None:
            try:
                payload = _build_firefly_transaction(details, message.date, {"firefly": source.firefly})
                self.firefly_client.create_transaction(payload)
                print("Posted to Firefly:", payload)
                if self.enable_processed_tagging:
                    mark_message_processed(mailbox, message, source.processed_tag)
            except FireflyClientError as exc:
                print("Firefly post failed:", exc)

        print(convert_to_timezone(message.date), message.subject, details.as_dict() if details else None)
