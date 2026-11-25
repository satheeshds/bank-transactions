---
type: operations
title: Deployment, containers and scheduling
description: How Mail2Firefly is packaged and run — a two-stage Dockerfile that builds the Vue bundle and installs the Python app, a compose topology of MariaDB, Firefly III, the web service and an fcron scheduler sidecar, and the static crontab that triggers sync and database backups.
tags: [deployment, docker, compose, scheduler, cron, backup, mariadb]
verified:
  - by: openwiki/0.9.0
    at: 2026-11-25T04:51:17.394Z
sources:
  - id: openwiki-source-b79fbbd921df689b4bbdc82f
    resource: repo://docker-compose.yml
  - id: openwiki-source-dec44190edc3a689166bf3e2
    resource: repo://docker/db-init/init.sh
  - id: openwiki-source-bb1ebe868e35e9e500714501
    resource: repo://Dockerfile
  - id: openwiki-source-c1bd8bd4834d4dc70a8b85cc
    resource: repo://frontend/vite.config.js
  - id: openwiki-source-32cfc41ef162f60f58bc8cb7
    resource: repo://scheduler-worker/backup.sh
  - id: openwiki-source-4a49caa583cf0a4a10128358
    resource: repo://scheduler-worker/crontab
  - id: openwiki-source-f6e655faa4c5da931e74a2a7
    resource: repo://scheduler-worker/Dockerfile
  - id: openwiki-source-b92fbaa54c1e17b223887dd7
    resource: repo://scheduler-worker/entrypoint.sh
generated: { by: "omp", at: "2026-11-25T04:51:17.394Z" }
---

# Deployment, containers and scheduling

The repository ships two images: the application image (FastAPI + prebuilt frontend) and a small scheduler/backup image built from `scheduler-worker/`. `docker-compose.yml` wires them together with MariaDB, a Firefly III core container and a Firefly AI categorizer that this codebase does not use directly.

## Application image

`Dockerfile` is a two-stage build:

1. **`node-builder`** (`node:18-alpine`): copies `frontend/`, runs `npm ci --legacy-peer-deps` (falling back to `npm ci`) with a BuildKit npm cache, then `npm run build`. Vite writes the bundle to `../static/dist`, i.e. `/src/static/dist` inside that stage.
2. **Runtime** (`python:3.12-slim`): installs build tooling, copies `requirements.txt` and installs with a pip BuildKit cache, then copies only `app/`, `cli/`, `web.py` and `config.toml` plus the built `static/dist` from the first stage. The container command is `uvicorn web:app --host 0.0.0.0 --port 8000`.

Consequences worth remembering:

* `config.toml` must exist at build time (it is copied, and it is git-ignored — the image build therefore needs the operator's local file or a mounted secret), while mailboxes and rules come from the database at runtime.
* There is no Node runtime in the final image; a UI change requires rebuilding the image.
* `/app/static/dist` is the directory `app/main.py` resolves through `_get_dist_dir()`, so the copy target must not be renamed.

## Compose topology

| Service | Image / build | Role |
| --- | --- | --- |
| `app` | `fireflyiii/core:latest` | Firefly III itself, exposed on host port 80, configured from `.env` |
| `db` | `mariadb:lts` | shared database server; initialised by `docker/db-init/init.sh` |
| `categorizer` | `ghcr.io/ejagombar/fireflyiii-ai-categorizer` | optional Firefly-side categoriser |
| `scheduler` | built from `scheduler-worker/` | fcron sidecar: cron triggers plus rclone database backups |
| `web` | built from the repository root | Mail2Firefly API + dashboard on host port 8000 |

The `web` service reads `.db.env` and sets `TZ=Asia/Kolkata`, `DB_CONNECTION=mysql`, `DB_HOST=db`, `DB_PORT=3306` and `MAIL2FIREFLY_LOG_LEVEL=debug`, and depends on `db`. The `scheduler` service additionally mounts `./scheduler-worker/crontab` to `/config/crontab` and `./rclone-config` to `/root/.config/rclone`, and receives `RCLONE_REMOTE`, `BACKUP_FOLDER` and `BACKUP_AGE` for the backup job.

`docker/db-init/init.sh` runs as a MariaDB init script. It requires `MYSQL_ROOT_PASSWORD`, derives database name and user from `WEB_DB_NAME`, `WEB_DB_USER` and `WEB_DB_PASSWORD` (defaults: `bank_transactions`, `bank_transactions_user`, `ReplaceWithStrongPassword`), writes the SQL to a temporary file to survive CRLF line endings on Windows hosts, and executes it through `mysql` or `mariadb`, warning (without failing) when neither client exists.

## Scheduler sidecar

The image is based on `satheeshds/fcron-container` and adds `postgresql-client`, `sqlite3`, `rclone`, `gzip`, `mariadb-client` and `curl`. Its entrypoint validates required environment variables per database type, verifies the rclone remote and bucket, and then `exec`s the base image entrypoint that starts fcron.

`entrypoint.sh` does **not** write cron entries. The schedule is the mounted `scheduler-worker/crontab`, an fcrontab with two active jobs:

```
%daily * * run-logged sh /app/backup.sh
0 7-21/3 * * * run-logged sh -c 'curl -s -X POST http://web:8000/api/v1/sync || ...'
```

So sync runs at minute 0 of hours 07 through 21 every third hour — roughly eight runs a day during business hours, not the "3 hours around the clock" a cursory read suggests. A commented example also shows the Firefly-side `curl http://app:8080/api/v1/cron/$STATIC_CRON_TOKEN` job, which belongs to Firefly III rather than to this application.

The crontab file preloads `DB_*`, `WEB_DB_*`, `RCLONE_*`, `BACKUP_*` and `STATIC_CRON_TOKEN` values, so the same variables the sidecar uses for backups are visible to cron jobs without a `.env` re-read. Despite the README's phrasing, nothing in the entrypoint reads a recurrence from the API and rewrites the crontab; changing the schedule means editing the mounted file and restarting the container.

`backup.sh` dumps **two** databases in mysql mode — the Firefly database (`DB_DATABASE`) and the Mail2Firefly database (`WEB_DB_NAME`) — gzips both, uploads them with `rclone copy`, removes the local copies, then prunes remote files older than `BACKUP_AGE` days. `set -e` plus explicit exit checks mean a failed dump or upload fails the job, which is what makes the fcrontab's `erroronlymail(true)` produce an alert email.

## Local development versus container deployment

For UI work the documented loop is `npm run dev` on port 5173 against a separately started `uv run uvicorn web:app --reload` on port 8000, relying on the Vite proxy. For backend-only work `uvicorn` alone is enough because a missing `static/dist/index.html` yields the 503 instruction page. Production exposure is the `web` container on port 8000, with the SPA served from the same origin so no CORS configuration is needed.
