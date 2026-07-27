from __future__ import annotations

from ast import And
import logging

from imap_tools.query import LogicOperator

try:
    from imap_tools import AND, MailBox, NOT
except ImportError:  # pragma: no cover - exercised when dependency is unavailable
    AND = None
    NOT = None
    MailBox = None

logger = logging.getLogger(__name__)


def get_mailbox_client(mailbox_config: dict):
    if MailBox is None or AND is None:
        raise RuntimeError("imap_tools is not installed; install it to fetch emails from your mailbox.")
    return MailBox(mailbox_config["host"]).login(mailbox_config["username"], mailbox_config["password"])


def build_query(query_filter: dict | list, processed_tag: str | None = None):
    if AND is None:
        raise RuntimeError("imap_tools is not installed; install it to fetch emails from your mailbox.")
    logger.debug("build_query start: query_filter=%s processed_tag=%s", query_filter, processed_tag)

    # Support two shapes for query_filter:
    # - mapping/dict (legacy) -> returns a single AND(...) query
    # - list of condition mappings -> when connectors include OR, return a list of dicts
    if isinstance(query_filter, list):
        # Convert conditions list into one or more simple keyword dicts.
        previous_connector: str | None = None
        search_query: str | None = None
        for cond in query_filter:
            # cond expected keys: field, operator, value, connector (AND/OR), not
            field = cond.get("field")
            operator = cond.get("operator")
            value = cond.get("value")
            connector = (cond.get("connector") or "AND").upper()
            neg = bool(cond.get("not"))
            search_key = None
            logger.debug("processing condition: field=%s operator=%s value=%s connector=%s not=%s", field, operator, value, connector, neg)

            if field and operator:
                fld = field.lower()
                op = operator.lower()

                # Map fields to IMAP keywords where possible
                if fld in ("from", "sender"):
                    search_key = f"FROM \"{value}\""
                elif fld in ("to", "recipient"):
                    search_key = f"TO \"{value}\""
                elif fld in ("subject",):
                    search_key = f"SUBJECT \"{value}\""
                elif fld in ("text", "body"):
                    search_key = f"TEXT \"{value}\""
                elif fld in ("sent_date",) and op in (">=", "<"):
                    search_key = f"SENTSINCE \"{value}\"" if op == ">=" else f"SENTBEFORE \"{value}\""
                else:
                    search_key = None

                if neg and search_key:
                    search_key = f"NOT {search_key}"
                # AND -> continue accumulating
                pass

            if previous_connector is not None:
                search_query = f"{previous_connector} {search_query} {search_key}" if previous_connector == "OR" else f"{search_query} {search_key}"
            else:
                search_query = search_key

            previous_connector = "OR" if connector == "OR" else "AND"
            
        
        if processed_tag:
            search_query = f"{search_query} UNKEYWORD \"{processed_tag}\"" if search_query else f"UNKEYWORD \"{processed_tag}\""

        search_query = f"({search_query})" if search_query else None
        # single combined AND -> return a wrapper dict so caller can see post_filters
        logger.debug("build_query returning : %s", search_query)
        return search_query if search_query else {}

    # Legacy dict path
    query_kwargs = {key: value for key, value in query_filter.items() if key not in {"name", "processed_tag"}}
    # not_query_kwargs = {key: value for key, value in query_filter.items() if key not in {"name", "processed_tag"} and "not" is True}
    logger.debug("build_query legacy dict path: query_kwargs=%s not_query_kwargs=%s processed_tag=%s", query_kwargs, "tst", processed_tag)
    if processed_tag:
        if NOT is None:
            raise RuntimeError("imap_tools is not installed; install it to fetch emails from your mailbox.")
        q = AND(**query_kwargs, no_keyword=processed_tag)
        logger.debug("build_query returning AND with no_keyword: %s", q)
        return q
    q = AND(**query_kwargs)
    logger.debug("build_query returning AND: %s", q)
    return q


def is_message_processed(message: object, tag: str | None = None) -> bool:
    if not tag:
        return False
    flags = getattr(message, "flags", None) or []
    # safe-check and debug log
    try:
        from logging import getLogger
        _log = getLogger(__name__)
        _log.debug("is_message_processed check: uid=%s tag=%s flags=%s", getattr(message, 'uid', None), tag, flags)
    except Exception:
        pass

    if not isinstance(flags, (list, tuple, set)):
        return False

    tag_lower = str(tag).strip().lower()
    return any(str(flag).strip().lower() == tag_lower for flag in flags)


def mark_message_processed(mailbox: MailBox, message: object, tag: str | None = None) -> None: # type: ignore
    if not tag:
        return

    message_uid = getattr(message, "uid", None)
    try:
        from logging import getLogger
        _log = getLogger(__name__)
        _log.debug("mark_message_processed: uid=%s tag=%s mailbox=%s", message_uid, tag, getattr(mailbox, 'host', None))
    except Exception:
        _log = None

    if message_uid in (None, ""):
        if _log:
            _log.debug("mark_message_processed: no uid available, skipping flag")
        return

    try:
        mailbox.flag(message_uid, tag, True)
        if _log:
            _log.debug("mark_message_processed: flagged uid=%s with tag=%s", message_uid, tag)
    except Exception as e:
        if _log:
            _log.error("mark_message_processed: failed to flag uid=%s with tag=%s: %s", message_uid, tag, e)
