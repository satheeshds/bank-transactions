---
type: operations
title: Tests, logging and diagnosing failed parses
description: How to verify a change and debug a bad import in Mail2Firefly — which unit tests exist and what they pin, the log-level environment variable and per-module loggers, the sync log versus transaction log, and the Failed Parse detail view that renders the stored parser input.
tags: [testing, diagnostics, logging, troubleshooting, failed-parses]
verified:
  - by: openwiki/0.9.0
    at: 2026-11-25T04:51:17.394Z
sources:
  - id: openwiki-source-ea70eb6c045047448e446296
    resource: repo://.gitignore
  - id: openwiki-source-764ab08c62ebae565249447e
    resource: repo://app/api/v1/endpoints/logs.py
  - id: openwiki-source-c78a685ff399d80e0ef6e6b9
    resource: repo://app/api/v1/endpoints/regex_preview.py
  - id: openwiki-source-20533e4b5cae7e92f027e0af
    resource: repo://app/api/v1/endpoints/transactions.py
  - id: openwiki-source-9635a37a0238c8e9633cf346
    resource: repo://app/db/session.py
  - id: openwiki-source-21c0a295e6c6f5529dc70d5f
    resource: repo://app/main.py
  - id: openwiki-source-d85e29b90d810449d653534a
    resource: repo://app/services/firefly_builder.py
  - id: openwiki-source-cafc76c8a8dfb7bafb137d8a
    resource: repo://app/services/imap.py
  - id: openwiki-source-dd4e9388d1ad0a8dafd32128
    resource: repo://app/services/parser.py
  - id: openwiki-source-08628abdfe83c50c2702a735
    resource: repo://app/services/service.py
  - id: openwiki-source-ed31fdd907f93645f93ecd02
    resource: repo://frontend/src/views/FailedParseDetailView.vue
  - id: openwiki-source-7b05dab96e231da3a0584fc2
    resource: repo://tests/test_email_body.py
  - id: openwiki-source-8bb0b8f087c8e236af369473
    resource: repo://tests/test_parser.py
generated: { by: "omp", at: "2026-11-25T04:51:17.394Z" }
---

# Tests, logging and diagnosing failed parses

## Test suites

Two `unittest` modules live under `tests/`, with `tests/conftest.py` only inserting the repository root on `sys.path` so `app.*` imports resolve.

`tests/test_email_body.py` is the suite that currently runs. It is stdlib-only (no FastAPI, no IMAP, no database) and pins the email body contract:

* `StripHtmlTests` — markup removal, `<style>`/`<script>` removal, empty input;
* `ExtractTextFromMessageTests` — a synthetic `multipart/alternative` message whose plain part is the "please use an HTML enabled email client" notice and whose HTML part holds the transaction, asserting the parsed text contains both and no literal `<p>`;
* `CoerceTextContentTests` — plain text passthrough, HTML document stripping, raw MIME detection;
* `BodyTextFromMessageTests` — the regression that motivated the module: the HTML content must be present even when the plain part is only boilerplate, and `body_text_from_message(msg)` must equal the parser's body for the equivalent MIME message;
* `ParserStillMatchesTests` — end-to-end assertion that `extract_transaction_details()` on that fake message yields amount `78.0`, merchant `SUBEESHW`, card `4465`, date `2026-06-26`, reference `309259409044`.

Run it with:

```bash
uv run python -m unittest tests.test_email_body -v
# or: uv run python -m pytest tests/test_email_body.py -q
```

`tests/test_parser.py` predates the `app/` refactor and no longer imports: it asks for `config`, `imap_client` and `main`, and it reads a `sample-data/` directory that does not exist in the repository (and is git-ignored). It is currently dead weight — useful as a description of intended behaviour (SBI/HDFC sample emails, timezone conversion, Firefly payload shape, processed-tag behaviour) but not as an executable gate. Repointing its imports at `app.config`, `app.services.imap`, `app.services.parser` and `app.services.firefly_builder` would restore the coverage.

