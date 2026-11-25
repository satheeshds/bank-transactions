# OpenWiki brief for Mail2Firefly

Scope and priorities for generated pages in `openwiki/`.

## What this repository is

Mail2Firefly imports bank alert emails into Firefly III: a FastAPI service plus Vue 3 dashboard, a
sync worker, MySQL/MariaDB persistence, IMAP ingestion and a regex parser.

## Priorities

1. **Behavioural contracts over file inventories.** Explain how a rule turns an email into a Firefly
   transaction, and where each step can fail.
2. **Document the email body extraction contract explicitly.** `app/services/email_body.py` is the
   single source of truth for the text a regex is matched against, shared by the parser, the
   `/api/v1/mailboxes/{id}/sample` endpoints and the transaction log. Pages must state that the rule
   wizard's "Sample Text" equals parser input, and must explain the `multipart/alternative`
   boilerplate-text-part failure mode it fixes.
3. **Call out silent-failure seams**, because they cost the most debugging time:
   * rule `mappings_json` is stored as JSON text while the payload builder only applies lists, so
     database-rule mappings are currently ignored at sync time;
   * the Firefly field whitelist is loaded from `static/dist/firefly_fields.json`, a frontend build
     artifact, so an unbuilt frontend yields payloads containing only `notes`;
   * currency is hard-coded to INR by the parser;
   * `condition_mode` is stored but unused, and per-condition connectors decide the IMAP query;
   * the processed IMAP keyword is the only dedupe mechanism (`error_if_duplicate_hash: false`).
4. **Prefer MySQL reality.** The data layer is MySQL-only through `pymysql`; there are no migrations,
   no foreign keys and timestamps are ISO strings in TEXT columns.
5. **Be honest about tests.** `tests/test_email_body.py` is the runnable suite; `tests/test_parser.py`
   still imports modules removed by the `app/` refactor.

## Task and workflow pages expected

Rule authoring (the four-step wizard), sync pipeline end to end, IMAP ingestion and query building,
regex parsing and field mapping, Firefly payload building and posting, persistence, dashboard API,
deployment/scheduling (Docker + fcron sidecar) and diagnostics.

## Maintenance

Update with `openwiki code --update`, or drive the host lifecycle from a coding agent via
`openwiki integrations install omp --project` and then `openwiki mcp --host omp`.
