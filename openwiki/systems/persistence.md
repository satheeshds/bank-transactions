---
type: "Reference"
title: "Persistence: MySQL schema and data access"
openwiki_generated: true
verified:
  - by: openwiki/0.9.0
    at: 2026-11-25T04:51:17.394Z
sources:
  - id: openwiki-source-9635a37a0238c8e9633cf346
    resource: repo://app/db/session.py
  - id: openwiki-source-08628abdfe83c50c2702a735
    resource: repo://app/services/service.py
generated: { by: "omp", at: "2026-11-25T04:51:17.394Z" }
---


# Persistence: MySQL schema and data access

Every persistent fact in Mail2Firefly lives in MySQL/MariaDB. There is no ORM, no migration tool and no fallback store: `app/db/session.py` opens a `pymysql` connection per operation, and `init_db()` creates the five tables with `CREATE TABLE IF NOT EXISTS` on FastAPI startup (and again before a manual sync run).

## Connection wrapper

`get_db_connection()` imports `pymysql` and `DictCursor` lazily, so importing the module does not require the driver, and raises `RuntimeError("pymysql is required for MySQL/MariaDB connections")` when it is absent. Connection parameters come from `DB_HOST` (default `127.0.0.1`), `DB_PORT` (default `3306`), `WEB_DB_USER`, `WEB_DB_PASSWORD` and `WEB_DB_NAME`; `autocommit` is off.

Two thin wrappers make the rest of the code portable:

* `_WrappedCursor` rewrites `?` placeholders to `%s` before delegating, so older SQL written for SQLite keeps working while new code can use `%s` directly.
* `_ConnWrapper` implements the context-manager protocol: commit on clean exit, rollback on exception, always close. That is why so much of the code reads `with get_db_connection() as conn:` and then calls `conn.commit()` explicitly — the explicit commit is redundant but harmless, and a missing one inside the `with` block still commits.

Every helper returns plain dictionaries (because of `DictCursor`), which is what lets the FastAPI handlers return rows without serialisation code.

## Tables

| Table | Purpose | Behaviourally relevant columns |
| --- | --- | --- |
| `transactions` | one row per processed message outcome | `status` (`pending`/`synced`/`error`), `error_message`, `rule_name`, `rule_id`, `source_name`, `email_subject`, `reference_no`, `raw_email` (parser-visible body), `firefly_payload` (stringified payload) |
| `sync_runs` | one row per sync invocation | `start_time`, `end_time`, `status` (`running` then `success`/`failed`), `unprocessed_emails`, `parsed_count`, `error_count` |
| `sync_logs` | narrative per run | `run_id`, `level`, `message` |
| `mailboxes` | IMAP endpoints | `name` (unique, matched against a rule's `source_name`), `host`, `port`, `username`, `password`, `encryption`, `processed_tag` |
| `settings` | key/value overrides | `key` (VARCHAR primary key), `value` TEXT |
| `parsing_rules` | dashboard-authored rules | `source_name`, `rule_name`, `regex`, `transaction_type`, `conditions_json`, `mappings_json`, `condition_mode` |

Notes that matter when reading the code:

* Timestamps are stored as ISO strings in `TEXT` columns, and the statistics query relies on MySQL's `DATE(timestamp)` function — so "today" is computed in the database's timezone, not the container's `TZ` alone.
* `amount` is `DOUBLE`, everything else that looks textual is `TEXT`. There are no foreign keys, so deleting a mailbox leaves its rules dangling; the worker then logs "No mailbox found for rule …" and skips that rule.
* `raw_email` is `LONGTEXT`: it holds whatever `body_text_from_message()` produced, which for long statement emails can be sizeable.
* `parsing_rules.conditions_json` and `mappings_json` are JSON-encoded text written by the rules API; `condition_mode` is stored but unused when building IMAP queries (per-condition `connector` wins).

## Mailbox helpers

`list_mailboxes()` deliberately omits `password` and is used by the dashboard list, the status probe and the worker's name→mailbox lookup. `get_mailbox_by_id()` includes `password` and is reserved for paths that must log in: the sample endpoints and the worker. Callers that log a mailbox row (the worker does) pop `password` first — the API's mailbox list is safe because the column is never selected.

`add_mailbox()` inserts a row and returns `lastrowid`; `update_mailbox()` builds a dynamic `SET` clause from the non-`None` arguments (so passing `None` means "leave unchanged", and there is no way to clear a column to `NULL` through it); `delete_mailbox()` simply deletes.

## Settings helpers

`get_setting(key)` selects a single row and returns `None` when absent. `set_setting(key, value)` is a small upsert: `None` deletes the row, any other value uses `REPLACE INTO`. That delete-on-`None` behaviour is what makes clearing the Firefly token in the UI actually remove the setting rather than store an empty string.

## Transaction log and run bookkeeping

`log_transaction(...)` inserts into `transactions` with `datetime.now().isoformat()` and returns the new id. It is called from three places in the worker — parser exception (`status='error'`, message `Parser exception: …`), no matching pattern (`status='error'`), and after a Firefly post (`synced`, `pending` or `error`).

`start_sync_run()` inserts a `running` row, `end_sync_run()` updates it with the final status and counters, and `log_sync_message()` appends to `sync_logs` with the level upper-cased. `get_stats_today()` runs three `DATE(...)` comparisons for parsed/error/run counts plus `get_latest_sync_run()`, and the dashboard shows exactly those numbers.

## Rules

`get_parsing_rules()` selects the scalar columns plus `conditions_json`, `mappings_json` and `condition_mode` ordered by id, and is consumed by the worker (`_run_db_rules`) and by `TransactionImportService.from_config()` for its per-source override. The rules API writes with `?` placeholders (exercising the cursor rewrite) and serialises `conditions`/`mappings` via inline `json.dumps`, parsing them back only for the single-rule `GET`.

## Provisioning

`docker/db-init/init.sh` creates the database and user from `WEB_DB_NAME`, `WEB_DB_USER` and `WEB_DB_PASSWORD` when MariaDB initialises its data directory; the application then creates tables itself. Because both the Firefly database (`DB_DATABASE`) and this one live on the same server, the scheduler's backup script dumps both.
