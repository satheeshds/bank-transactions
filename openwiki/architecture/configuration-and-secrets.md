---
type: architecture
title: Configuration, credentials and runtime overrides
description: Every configuration surface of Mail2Firefly — config.toml defaults, the MySQL settings table used for Firefly connection values and custom keys, mailbox credentials, database and log-level environment variables — plus which surfaces still fall back to static config and which do not.
tags: [configuration, secrets, settings, environment, firefly, database]
verified:
  - by: openwiki/0.9.0
    at: 2026-11-25T04:51:17.394Z
sources:
  - id: openwiki-source-afe0d08c945bf37d271aceb6
    resource: repo://app/api/v1/endpoints/firefly.py
  - id: openwiki-source-833fc642bfe0c1d5bb06b763
    resource: repo://app/api/v1/endpoints/mailboxes.py
  - id: openwiki-source-98e0da3a188cc261aae2099b
    resource: repo://app/api/v1/endpoints/settings.py
  - id: openwiki-source-27968b0140d9f4dbf73030e5
    resource: repo://app/config.py
  - id: openwiki-source-9635a37a0238c8e9633cf346
    resource: repo://app/db/session.py
  - id: openwiki-source-21c0a295e6c6f5529dc70d5f
    resource: repo://app/main.py
  - id: openwiki-source-dd4e9388d1ad0a8dafd32128
    resource: repo://app/services/parser.py
  - id: openwiki-source-b79fbbd921df689b4bbdc82f
    resource: repo://docker-compose.yml
  - id: openwiki-source-23775c3de52f3ab95a13cb8b
    resource: repo://README.md
generated: { by: "omp", at: "2026-11-25T04:51:17.394Z" }
---

# Configuration, credentials and runtime overrides

Mail2Firefly has three configuration layers: a static `config.toml`, a `settings` table in MySQL, and process environment variables. They are not interchangeable — the dashboard and the sync worker read different layers for different concerns, and the static file has been demoted for some values but is still authoritative for others.

## Where each value comes from

| Concern | Source of truth | Fallback |
| --- | --- | --- |
| Mailboxes (host, credentials, processed tag) | `mailboxes` table, managed via the dashboard | none at runtime |
| Parsing rules (conditions, regex, mappings) | `parsing_rules` table, managed via the wizard | none at runtime |
| Firefly III base URL, token, timeout | `settings` rows `firefly.base_url`, `firefly.token`, `firefly.timeout` | empty URL/token, timeout 15 |
| Firefly custom keys for mapping | `settings` row `firefly.custom_keys` (JSON) | `{}` |
| Database connection | env vars `DB_HOST`, `DB_PORT`, `WEB_DB_USER`, `WEB_DB_PASSWORD`, `WEB_DB_NAME` | `127.0.0.1:3306`, empty user/password/db |
| Log verbosity | env var `MAIL2FIREFLY_LOG_LEVEL` | `INFO` |
| CLI worker defaults (`[mailbox]`, `[fetch]`, `[dev]`) | `config.toml` | — |

## Static configuration (`config.toml`)

`app/config.py` resolves `CONFIG_PATH` to `config.toml` next to the repository root and `load_config()` reads it with `tomllib`. The example file documents the shape the CLI worker expects: a `[mailbox]` block with IMAP host/username/password and `processed_tag`, one `[[mailbox.sources]]` per statement with an embedded `[mailbox.sources.firefly]` block, a `query` list and one or more `transaction_patterns`, a `[fetch]` block (`reverse`, `limit`) and a `[dev]` block with `enable_processed_tagging`.

`load_config()` normalises the historical `mailbox.sources` / `mailbox.statements` spelling so both keys resolve to the same list, and `build_source_definitions()` turns the file into `SourceDefinition` dictionaries (name, mailbox, query list, patterns, firefly block, processed tag). The processed tag is resolved by inheritance: source → mailbox → top-level config.

The web application does **not** read mailboxes or rules from this file. `mailboxes` endpoints require a row in the database and return `404` otherwise, and the worker builds a temporary source model per database rule. `config.toml` remains the entry point for `cli/main.py` only.

## Firefly connection stored in the database

`build_firefly_config()` prefers the `settings` table: it reads `firefly.base_url`, `firefly.token` and `firefly.timeout`, coerces the timeout string to `int` (falling back to `15` when unparseable or absent), and wraps the lookup in a `try/except` so a database failure degrades to an empty base URL rather than crashing the import.

The dashboard writes those rows through `PUT /api/v1/firefly`, which also persists `firefly.custom_keys` as a JSON string. `GET /api/v1/firefly` reassembles the same four values for the Settings page and for the rule wizard, which fetches `custom_keys` to populate the "Custom Key" mapping source.

Generic settings access goes through `/api/v1/settings/{key}` and `POST /api/v1/settings`. The GET handler masks anything whose key ends in `api_key` or `token`: it returns `{"value": null, "configured": true|false}` instead of the secret, so the dashboard can show "configured" without ever rendering the token. Any other key is returned verbatim.

## Mailbox credentials

Mailbox passwords live in the `mailboxes` table and are read by the IMAP service at sync time and by the sample endpoints when the wizard requests an email. There is no encrypted-at-rest handling in the code: `list_mailboxes()` and `get_mailbox_by_id()` return the stored password, so any read path that exposes a mailbox row exposes a credential. Treat the dashboard API and the database as trusted-tier surfaces, and keep the container network private.

## Environment variables

`app/db/session.py` is the only place that reads database connection settings, and the application supports MySQL/MariaDB only — `pymysql` is imported lazily and a missing driver raises `RuntimeError: pymysql is required for MySQL/MariaDB connections`.

`MAIL2FIREFLY_LOG_LEVEL` is read in two places: `app/main.py` configures a `dictConfig` with a console handler, a `mail2firefly` logger and a dedicated `app.services.parser` logger (so parser debug output can be raised independently), while `app/services/parser.py` applies the same level to its own logger at import time. `docker-compose.yml` sets it to `debug` for the `web` service.

## Operational notes

* Credentials for Firefly III itself belong in `.db.env` / `.env` files consumed by compose, not in the application config.
* Changing the log level requires a container restart, because both readers evaluate the variable at import time.
* Because the Firefly connection is read per call (`build_firefly_config()` hits the database each time), a Settings-page change takes effect on the next sync without restarting the worker.
