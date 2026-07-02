from __future__ import annotations

from pathlib import Path
import re
import tomllib

from app.models import SourceDefinition

CONFIG_PATH = Path(__file__).parent.parent / "config.toml"
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
        config = tomllib.load(config_file)

    mailbox = config.get("mailbox")
    if isinstance(mailbox, dict):
        sources = mailbox.get("sources")
        statements = mailbox.get("statements")
        if sources is not None and statements is None:
            mailbox["statements"] = sources
        if statements is not None and sources is None:
            mailbox["sources"] = statements

    return config


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


def build_source_definitions(config: dict | None = None) -> list[dict]:
    if not config:
        return []

    mailbox_config = config.get("mailbox")
    if mailbox_config is None:
        mailbox_config = {}

    raw_definitions = mailbox_config.get("sources")
    if raw_definitions is None:
        raw_definitions = config.get("sources")
    if raw_definitions is None:
        raw_query = config.get("query")
        if raw_query is None:
            return []
        raw_definitions = [{"query": raw_query, "transaction_patterns": config.get("transaction_patterns")}]

    if isinstance(raw_definitions, dict):
        raw_definitions = [raw_definitions]
    if not isinstance(raw_definitions, list):
        raise TypeError("mailbox.sources must be a mapping or a list of mappings")

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

        processed_tag = definition.get("processed_tag")
        if processed_tag is None:
            processed_tag = mailbox_config.get("processed_tag")
        if processed_tag is None:
            processed_tag = config.get("processed_tag")

        definitions.append(
            {
                "name": definition.get("name"),
                "mailbox": mailbox_config,
                "query": [dict(item) for item in query],
                "transaction_patterns": patterns,
                "firefly": {
                    "account_id": firefly_config.get("account_id", ""),
                },
                "processed_tag": processed_tag,
            }
        )

    return definitions


def build_source_models(config: dict | None = None) -> list[SourceDefinition]:
    return [
        SourceDefinition(
            name=source.get("name"),
            mailbox=dict(source.get("mailbox") or {}),
            query=[dict(item) for item in source.get("query", [])],
            transaction_patterns=source.get("transaction_patterns"),
            firefly=dict(source.get("firefly") or {}),
            processed_tag=source.get("processed_tag"),
        )
        for source in build_source_definitions(config)
    ]


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


def _coerce_firefly_mapping(pattern_config: dict | None) -> dict:
    if not isinstance(pattern_config, dict):
        return {}

    firefly_mapping = pattern_config.get("firefly_mapping")
    if isinstance(firefly_mapping, dict):
        return firefly_mapping

    firefly_config = pattern_config.get("firefly")
    if isinstance(firefly_config, dict):
        return firefly_config

    legacy_mapping: dict[str, object] = {}
    for key in ("source_field", "destination_field", "source_value", "destination_value"):
        value = pattern_config.get(key)
        if value is not None:
            legacy_mapping[key] = value
    return legacy_mapping


def build_transaction_patterns(config: dict | None = None) -> list[dict]:
    raw_patterns = (config or {}).get("transaction_patterns")
    if raw_patterns is None:
        raw_patterns = DEFAULT_TRANSACTION_PATTERNS
