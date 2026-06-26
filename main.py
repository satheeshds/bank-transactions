from __future__ import annotations

from config import build_statement_definitions, load_config
from imap_client import build_query, get_mailbox_client
from parser import convert_to_timezone, extract_transaction_details


def main():
    config = load_config()
    fetch_config = config.get("fetch", {})
    statements = build_statement_definitions(config)

    print("Hello from bank-transactions!")
    for statement in statements:
        mailbox_config = statement.get("mailbox")
        if mailbox_config is None:
            raise KeyError("mailbox configuration is required for each statement")

        with get_mailbox_client(mailbox_config) as mailbox:
            for query_filter in statement.get("query", []):
                query = build_query(query_filter)
                for msg in mailbox.fetch(
                    query,
                    reverse=fetch_config.get("reverse", True),
                    limit=fetch_config.get("limit", 15),
                ):
                    try:
                        details = extract_transaction_details(
                            msg,
                            config={**config, "transaction_patterns": statement.get("transaction_patterns")},
                        )
                    except ValueError:
                        details = None

                    print(convert_to_timezone(msg.date), msg.subject, details)


if __name__ == "__main__":
    main()
