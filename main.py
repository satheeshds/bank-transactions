from __future__ import annotations

from imap_tools import MailBox

from config import build_firefly_config, build_source_definitions, load_config
from firefly import _build_firefly_transaction
from firefly_client import FireflyClientError, build_firefly_client
from imap_client import build_query, get_mailbox_client, is_message_processed, mark_message_processed
from parser import convert_to_timezone, extract_transaction_details



def main():
    config = load_config()
    fetch_config = config.get("fetch", {})
    dev_config = config.get("dev", {})
    enable_processed_tagging = dev_config.get("enable_processed_tagging", True)
    sources = build_source_definitions(config)

    firefly_client = None
    firefly_config = build_firefly_config(config)
    if firefly_config.get("base_url") and firefly_config.get("token"):
        try:
            firefly_client = build_firefly_client(firefly_config)
        except ValueError:
            firefly_client = None

    print("Hello from bank-transactions!")
    for source in sources:
        mailbox_config = source.get("mailbox")
        if mailbox_config is None:
            raise KeyError("mailbox configuration is required for each source")

        with get_mailbox_client(mailbox_config) as mailbox:
            for query_filter in source.get("query", []):
                # Use processed_tag in query only if tagging is enabled
                processed_tag = source.get("processed_tag") if enable_processed_tagging else None
                query = build_query(query_filter, processed_tag=processed_tag)
                for msg in mailbox.fetch(
                    query,
                    reverse=fetch_config.get("reverse", True),
                    limit=fetch_config.get("limit", 15),
                ):
                    # Skip processed message check if tagging is disabled
                    if enable_processed_tagging:
                        processed_tag = source.get("processed_tag")
                        if is_message_processed(msg, processed_tag):
                            print("Skipping already processed message:", msg.subject)
                            continue

                    try:
                        details = extract_transaction_details(
                            msg,
                            config={**config, "transaction_patterns": source.get("transaction_patterns")},
                        )
                    except ValueError:
                        details = None

                    if details and firefly_client is not None:
                        try:
                            payload = _build_firefly_transaction(details, msg.date, source)
                            firefly_client.create_transaction(payload)
                            print("Posted to Firefly:", payload)
                            # Mark message as processed only if tagging is enabled
                            if enable_processed_tagging:
                                processed_tag = source.get("processed_tag")
                                mark_message_processed(mailbox, msg, processed_tag)
                        except FireflyClientError as exc:
                            print("Firefly post failed:", exc)

                    print(convert_to_timezone(msg.date), msg.subject, details)


if __name__ == "__main__":
    main()
