---
type: architecture
title: System overview and runtime topology
description: The runnable surfaces of Mail2Firefly — a FastAPI dashboard that also serves the built Vue 3 SPA, and a background sync worker (in-process thread, CLI, or cron sidecar) that reads rules and mailboxes from MySQL, parses emails and posts transactions to Firefly III.
tags: [architecture, fastapi, vue, worker, mysql, firefly]
verified:
  - by: openwiki/0.9.0
    at: 2026-11-25T04:51:17.394Z
sources:
  - id: openwiki-source-7c5b70043cbea8a67ca2b292
    resource: repo://app/api/v1/endpoints/sync.py
  - id: openwiki-source-21c0a295e6c6f5529dc70d5f
    resource: repo://app/main.py
  - id: openwiki-source-08628abdfe83c50c2702a735
    resource: repo://app/services/service.py
  - id: openwiki-source-4c4491a04c0be4df38325cfd
    resource: repo://cli/sync_worker.py
  - id: openwiki-source-bb1ebe868e35e9e500714501
    resource: repo://Dockerfile
  - id: openwiki-source-9ddd27c88fe184a37617e5ff
    resource: repo://frontend/src/main.js
  - id: openwiki-source-c1bd8bd4834d4dc70a8b85cc
    resource: repo://frontend/vite.config.js
  - id: openwiki-source-bca9dcf3f5166562741a16af
    resource: repo://web.py
generated: { by: "omp", at: "2026-11-25T04:51:17.394Z" }
---

# System overview and runtime topology

Mail2Firefly is one Python package with two kinds of process: a FastAPI application that serves both the JSON API and the compiled Vue single-page app, and a sync worker that does the email→Firefly work. Both talk to the same MySQL/MariaDB database; only the worker talks to IMAP and to Firefly III.

```
                    ┌────────────────────────────┐
  browser ─────────►│ FastAPI (web.py / app.main)│──► MySQL (mailboxes, parsing_rules,
                    │  /api/v1/* + static/dist   │        settings, transactions, sync_*)
                    └───────────┬────────────────┘
                                │ POST /api/v1/sync
                                ▼
                    ┌────────────────────────────┐        ┌─────────────┐
                    │ sync worker (thread/CLI)   │───────►│ IMAP server │
                    │ app.services.service       │        └─────────────┘
                    └───────────┬────────────────┘
                                │ POST /api/v1/transactions
                                ▼
                    ┌────────────────────────────┐
                    │ Firefly III                │
                    └────────────────────────────┘
```

## FastAPI application

`web.py` is a two-line compatibility shim that re-exports `app` from `app/main.py`. `app/main.py` is where the application is assembled:

* logging is configured with `dictConfig` before anything else, honouring `MAIL2FIREFLY_LOG_LEVEL` and adding a dedicated `app.services.parser` logger;
* the React-free Single Page App is served from `static/dist/` — `/assets` is mounted as static files, `/static` is kept as a legacy mount, and `GET /` returns `static/dist/index.html` or a `503` page telling the operator to run `npm install && npm run build`;
* eleven routers are included under `/api/v1` (status, sync, logs, transactions, rules, mailboxes, firefly, regex preview, ai, settings, autocomplete);
* a handful of `/api/*` legacy routes forward to the same handlers so older dashboards keep working;
* `@app.on_event("startup")` calls `database.init_db()`, so the schema is created idempotently on boot and no migration step is required.

`app/api/v1/schemas.py` holds the shared Pydantic request models; each router keeps its own small models where the payload is endpoint-specific.

## Vue 3 single-page app

`frontend/` is a Vite workspace with Vue 3 in hash-history mode: `frontend/src/main.js` registers the router, so URLs look like `/#/dashboard` and no server-side rewrite rules are needed. Routes cover the dashboard, parsing rules (list and wizard), failed parses (list and detail) and settings; the legacy `/mailboxes` and `/firefly-connection` paths simply redirect to `/settings`.

`frontend/vite.config.js` writes the production bundle to `../static/dist` with `emptyOutDir: true`, which is exactly the directory `app/main.py` serves. In development the same config proxies `/api` to `http://127.0.0.1:8000`, so `npm run dev` on port 5173 talks to an independently started uvicorn.

Because the frontend is compiled into `static/dist` and the Python image copies that directory, a production image contains no Node runtime; rebuilding the UI means rebuilding the image (see `/openwiki/operations/deployment-and-scheduling.md`).

## Sync worker

There is no separate worker service: the sync loop is a Python class, `TransactionImportService`, and three entry points drive it.

1. **In-process thread.** `POST /api/v1/sync` calls `cli.sync_worker.start_sync_background()`, which takes a module-level `threading.Lock` (returning `409` with the current run id when a run is already active), inserts a `sync_runs` row, and starts a daemon thread that instantiates the service and calls `run()`.
2. **CLI.** `cli/main.py` loads `config.toml`, builds the service with `TransactionImportService.from_config()` and runs it synchronously — the path used for local experiments and the Docker `config.toml` copy.
3. **Cron sidecar.** The `scheduler-worker` container can call the HTTP endpoint on a schedule; it never imports the Python package.

`from_config()` is where the database becomes authoritative: it builds sources from `config.toml`, then overrides each source's `transaction_patterns` with the rules stored in `parsing_rules` grouped by `source_name`. If the database lookup fails the configured patterns stay in place, which keeps the CLI usable without a populated database.

Firefly connectivity is optional at construction time: `build_firefly_config()` reads the `settings` table and the client is only built when both `base_url` and `token` are non-empty.

## Shared state and boundaries

| Component | Reads | Writes |
| --- | --- | --- |
| Dashboard API | `status`, `transactions`, `sync_runs`, `sync_logs`, `rules`, `mailboxes`, `settings` | `rules`, `mailboxes`, `settings`, `sync_runs` (when starting a run) |
| Sync worker | `parsing_rules`, `mailboxes`, `settings`, `transactions` (dedupe is IMAP-side) | `transactions`, `sync_runs`, `sync_logs` |
| Frontend | everything under `/api/v1` | same |

MySQL is the only shared medium, which is why the API can stay stateless and the worker can be restarted independently. IMAP flags are the second persistence layer: the processed keyword on a message is what prevents a transaction being imported twice, and it lives in the mail server rather than in the database.

## Novelty notes

* The dashboard and the parser share code: `build_transaction_patterns()` and `body_text_from_message()` are used by the worker, and the sample/regex-preview endpoints reuse the same parsing assumptions so that what the wizard previews is what sync will do.
* Firefly III itself is *not* part of this repository. `docker-compose.yml` happens to run a Firefly core image, MariaDB, a Firefly AI categorizer and the scheduler sidecar, but the Mail2Firefly `web` service is the only component built from this codebase.
