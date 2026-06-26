from __future__ import annotations

try:
    from imap_tools import AND, MailBox
except ImportError:  # pragma: no cover - exercised when dependency is unavailable
    AND = None
    MailBox = None


def get_mailbox_client(mailbox_config: dict):
    if MailBox is None or AND is None:
        raise RuntimeError("imap_tools is not installed; install it to fetch emails from your mailbox.")
    return MailBox(mailbox_config["host"]).login(mailbox_config["username"], mailbox_config["password"])


def build_query(query_filter: dict):
    if AND is None:
        raise RuntimeError("imap_tools is not installed; install it to fetch emails from your mailbox.")
    return AND(**{key: value for key, value in query_filter.items() if key != "name"})
