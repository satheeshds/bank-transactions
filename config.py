from __future__ import annotations

from pathlib import Path
import re
import tomllib

CONFIG_PATH = Path(__file__).with_name("config.toml")
DEFAULT_TRANSACTION_PATTERNS = [
    {
        "name": "sbi_card",
        "regex": (
            r"(?P<currency>Rs\.|₹)\s*(?P<amount>[\d,]+(?:\.\d+)?)\s*spent on your\s+"
            r"SBI Credit Card\s+ending with\s+(?P<card_last4>\d{4})\s+"
            r"at\s+(?P<merchant>.+?)\s+on\s+(?P<date>\d{1,2}-\d{1,2}-\d{2,4})\s+"
            r"via\s+(?P<channel>.+?)\s*\(Ref No\.\s*(?P<reference_no>\d+)\)"
        ),
        "flags": ["IGNORECASE"],
    }
]


def load_config(config_path: Path = CONFIG_PATH) -> dict:
    with config_path.open("rb") as config_file:
        return tomllib.load(config_file)


def _coerce_flags(flags: object) -> int:
    if not flags:
        return 0
    if isinstance(flags, str):
        flags = [flags]
    if not isinstance(flags, (list, tuple, set)):
        raise TypeError("flags must be a string or a sequence of strings")

    compiled_flags = 0
    for flag in flags:
        if isinstance(flag, str):
            flag_name = flag.upper()
            if not hasattr(re, flag_name):
                raise ValueError(f"unsupported regex flag: {flag}")
            compiled_flags |= getattr(re, flag_name)
        else:
            compiled_flags |= int(flag)
    return compiled_flags


def build_statement_definitions(config: dict | None = None) -> list[dict]:
    if not config:
        return []

    mailbox_config = config.get("mailbox")
    if mailbox_config is None:
        mailbox_config = {}

    raw_definitions = mailbox_config.get("statements")
    if raw_definitions is None:
        raw_definitions = config.get("statements")
    if raw_definitions is None:
        raw_query = config.get("query")
        if raw_query is None:
            return []
        raw_definitions = [{"query": raw_query, "transaction_patterns": config.get("transaction_patterns")}]

    if isinstance(raw_definitions, dict):
        raw_definitions = [raw_definitions]
    if not isinstance(raw_definitions, list):
        raise TypeError("mailbox.statements must be a mapping or a list of mappings")

    definitions: list[dict] = []
    for definition in raw_definitions:
        if not isinstance(definition, dict):
            raise TypeError("each statement definition must be a mapping")

        query = definition.get("query")
        if query is None:
            query = definition.get("queries")
        if query is None:
            query = config.get("query")
        if isinstance(query, dict):
            query = [query]
        if query is None:
            query = []
        if not isinstance(query, list):
            raise TypeError("statement query must be a mapping or a list of mappings")

        patterns = definition.get("transaction_patterns")
        if patterns is None:
            patterns = config.get("transaction_patterns")

        firefly_config = definition.get("firefly")
        if not isinstance(firefly_config, dict):
            firefly_config = {}

        definitions.append(
            {
                "name": definition.get("name"),
                "mailbox": mailbox_config,
                "query": [dict(item) for item in query],
                "transaction_patterns": patterns,
                "firefly": {
                    "source_id": firefly_config.get("source_id", ""),
                },
            }
        )

    return definitions


def build_firefly_config(config: dict | None = None) -> dict:
    if not config:
        return {}

    firefly_config = config.get("firefly")
    if not isinstance(firefly_config, dict):
        return {}

    return {
        "base_url": firefly_config.get("base_url", ""),
        "token": firefly_config.get("token", ""),
        "timeout": firefly_config.get("timeout", 15),
    }


def build_transaction_patterns(config: dict | None = None) -> list[dict]:
    raw_patterns = (config or {}).get("transaction_patterns")
    if raw_patterns is None:
        raw_patterns = DEFAULT_TRANSACTION_PATTERNS

    if isinstance(raw_patterns, dict):
        raw_patterns = [raw_patterns]
    if not isinstance(raw_patterns, list):
        raise TypeError("transaction_patterns must be a mapping or a list of mappings")

    compiled_patterns: list[dict] = []
    for index, pattern_config in enumerate(raw_patterns):
        if isinstance(pattern_config, str):
            pattern_name = f"pattern_{index + 1}"
            regex = pattern_config
            flags = []
        elif isinstance(pattern_config, dict):
            pattern_name = pattern_config.get("name", f"pattern_{index + 1}")
            regex = pattern_config.get("regex") or pattern_config.get("pattern")
            if not regex:
                raise ValueError("each transaction pattern requires a regex or pattern value")
            flags = pattern_config.get("flags", [])
        else:
            raise TypeError("transaction patterns must be strings or mappings")

        compiled_patterns.append(
            {
                "name": pattern_name,
                "regex": regex,
                "field_mapping": pattern_config.get("field_mapping", {}) if isinstance(pattern_config, dict) else {},
                "compiled": re.compile(regex, _coerce_flags(flags)),
            }
        )

    return compiled_patterns
