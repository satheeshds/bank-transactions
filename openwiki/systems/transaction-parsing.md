---
type: system
title: Regex transaction parsing and field mapping
description: How Mail2Firefly compiles configured regex patterns into matchable objects, maps named capture groups onto transaction fields with per-pattern overrides, normalises amounts and dates, and converts timestamps to the configured timezone.
tags: [parser, regex, patterns, transaction-details, timezone]
verified:
  - by: openwiki/0.9.0
    at: 2026-11-25T04:51:17.394Z
sources:
  - id: openwiki-source-27968b0140d9f4dbf73030e5
    resource: repo://app/config.py
  - id: openwiki-source-fcfa7a2f6773406c3c537551
    resource: repo://app/models/__init__.py
  - id: openwiki-source-dd4e9388d1ad0a8dafd32128
    resource: repo://app/services/parser.py
  - id: openwiki-source-08628abdfe83c50c2702a735
    resource: repo://app/services/service.py
generated: { by: "omp", at: "2026-11-25T04:51:17.394Z" }
---

# Regex transaction parsing and field mapping

`app/services/parser.py` is the only component that knows what a transaction looks like. It takes a body string (produced by the extraction contract described in `/openwiki/systems/email-body-extraction.md`), applies the configured patterns in order, and returns a `TransactionDetails` dataclass.

## Pattern configuration and compilation

`build_transaction_patterns(config)` in `app/config.py` normalises `config["transaction_patterns"]` — a dict or a list — and, when the key is absent entirely, falls back to a built-in `DEFAULT_TRANSACTION_PATTERNS` list containing a single `sbi_card` pattern. Each entry becomes a dictionary with `name`, the `compiled` regex, `field_mapping`, `defaults`, `firefly_mapping` and `firefly`.

Two details are easy to miss:

* `flags` accepts a string, a list of strings, or integers, resolved through `getattr(re, name.upper())`. An unknown flag name raises `ValueError`, so a typo in a rule's flags fails every message for that rule rather than silently ignoring it.
* Entries without a `regex` are dropped silently (`continue`), so a malformed rule degrades to "no patterns" instead of an error at parse time.

The worker builds patterns per source: for database rules it passes `[{"name": rule_name, "regex": rule.regex}]` (no flags, no field mapping), while `config.toml` sources can carry `flags` and `field_mapping`. That is why a `config.toml` pattern can use case-insensitive matching but a dashboard-authored rule cannot — it relies on inline `(?i)` if it needs it.

## Matching and field extraction

`extract_transaction(source, config)` iterates the compiled patterns and applies `re.search` (not `match`), so the pattern can start anywhere in the body. The first pattern whose **amount group** yields a value wins; a pattern that matches but has no amount is skipped and the next pattern is tried.

Group names are resolved through `field_mapping`, with these defaults:

| Field | Default group | Override key | Fallback |
| --- | --- | --- | --- |
| amount | `amount` | `field_mapping.amount` | required — pattern skipped when absent |
| merchant | `merchant` | `field_mapping.merchant` | `""` |
| description | `description` | `field_mapping.description` | merchant value |
| card_last4 | `card_last4` | `field_mapping.card_last4` | `None` |
| transaction_date | `date` | `field_mapping.transaction_date` | `""` |
| reference_no | `reference_no` | `field_mapping.reference_no` | `None` |
| channel | `channel` | `field_mapping.channel` | `""` |
| currency | `currency` | `field_mapping.currency` | `"INR"` |
| vpa | `vpa` | `field_mapping.vpa` | `None` |

`_get_match_group()` swallows `IndexError`, so a mapping that points at a non-existent group behaves like an absent one instead of raising.

Normalisation applied on the way out:

* **Amount.** Commas are stripped and `float()` applied. A non-numeric capture (for example a currency symbol captured by mistake) raises `ValueError`, which propagates as a parser failure for that message — it is a hard error, not a skip.
* **Currency.** `currency = "INR" if currency_value in {"Rs.", "₹"} else "INR"` — both branches return the same value, so every parsed transaction is INR regardless of what the pattern captured. Multi-currency support would start here.
* **Date.** `_normalize_date()` accepts `%d-%m-%y` and `%d-%m-%Y` and returns `YYYY-MM-DD`; anything else is returned unchanged. So `26-06-26` becomes `2026-06-26`, while `2026-06-26` or `June 26` pass through untouched.
* **Description.** Falls back to the merchant when the description group is empty or unmapped.

`defaults` is read into the pattern dictionary but never consulted by `extract_transaction()` — a declared default has no effect on the produced details.

## Firefly pointer on the dataclass

`TransactionDetails.firefly` is filled from `pattern["firefly_mapping"]` (falling back to `pattern["firefly"]`), which `_coerce_firefly_mapping()` derives from `firefly_mapping`, then `firefly`, then the legacy `source_field`/`destination_field`/`source_value`/`destination_value` keys. That dict is what `_build_firefly_payload()` later uses for `{placeholder}` substitution — see `/openwiki/systems/firefly-posting.md`.

`transaction_type` exists on the dataclass and in `as_dict()`, but nothing in the parser sets it: the wizard's transaction type never reaches the dataclass, so Firefly payloads default to `withdrawal` unless a mapping injects the field. A credit alert therefore needs an explicit `type` mapping to be imported correctly.

## Group capture for mappings

`extract_transaction_details(source, config)` wraps `extract_transaction()` and then re-runs the pattern search to attach `groups` (positional, without the full match) and `groupdict` (named) to the returned dictionary. Those two keys are what the `regex_group` mapping resolver reads, and they are why the wizard's group tiles and map rows work without a second parse.

Re-running the search means the body is extracted twice per message; for large HTML statements that is measurable but not pathological.

## Timezone conversion

`convert_to_timezone(value, tz_name="Asia/Kolkata")` is used by the worker when logging message dates and by callers that need a local timestamp. Naive datetimes are assumed UTC, the target zone is resolved with `zoneinfo`, and an unknown zone falls back to UTC instead of raising. Unknown-zone resilience matters because the zone database comes from the `tzdata` package in slim containers.

## What the tests cover

`tests/test_parser.py` describes the intended behaviour (SBI card parsing, HDFC VPA parsing, comma-separated amounts, timezone conversion, Firefly payload shape, processed-tag handling) but no longer imports after the `app/` refactor. The executable coverage for parsing today is `tests/test_email_body.py::ParserStillMatchesTests`, which asserts amount, currency, merchant, card, date, reference and the `amount` groupdict entry for a synthetic SBI alert.
