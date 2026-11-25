---
type: guide
title: Mail2Firefly wiki quickstart
description: Entry point to the Mail2Firefly wiki — a five-line mental model of the email-to-Firefly importer and a task-routing table that sends readers and coding agents to the page that answers their question.
tags: [quickstart, navigation, orientation]
verified:
  - by: openwiki/0.9.0
    at: 2026-11-25T04:51:17.394Z
sources:
  - id: openwiki-source-833fc642bfe0c1d5bb06b763
    resource: repo://app/api/v1/endpoints/mailboxes.py
  - id: openwiki-source-9635a37a0238c8e9633cf346
    resource: repo://app/db/session.py
  - id: openwiki-source-21c0a295e6c6f5529dc70d5f
    resource: repo://app/main.py
  - id: openwiki-source-a8047a190df69a0969f10e04
    resource: repo://app/services/email_body.py
  - id: openwiki-source-d85e29b90d810449d653534a
    resource: repo://app/services/firefly_builder.py
  - id: openwiki-source-cafc76c8a8dfb7bafb137d8a
    resource: repo://app/services/imap.py
  - id: openwiki-source-dd4e9388d1ad0a8dafd32128
    resource: repo://app/services/parser.py
  - id: openwiki-source-08628abdfe83c50c2702a735
    resource: repo://app/services/service.py
  - id: openwiki-source-bb1ebe868e35e9e500714501
    resource: repo://Dockerfile
  - id: openwiki-source-c1bd8bd4834d4dc70a8b85cc
    resource: repo://frontend/vite.config.js
  - id: openwiki-source-23775c3de52f3ab95a13cb8b
    resource: repo://README.md
generated: { by: "omp", at: "2026-11-25T04:51:17.394Z" }
---

# Mail2Firefly wiki quickstart

Mail2Firefly imports bank alert emails into [Firefly III](https://www.firefly-iii.org/). It is a FastAPI service (which also serves a Vue 3 dashboard) plus a sync worker, both backed by MySQL/MariaDB.

## Mental model in five lines

1. A **mailbox** row stores IMAP credentials and an optional processed-tag keyword.
2. A **parsing rule** row stores IMAP conditions, one regex, and optional Firefly field mappings.
3. A sync run fetches unprocessed messages that match each rule's conditions.
4. The email body (plain part **plus** stripped HTML part) is matched against the rule regex, producing amount, merchant, card, date, channel and reference.
5. A matching message is posted to Firefly III, the message is tagged processed, and a row is written to the `transactions` log either way.

## Task routing

| I want to… | Read |
| --- | --- |
| Understand how the pieces fit together | `/openwiki/architecture/system-overview.md` |
| Know where a setting, secret or credential comes from | `/openwiki/architecture/configuration-and-secrets.md` |
| Create or fix a parsing rule in the UI | `/openwiki/systems/rule-authoring-workflow.md` |
| Understand what text the regex actually runs against | `/openwiki/systems/email-body-extraction.md` |
| Debug "no matching pattern" / a failed parse | `/openwiki/operations/testing-and-diagnostics.md` |
| Trace one sync run end to end | `/openwiki/workflows/sync-pipeline.md` |
| Change which emails a rule picks up | `/openwiki/systems/email-ingestion.md` |
| Change how a regex becomes transaction fields | `/openwiki/systems/transaction-parsing.md` |
| Change what gets posted to Firefly III | `/openwiki/systems/firefly-posting.md` |
| Work on the database schema or queries | `/openwiki/systems/persistence.md` |
| Call the HTTP API directly | `/openwiki/systems/dashboard-api.md` |
| Deploy, schedule or back up | `/openwiki/operations/deployment-and-scheduling.md` |

## Three facts worth knowing before changing anything

* **The sample box and the parser see the same text.** `body_text_from_message()` in `app/services/email_body.py` produces the body for both the parse and the wizard's "Sample Text"; changing one without the other breaks the guarantee that a rule previewed in the UI behaves the same at sync time.
* **Rules come from the database, never from `config.toml`.** `config.toml` still drives the CLI worker and fallback values like the processed tag, but the running service ignores it for mailboxes and rules.
* **Deduplication lives in IMAP, not the database.** A processed keyword on the message prevents re-import; Firefly's duplicate protection is disabled in the payload.

## Repository shape

```
app/api/v1/endpoints/   FastAPI routers (rules, mailboxes, sync, status, …)
app/services/           parser, email_body, imap, firefly_builder, firefly_client, service (worker)
app/db/session.py       pymysql data layer and schema creation
cli/                    sync_worker (API-triggered thread) and main (manual run)
frontend/src/            Vue 3 dashboard (built into static/dist)
scheduler-worker/        fcron sidecar: cron sync trigger + rclone backups
tests/                   unittest suites (test_email_body.py is the runnable one)
```
