---
type: system
title: IMAP ingestion and query building
description: How Mail2Firefly connects to mailboxes, translates rule conditions into IMAP search strings (including NOT and AND/OR connectors), de-duplicates fetched UIDs, and uses a keyword tag to avoid re-importing processed messages.
tags: [imap, ingestion, query, processed-tag, conditions]
verified:
  - by: openwiki/0.9.0
    at: 2026-11-25T04:51:17.394Z
sources:
  - id: openwiki-source-833fc642bfe0c1d5bb06b763
    resource: repo://app/api/v1/endpoints/mailboxes.py
  - id: openwiki-source-cafc76c8a8dfb7bafb137d8a
    resource: repo://app/services/imap.py
  - id: openwiki-source-08628abdfe83c50c2702a735
    resource: repo://app/services/service.py
generated: { by: "omp", at: "2026-11-25T04:51:17.394Z" }
---

# IMAP ingestion and query building

All IMAP work goes through `app/services/imap.py`, which is a thin layer over `imap_tools`. The module imports `AND`, `NOT` and `MailBox` inside a `try/except ImportError`, leaving them `None` when the dependency is missing, so the API can import cleanly in a minimal environment while every worker path raises `RuntimeError("imap_tools is not installed; ...")` instead of an `AttributeError`.

## Connecting

`get_mailbox_client(config)` builds `MailBox(host).login(username, password)` — no port, encryption or timeout options are passed, so the defaults supplied by `imap_tools` apply and the stored `port`/`encryption` columns are used only for connectivity probes in the API layer. The worker uses the result as a context manager (`with get_mailbox_client(mailbox_row) as mailbox:`), which logs in on entry and logs out on exit.

Mailbox rows come from the `mailboxes` table; the worker logs the row with the password removed before use. When `processed_tag` is empty in the database the worker falls back to `config.toml`'s `mailbox.processed_tag` and finally to the literal `"processed"`.

## Condition shapes

`build_query(query_filter, processed_tag=None)` accepts two shapes:

**Legacy dict** (still used by the CLI `config.toml` path). Everything except `name` and `processed_tag` is passed as `AND(**kwargs)`, and the processed tag becomes `AND(..., no_keyword=tag)`.

**List of conditions** (what the rules table stores, and what the sample endpoint sends). Each entry may hold `field`, `operator`, `value`, `connector` (`"AND"`/`"OR"`, default `"AND"`) and the boolean `not`. Fields map to raw IMAP keywords:

| Field | Emitted search key |
| --- | --- |
| `from`, `sender` | `FROM "value"` |
| `to`, `recipient` | `TO "value"` |
| `subject` | `SUBJECT "value"` |
| `text`, `body` | `TEXT "value"` |
| `date`, `sent_date` with operator `>=` | `SENTSINCE "DD-Mon-YYYY"` |
| `date`, `sent_date` with operator `<` | `SENTBEFORE "DD-Mon-YYYY"` |
| anything else | no clause (condition ignored) |

Dates are parsed from `date` objects, ISO strings, or one of `%Y-%m-%d`, `%d-%m-%Y`, `%d/%m/%Y`, `%m/%d/%Y`; an unparseable date drops the condition rather than failing the query. `_format_imap_date()` emits the IMAP `D-Mon-YYYY` form (`06-Feb-2026`).

The conditions are then folded left to right: a condition's `connector` describes how it joins to what has been accumulated so far, so `{from: a, connector: AND}` + `{subject: b, connector: OR}` becomes `FROM "a" OR SUBJECT "b"`. `not: true` prefixes `NOT `. The processed-tag clause is appended last (`UNKEYWORD "tag"`), the whole expression is wrapped in parentheses, and the function returns the string, or `{}` when nothing at all was accumulated.

Note that `operator` is ignored for `from`/`to`/`subject`/`text`: the wizard hard-codes "Equals" for email fields and "Contains" for subject/text, and IMAP itself only supports substring matching for these headers. `condition_mode` from the wizard is likewise unused server-side — the per-condition `connector` is what matters.

## From query string to fetch call

`build_imap_query()` in `app/services/service.py` adapts whatever `build_query()` returned into something `mailbox.fetch()` accepts: a dict containing `criteria` is unwrapped, a list of dicts is OR-ed through `AND(...)`/`OR(...)` helpers, and a plain dict is wrapped in `A(**query)`. Anything that fails conversion is passed through unchanged, which keeps the legacy path working.

`fetch_messages(mailbox, fetch_query, reverse=True, limit=15)` then iterates `mailbox.fetch(...)`, dropping messages whose UID was already seen in this call. `reverse` and `limit` come from the `fetch` block of `config.toml` (`reverse` default `true`, `limit` default `15`), so a rule never imports an unbounded backlog.

## The processed tag is the dedupe mechanism

Two helpers, both no-ops when no tag is configured:

* `is_message_processed(message, tag)` reads `message.flags`, verifies it is a list/tuple/set, and compares case-insensitively after stripping; any match means "skip".
* `mark_message_processed(mailbox, message, tag)` requires a non-empty `message.uid` and calls `mailbox.flag(uid, tag, True)`, logging rather than raising on failure — a failed flag operation is recoverable (the message will be re-processed) while a raise would abort the run.

`_process_message()` checks `is_message_processed()` first, but only when `dev.enable_processed_tagging` is true (default `true`; setting it false in `config.toml` allows re-processing during experiments). The tag is applied only after a successful Firefly post, so parsing failures and Firefly errors leave the message untagged and therefore retryable.

Three consequences follow:

1. **The database is not the dedupe source.** Deleting a transaction row from the dashboard does not cause a re-import; removing the keyword in the mail client does.
2. **Sample fetching respects it.** The `POST /mailboxes/{id}/sample` endpoint builds its query through the same `build_query(..., processed_tag=...)`, which is why an operator can fail to get a sample for a message that was already imported — `UNKEYWORD` excludes it.
3. **Tag vocabulary is per mailbox.** Different mailboxes may use different keywords; the fallback chain (DB → `config.toml` → `"processed"`) is resolved per mailbox at fetch time and stored on the temporary `SourceDefinition` used for that rule.

## Failure surface

`_run_db_rules()` wraps each rule in `try/except`: a login or fetch failure for one mailbox is logged and the loop continues with the next rule, so one broken mailbox does not stop the worker. If no database rule exists at all, the worker logs "No DB parsing rules found; skipping config-based sources." and stops — the config-file sources are deliberately not used as a runtime fallback.
