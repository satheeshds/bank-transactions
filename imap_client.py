from __future__ import annotations

try:
    from imap_tools import AND, MailBox, NOT
except ImportError:  # pragma: no cover - exercised when dependency is unavailable
    AND = None
    NOT = None
    MailBox = None


def get_mailbox_client(mailbox_config: dict):
    if MailBox is None or AND is None:
        raise RuntimeError("imap_tools is not installed; install it to fetch emails from your mailbox.")
    return MailBox(mailbox_config["host"]).login(mailbox_config["username"], mailbox_config["password"])


def build_query(query_filter: dict, processed_tag: str | None = None):
    if AND is None:
        raise RuntimeError("imap_tools is not installed; install it to fetch emails from your mailbox.")

    query_kwargs = {key: value for key, value in query_filter.items() if key not in {"name", "processed_tag"}}
    if processed_tag:
        if NOT is None:
            raise RuntimeError("imap_tools is not installed; install it to fetch emails from your mailbox.")
        return AND(**query_kwargs, no_keyword=processed_tag)
    return AND(**query_kwargs)
