from __future__ import annotations

from typing import Any
import logging

logger = logging.getLogger(__name__)


def resolve_fixed(mapping: dict[str, Any], details: dict[str, Any], message: object | None = None) -> Any:
    logger.debug("resolve_fixed start mapping=%s details_keys=%s", mapping, list(details.keys()))
    result = mapping.get("value")
    logger.debug("resolve_fixed result=%s", result)
    return result


def resolve_firefly(mapping: dict[str, Any], details: dict[str, Any], message: object | None = None) -> Any:
    # treated as a fixed value representing Firefly account fields
    logger.debug("resolve_firefly start mapping=%s details_keys=%s", mapping, list(details.keys()))
    result = mapping.get("value")
    logger.debug("resolve_firefly result=%s", result)
    return result


def resolve_imap(mapping: dict[str, Any], details: dict[str, Any], message: object | None = None) -> Any:
    imap_field = mapping.get("imap_field")
    if not imap_field:
        return None
    # message may be provided by caller; fall back to details dict
    logger.debug("resolve_imap start imap_field=%s mapping=%s message=%s", imap_field, mapping, message)
    if message is not None and hasattr(message, imap_field):
        result = getattr(message, imap_field)
        logger.debug("resolve_imap from message result=%s", result)
        return result
    # If message provided but doesn't have the attribute, log its available attributes for debugging
    if message is not None and not hasattr(message, imap_field):
        attrs: dict[str, object] = {}
        for a in dir(message):
            if a.startswith("_"):
                continue
            try:
                v = getattr(message, a)
            except Exception:
                v = "<error>"
            # skip callables (methods)
            if callable(v):
                continue
            attrs[a] = v
        logger.debug("resolve_imap message attributes (non-callable): %s", attrs)
    result = details.get(imap_field)
    logger.debug("resolve_imap from details result=%s", result)
    return result


def resolve_regex_group(mapping: dict[str, Any], details: dict[str, Any], message: object | None = None) -> Any:
    grp = mapping.get("group")
    if grp is None:
        return None
    groups = details.get("groups") or []
    groupdict = details.get("groupdict") or {}
    logger.debug("resolve_regex_group start group=%s groups=%s groupdict=%s mapping=%s", grp, groups, groupdict, mapping)
    # prefer named groups
    if isinstance(groupdict, dict) and str(grp) in groupdict:
        result = groupdict.get(str(grp))
        logger.debug("resolve_regex_group named result=%s", result)
        return result
    try:
        idx = int(grp)
    except Exception:
        logger.debug("resolve_regex_group invalid group index: %s", grp)
        return None
    if 0 < idx <= len(groups):
        # 1-based index for regex groups
        result = groups[idx - 1]
        logger.debug("resolve_regex_group indexed result=%s", result)
        return result
    logger.debug("resolve_regex_group no match for index=%s", idx)
    return None


_RESOLVERS = {
    "fixed": resolve_fixed,
    "firefly": resolve_firefly,
    "imap": resolve_imap,
    "regex_group": resolve_regex_group,
}


def apply_mappings(details: dict[str, Any], mappings: list[dict[str, Any]] | None, message: object | None = None) -> dict[str, Any]:
    if not mappings:
        return details
    out = dict(details)
    logger.debug("apply_mappings start; mappings=%s", mappings)
    for m in mappings:
        try:
            key = m.get("fieldKey") or m.get("field")
            if not key:
                logger.debug("skipping mapping without key: %s", m)
                continue
            source_type = (m.get("source_type") or "").lower()
            resolver = _RESOLVERS.get(source_type)
            if not resolver:
                logger.debug("no resolver for source_type '%s' on mapping %s", source_type, m)
                continue
            logger.debug("applying mapping for key=%s source_type=%s mapping=%s", key, source_type, m)
            result = resolver(m, out, message)
            out[key] = result
            logger.debug("mapping applied key=%s result=%s", key, result)
        except Exception as e:
            logger.debug("failed to apply mapping %s: %s", m, e, exc_info=True)
            continue
    logger.debug("apply_mappings result=%s", out)
    return out
