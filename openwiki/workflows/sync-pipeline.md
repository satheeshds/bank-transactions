---
type: workflow
title: Sync pipeline end to end
description: Traces one sync run of Mail2Firefly from the HTTP trigger or cron sidecar through the lock and sync_runs bookkeeping, per-rule IMAP fetch, parser invocation, Firefly post, processed tagging and transaction logging — including the known gap where rule mappings never reach the payload builder.
tags: [sync, worker, pipeline, lifecycle, tagging, logging]
verified:
  - by: openwiki/0.9.0
    at: 2026-11-25T04:51:17.394Z
sources:
  - id: openwiki-source-7c5b70043cbea8a67ca2b292
    resource: repo://app/api/v1/endpoints/sync.py
  - id: openwiki-source-9635a37a0238c8e9633cf346
    resource: repo://app/db/session.py
  - id: openwiki-source-d85e29b90d810449d653534a
    resource: repo://app/services/firefly_builder.py
  - id: openwiki-source-d9baa31399f68a28b825b26c
    resource: repo://app/services/mapping_resolvers.py
  - id: openwiki-source-08628abdfe83c50c2702a735
    resource: repo://app/services/service.py
  - id: openwiki-source-93c4bf642ecfa683655a01ec
    resource: repo://cli/main.py
  - id: openwiki-source-4c4491a04c0be4df38325cfd
    resource: repo://cli/sync_worker.py
generated: { by: "omp", at: "2026-11-25T04:51:17.394Z" }
---

# Sync pipeline end to end

A sync run is the only path that imports transactions. It always executes inside a single process — a background thread started from the API, or the CLI worker — and iterates database rules one by one.

## Trigger and bookkeeping

`POST /api/v1/sync` → `cli.sync_worker.start_sync_background()`:

1. `_sync_lock.acquire(blocking=False)`; failure means a run is already active, and the endpoint answers `409` with the running `run_id` (`is_sync_running()`/`get_current_run_id()` expose the module-level state that `GET /api/v1/status` reports).
2. `database.init_db()` runs again, so a fresh deployment does not need a manual migration before its first import.
3. `database.start_sync_run()` inserts a `sync_runs` row with status `running` and returns its id.
4. A daemon thread runs `_run_sync_worker(run_id)`, which loads `config.toml` with `load_config()`, builds `TransactionImportService.from_config(config, run_id=run_id)` and calls `run()`.
5. In `finally`: `end_sync_run(run_id, status, parsed_count, error_count)` closes the row, `_current_run_id` is cleared and the lock is released. A `success` status is written even when individual messages failed — failures are counted, not fatal.

`cli/main.py` skips steps 1–3 and runs the service synchronously with `run_id=None`; every `log()` call then writes `sync_logs` rows with a null run id, so CLI runs appear in the dashboard log without a `sync_runs` record.

## Rule iteration

`run()` logs a greeting, reads `database.get_parsing_rules()`, and dispatches to `_run_db_rules(rules)`. When the rules table is empty it logs "No DB parsing rules found; skipping config-based sources." and returns — the `config.toml` sources built by `from_config()` are **not** used at runtime, only their `transaction_patterns` would have been overridden anyway.

`_run_db_rules()` then, per rule:

1. resolves the mailbox by `name == rule.source_name` (falling back to a mailbox whose name is the empty string), else logs `No mailbox found for rule …` and skips;
2. re-reads the mailbox row with credentials, drops `password` before logging it at DEBUG;
3. resolves the processed tag: database value → `config.toml` `mailbox.processed_tag` → `"processed"`;
4. opens the IMAP connection as a context manager and builds the query from `rule.conditions` (a dict is wrapped in a list; an empty list becomes `[{}]`, i.e. "recent messages"), then `build_imap_query()` adapts what `build_query()` produced;
5. fetches with `reverse`/`limit` from the `fetch` config block (defaults `true`/`15`), adding to `unprocessed_emails`;
6. builds a temporary `SourceDefinition` (`_build_temp_source`) carrying the rule name, the rule regex as the single pattern, and the resolved processed tag;
7. processes each message inside its own `try/except`, so one bad message cannot abort the rule.

A failure anywhere in steps 3–6 is caught at the rule level and logged as `Failed to fetch messages for rule '<name>': …`; the next rule still runs.

## Per-message processing

`_process_message(mailbox, message, source, rule)`:

1. **Skip check.** If `dev.enable_processed_tagging` is true (default) and `is_message_processed(message, source.processed_tag)`, log `Skipping already processed message: <subject>` and return without logging a transaction row.
2. **Parse.** `extract_transaction_details(message, config={**config, "transaction_patterns": source.transaction_patterns})` — the message object goes through the shared body extractor, so the body is the plain part plus stripped HTML. Exceptions here log `Parser failed for '<subject>': …` at ERROR, increment `error_count`, and write a `transactions` row with `status='error'`, `error_message="Parser exception: …"` and `raw_email` set to the parser-visible body.
3. **Prepare.** `details.as_dict()` then `_prepare_details_for_firefly(details, rule, source)` attaches `rule_name`, `rule_id` and, if present, the rule's mappings.
4. **Empty-details guard.** `details is None` produces the `No matching transaction pattern` error row. In practice step 2 raises instead of returning empty, so this branch is defensive.
5. **Post.** `_post_to_firefly(...)` builds the payload, posts when a client is configured (marking the message processed on success), and returns `(status, payload, error_msg)` with status `synced`, `pending` (no Firefly client) or `error`.
6. **Log.** One `transactions` row records date, merchant, amount, currency, status, error message, rule metadata, source name, subject, reference number, `raw_email` and `str(payload)`.

Counters: `parsed_count` increments on `synced` and on `pending` (dry run), `error_count` on parser exceptions, no-match and Firefly failures. The run status itself is `success` unless the thread raises — for example when `load_config()` fails because `config.toml` is missing.

## Known gap: mappings do not reach the payload builder

`get_parsing_rules()` returns `mappings_json` as a **string**, and `_prepare_details_for_firefly()` stores whatever it finds under the key `mappings`:

```python
mappings = rule.get('mappings') or rule.get('mappings_json') or None
if mappings:
    out['mappings'] = mappings
```

`_build_firefly_payload()` only applies mappings when `isinstance(mappings, list)`, so a JSON string silently skips `apply_mappings()`. Consequences at sync time:

* rule mapping rows (IMAP fields, Firefly account ids, custom keys beyond the parsed fields) never influence the payload;
* only keys that already exist on the parsed details are forwarded, selected by the Firefly field whitelist;
* `transaction_type` falls back to `withdrawal`, because nothing injects it.

Fixing it means decoding `mappings_json` (and parsing `conditions_json` the same way, which `_run_db_rules` currently tolerates only because a string happens to be wrapped in a list and then ignored by the query builder). Nothing else in the pipeline needs to change.

## Failure isolation summary

| Failure | Effect |
| --- | --- |
| Sync already running | `409`, no new run row |
| `config.toml` unreadable | thread raises, run marked `failed` |
| Mailbox missing / login fails | rule skipped, error log, run continues |
| IMAP query fails | same as above |
| Message parse raises | error row, message left untagged (retried next run) |
| Firefly rejects payload | error row with status text, message left untagged |
| No Firefly configured | `pending` row, message tagged as processed only if tagging is enabled … it is not — see below |

One subtlety in that last row: the `pending` branch does not mark the message processed, so with no Firefly configured every run re-imports the same messages as `pending` rows. That is useful for rule development (the sample keeps matching) and dangerous if a deployment runs for days with a blank token.
