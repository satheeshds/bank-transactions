from __future__ import annotations

from typing import Any

from app.config import build_firefly_config, build_source_models
from app.db import session as database
import logging
import traceback
from app.services.firefly_builder import _build_firefly_transaction
from app.services.firefly_client import FireflyClientError, build_firefly_client
from app.services.imap import build_query, get_mailbox_client, is_message_processed, mark_message_processed
from imap_tools import A, OR
from app.models import SourceDefinition
from app.services.parser import convert_to_timezone, extract_transaction_details


def build_imap_query(conditions: list, processed_tag: str | None = None):
    """Return a fetch_query for the given conditions."""
    query = build_query(conditions or [], processed_tag=processed_tag)
    fetch_query = query
    if isinstance(query, dict) and "criteria" in query:
        fetch_query = query.get("criteria")
    elif isinstance(query, list):
        try:
            fetch_query = OR(*[A(**(q or {})) for q in query])
        except Exception:
            fetch_query = query
    elif isinstance(query, dict):
        try:
            fetch_query = A(**query)
        except Exception:
            fetch_query = query
    return fetch_query


def fetch_messages(mailbox, fetch_query, reverse: bool = True, limit: int = 15) -> list:
    """Fetch messages from mailbox with de-duplication by uid."""
    messages = []
    seen_uids = set()
    for msg in mailbox.fetch(fetch_query, reverse=reverse, limit=limit):
        uid = getattr(msg, 'uid', None)
        if uid and uid in seen_uids:
            continue
        seen_uids.add(uid)
        messages.append(msg)
    return messages


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
        # Include exception stack trace when logging errors
        if level.upper() == "ERROR":
            tb = traceback.format_exc()
            if tb and not tb.strip().endswith('NoneType: None'):
                message = f"{message}\n{tb}"

        # Print immediately (flush) so background threads' debug messages appear in stdout
        # print(f"[{level}] {message}")

        # Also route through python logging so server loggers capture it when configured
        logger = logging.getLogger("mail2firefly")
        if level.upper() == "DEBUG":
            logger.debug(message)
        elif level.upper() == "WARNING":
            logger.warning(message)
        elif level.upper() == "ERROR":
            logger.error(message)
        else:
            logger.info(message)

        from app.db.session import log_sync_message
        log_sync_message(self.run_id, level, message)

    def run(self) -> None:
        self.log("Hello from Mail2Firefly sync service!")

        # Prefer DB-driven rules if available: iterate parsing rules stored in DB
        try:
            db_rules = database.get_parsing_rules()
        except Exception:
            db_rules = []

        if db_rules:
            self._run_db_rules(db_rules)
            return

        # If no DB-driven rules are present, do not fall back to config-sources.
        # This keeps processing focused on DB rules and avoids building queries
        # from configured sources which may be undesirable in some deployments.
        self.log("No DB parsing rules found; skipping config-based sources.")


    def _run_db_rules(self, rules: list[dict]) -> None:
        """Process emails by iterating parsing rules from the DB.

        Each rule's `source_name` must match a mailbox entry in the `mailboxes` table.
        The rule's `conditions` (from `conditions_json`) are used as IMAP queries.
        The rule's `regex` is used as the single transaction pattern for parsing.
        """
        # Build mailbox lookup by name
        try:
            mailboxes = {m.get('name'): m for m in database.list_mailboxes()}
        except Exception as e:
            self.log(f"Failed to load mailboxes from DB: {e}", "ERROR")
            return

        for rule in rules:
            mailbox_name = rule.get('source_name') or ''
            mailbox_entry = mailboxes.get(mailbox_name)
            if not mailbox_entry:
                # try default mailbox (empty name)
                mailbox_entry = mailboxes.get('')
            if not mailbox_entry:
                self.log(f"No mailbox found for rule '{rule.get('rule_name')}' (source_name={mailbox_name})", "ERROR")
                continue
            
            mailbox_row = database.get_mailbox_by_id(mailbox_entry['id'])
            safe_mailbox_row = dict(mailbox_row or {})
            safe_mailbox_row.pop("password", None)
            self.log(f"Processing rule '{rule.get('rule_name')}' for mailbox data: {safe_mailbox_row}", "DEBUG")
            # Conditions may be a list or a single mapping
            conditions = rule.get('conditions') or []
            if isinstance(conditions, dict):
                conditions = [conditions]
            if not isinstance(conditions, list) or not conditions:
                # if no conditions provided, default to empty query (fetch recent)
                conditions = [{}]

            self.log(f"Processing rule '{rule.get('rule_name')}' conditions: {conditions}", "DEBUG")
            # Prepare a temporary SourceDefinition for parsing
            try:
                with get_mailbox_client(mailbox_row) as mailbox:
                    processed_tag = mailbox_row.get('processed_tag')

                    # If the DB mailbox has no processed_tag set, fall back to the
                    # configured default in `config.toml`, or the hardcoded
                    # "processed" fallback if not present in config.
                    if processed_tag is None or (isinstance(processed_tag, str) and processed_tag.strip() == ""):
                        processed_tag = self.config.get("processed_tag") or "processed"

                    fetch_query = build_imap_query(conditions, processed_tag=processed_tag)
                    self.log(f"Built combined IMAP query for rule '{rule.get('rule_name')}': {fetch_query}", "DEBUG")
                    self.log(f"Fetching messages for rule '{rule.get('rule_name')}' with combined query", "DEBUG")
                    messages = fetch_messages(
                        mailbox,
                        fetch_query,
                        reverse=self.fetch_config.get("reverse", True),
                        limit=self.fetch_config.get("limit", 15),
                    )
                    self.unprocessed_emails += len(messages)
                    self.log(f"Rule '{rule.get('rule_name')}' fetched {len(messages)} messages")

                    # Create a minimal source model to reuse _process_message
                    temp_source = self._build_temp_source(mailbox_name, mailbox_row, rule, processed_tag)

                    for msg in messages:
                        try:
                            self._process_message(mailbox, msg, temp_source, rule)
                        except Exception as e:
                            self.log(f"Failed processing message for rule '{rule.get('rule_name')}': {e}", "ERROR")
            except Exception as e:
                self.log(f"Failed to fetch messages for rule '{rule.get('rule_name')}': {e}", "ERROR")


    def _process_message(self, mailbox: Any, message: Any, source: SourceDefinition, rule_id: Any = None) -> None:
        if self.enable_processed_tagging and is_message_processed(message, source.processed_tag):
            self.log(f"Skipping already processed message: {message.subject}")
            return

        self.log(f"Processing message: {message.subject} ({convert_to_timezone(message.date)})")

        # Parse the message using the source's transaction patterns
        try:
            details_obj = extract_transaction_details(
                message,
                config={**self.config, "transaction_patterns": source.transaction_patterns},
            )
        except Exception as exc:
            self.log(f"Parser failed for '{message.subject}': {exc}", "ERROR")
            self.error_count += 1
            from app.db.session import log_transaction
            rule_name = getattr(source, '_db_rule_name', None)
            raw_email_body = getattr(message, 'html', None) or getattr(message, 'text', None) or None
            log_transaction(
                transaction_date=None,
                merchant=None,
                amount=None,
                currency=None,
                status="error",
                error_message=f"Parser exception: {exc}",
                rule_name=rule_name,
                rule_id=(rule_id.get('id') if isinstance(rule_id, dict) else rule_id),
                source_name=source.name,
                email_subject=message.subject,
                raw_email=raw_email_body,
            )
            return

        # convert to mutable dict and attach rule metadata + mappings
        try:
            details = details_obj.as_dict() if hasattr(details_obj, 'as_dict') else dict(details_obj)
        except Exception:
            details = details_obj if isinstance(details_obj, dict) else {}

        # Attach rule info and mappings (rule passed in as dict via caller)
        rule = rule_id if isinstance(rule_id, dict) else None
        details = self._prepare_details_for_firefly(details, rule, source)
        self.log(f"Parser matched fields: {details}", "DEBUG")

        if details is None:
            self.log(f"No transaction details matched in email: {message.subject}", "WARNING")
            self.error_count += 1
            from app.db.session import log_transaction
            rule_name = getattr(source, '_db_rule_name', None)
            raw_email_body = getattr(message, 'html', None) or getattr(message, 'text', None) or None
            log_transaction(
                transaction_date=None,
                merchant=None,
                amount=None,
                currency=None,
                status="error",
                error_message="No matching transaction pattern",
                rule_name=rule_name,
                rule_id=rule_id,
                source_name=source.name,
                email_subject=message.subject,
                raw_email=raw_email_body,
            )
            return

        status = "pending"
        error_msg = None

        status, payload, error_msg = self._post_to_firefly(details, message.date, source, mailbox, message, rule)

        from app.db.session import log_transaction
        # details may be a dict (we converted earlier) or object
        try:
            tx_date = details.get('transaction_date') if isinstance(details, dict) else details.transaction_date
            merchant = details.get('merchant') if isinstance(details, dict) else details.merchant
            amount = details.get('amount') if isinstance(details, dict) else details.amount
            currency = details.get('currency') if isinstance(details, dict) else details.currency
            reference_no = details.get('reference_no') if isinstance(details, dict) else details.reference_no
            rule_name = details.get('rule_name') if isinstance(details, dict) else getattr(source, '_db_rule_name', None)
        except Exception:
            tx_date = merchant = amount = currency = reference_no = rule_name = rule_id = None

        raw_email_body = getattr(message, 'html', None) or getattr(message, 'text', None) or None
        payload_str = str(payload) if 'payload' in locals() else None
        log_transaction(
            transaction_date=tx_date,
            merchant=merchant,
            amount=amount,
            currency=currency,
            status=status,
            error_message=error_msg,
            rule_name=rule_name,
            rule_id=(rule_id.get('id') if isinstance(rule_id, dict) else rule_id),
            raw_email=raw_email_body,
            firefly_payload=payload_str,
            source_name=source.name,
            email_subject=message.subject,
            reference_no=reference_no,
        )

    def _build_temp_source(self, mailbox_name: str, mailbox_row: dict, rule: dict, processed_tag: str | None = None) -> SourceDefinition:
        """Construct a minimal SourceDefinition from DB rule and mailbox row."""
        temp_source = SourceDefinition(
            name=mailbox_name,
            mailbox={k: mailbox_row.get(k) for k in ('host', 'username', 'password', 'port', 'encryption')},
            query=[rule.get('conditions') or {}],
            transaction_patterns=[{"name": rule.get('rule_name'), "regex": rule.get('regex')}],
            firefly={},
            processed_tag=processed_tag,
        )
        try:
            setattr(temp_source, '_db_rule_name', rule.get('rule_name'))
            setattr(temp_source, '_db_rule_id', rule.get('id'))
        except Exception:
            pass
        return temp_source

    def _prepare_details_for_firefly(self, details: dict, rule: dict | None, source: SourceDefinition) -> dict:
        """Attach rule metadata and mappings to parsed details dict."""
        out = dict(details or {})
        # attach rule name/id
        if rule and isinstance(rule, dict):
            out['rule_name'] = rule.get('rule_name') or getattr(source, '_db_rule_name', None)
            out['rule_id'] = rule.get('id')
            # attach mappings if present
            mappings = rule.get('mappings') or rule.get('mappings_json') or None
            if mappings:
                out['mappings'] = mappings
        else:
            # fallback to source attributes
            rule_name = getattr(source, '_db_rule_name', None)
            if rule_name:
                out['rule_name'] = rule_name
        return out

    def _post_to_firefly(self, details: dict, message_date: object | None, source: SourceDefinition, mailbox: Any, message: Any, rule: dict | None = None) -> tuple[str, dict | None, str | None]:
        """Build payload, post to Firefly if configured, and return (status, payload, error_msg)."""
        status = "pending"
        error_msg = None
        payload = None

        # Ensure debugging-only rule fields are not sent to Firefly
        details_for_firefly = dict(details)
        details_for_firefly.pop('rule_name', None)
        details_for_firefly.pop('rule_id', None)
        payload = _build_firefly_transaction(details_for_firefly, message_date, {"firefly": source.firefly}, message)
        self.log(f"Built Firefly payload: {payload}", "DEBUG")

        if self.firefly_client is not None:
            try:
                self.firefly_client.create_transaction(payload)
                self.log(f"Posted transaction to Firefly: {payload}")
                status = "synced"
                self.parsed_count += 1
                if self.enable_processed_tagging:
                    mark_message_processed(mailbox, message, source.processed_tag)
                else:
                    self.log("Processed tagging is disabled; message will not be marked as processed.", "WARNING")
            except FireflyClientError as exc:
                self.log(f"Firefly post failed: {exc}", "ERROR")
                status = "error"
                error_msg = str(exc)
                self.error_count += 1
        else:
            self.log(f"Firefly client not configured. Transaction parsed: {details}", "WARNING")
            status = "pending"
            self.parsed_count += 1

        return status, payload, error_msg