## Log levels

`MAIL2FIREFLY_LOG_LEVEL` (default `INFO`) drives both the `dictConfig` in `app/main.py` and the parser module logger in `app/services/parser.py`. Setting it to `DEBUG` turns on:

* parser traces from `extract_transaction()` — the extracted body text, every compiled pattern, each attempted match, and the captured groups/groupdict;
* IMAP query construction from `build_query()` — the resolved condition list and the exact IMAP search string;
* worker progress from `TransactionImportService.log()` for message fetches, parse results and posted payloads.

The variable is read at import time, so a restart is required. `docker-compose.yml` sets it to `debug` for the `web` service.

## Two logs, two purposes

| Table | Written by | Use |
| --- | --- | --- |
| `sync_logs` | `TransactionImportService.log()` via `log_sync_message()` | chronological narrative of a run: fetch counts, per-message decisions, Firefly responses, exceptions with tracebacks |
| `transactions` | `log_transaction()` | one row per processed message outcome, with `status` (`pending` on posted imports, `error` on failures), `error_message`, `rule_name`, `email_subject`, `reference_no`, `firefly_payload` and `raw_email` |

`GET /api/v1/logs?limit=N` returns `sync_logs` in chronological order (the newest `limit` rows, reversed) as `{"logs": [...]}`. `GET /api/v1/transactions?limit=N&status=error` loads the newest `limit` rows and then filters by status in Python, so `status=error` with a small `limit` can miss older failures — raise `limit` when hunting for them. `GET /api/v1/transactions/{id}` returns a single row as `{"transaction": {...}}` and `{"transaction": null}` when absent.

## Diagnosing a failed parse

1. **Open the Failed Parse detail view.** `FailedParseDetailView.vue` fetches `/api/transactions/{id}` (through the legacy route alias) and renders `raw_email`, `firefly_payload` and `error_message`. `raw_email` is stored by the worker as `body_text_from_message(message)` — the exact string the regex was applied to — so what you read is what the parser saw, including the HTML part of a bank alert.
2. **Check the error class.** `Parser exception: ...` means `extract_transaction_details()` raised (usually `ValueError: Could not find a supported transaction pattern in the email`); `No matching transaction pattern` means the exception was swallowed upstream and `details` stayed empty. Both are logged with `status='error'` and leave the message untagged, so it will be retried on the next run.
3. **Reproduce the regex without email.** Take the stored body and post it to `/api/v1/regex_preview` with the rule regex — it returns positional groups, named groups and `groupindex`, or `{"error": "compile_error: ..."}` / `{"error": "timeout"}` when the pattern is invalid or takes longer than 0.5 s.
4. **Check the rule's group mapping.** A pattern that matches but whose `amount` group is missing or unmapped is treated as "no match" for that pattern and the next pattern is tried. The wizard's group tiles and the `field_mapping` stored with the rule are the quickest cross-check.
5. **Confirm the fetch conditions.** If the email never appears in `sync_logs`, the failure is upstream: the IMAP query (from rules, plus `UNKEYWORD` on the processed tag) returned nothing, or the message was already tagged.

## Behavioural traps worth remembering

* `raw_email` used to store raw HTML (`html or text`); it now stores the parsed body, so old rows and new rows are not directly comparable. The detail view sanitises and renders either.
* The Failed Parse view sanitises HTML with a `DOMParser` pass that strips `script`/`style`/`iframe`/`form`/`input`/`button`, removes `on*` attributes and `javascript:` URLs before injecting with `v-html` — safe for the plain-text bodies stored today, and still the correct guard for legacy rows.
* A run that fails after posting to Firefly but before tagging leaves the message retryable. Nothing in this codebase deduplicates on import: the payload sets `error_if_duplicate_hash: false`, so Firefly's own duplicate-hash rule (disabled) will not reject the retry either — the only guard is the processed keyword flag.
