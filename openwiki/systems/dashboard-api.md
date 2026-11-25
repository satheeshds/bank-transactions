---
type: reference
title: Dashboard REST API surface
description: Map of the FastAPI routers Mail2Firefly exposes under /api/v1 — status, sync, logs, transactions, rules, mailboxes with sample fetching, regex preview, AI regex suggestion, Firefly settings, generic settings and Firefly autocomplete — plus the legacy /api aliases and the response shapes the Vue app depends on.
tags: [api, rest, fastapi, routers, contracts]
verified:
  - by: openwiki/0.9.0
    at: 2026-11-25T04:51:17.394Z
sources:
  - id: openwiki-source-fd1e08877986f66048c23b58
    resource: repo://app/api/v1/endpoints/ai.py
  - id: openwiki-source-84ca334463a3544a98534728
    resource: repo://app/api/v1/endpoints/autocomplete.py
  - id: openwiki-source-833fc642bfe0c1d5bb06b763
    resource: repo://app/api/v1/endpoints/mailboxes.py
  - id: openwiki-source-c78a685ff399d80e0ef6e6b9
    resource: repo://app/api/v1/endpoints/regex_preview.py
  - id: openwiki-source-dcf78c604dfbc84af96d4a29
    resource: repo://app/api/v1/endpoints/rules.py
  - id: openwiki-source-909c9d53b9d25913cfc4ad49
    resource: repo://app/api/v1/endpoints/status.py
  - id: openwiki-source-d56fe262d5d2c3f18c0f7fee
    resource: repo://app/api/v1/schemas.py
  - id: openwiki-source-21c0a295e6c6f5529dc70d5f
    resource: repo://app/main.py
  - id: openwiki-source-ed31fdd907f93645f93ecd02
    resource: repo://frontend/src/views/FailedParseDetailView.vue
generated: { by: "omp", at: "2026-11-25T04:51:17.394Z" }
---

# Dashboard REST API surface

All routers live in `app/api/v1/endpoints/` and are included by `app/main.py` under the `/api/v1` prefix. Shared response models are declared in `app/api/v1/schemas.py`; most handlers return plain dictionaries and are typed loosely (`list[dict[str, Any]]`), so the schemas document intent rather than enforce output.

## Router map

| Router | Endpoints | Notes |
| --- | --- | --- |
| `status` | `GET /status` | IMAP socket probe per mailbox, Firefly `/api/v1/about` probe, today's stats, latest run |
| `sync` | `POST /sync` | starts the background worker; `409` when a run is active |
| `logs` | `GET /logs?limit=` | `sync_logs` rows, oldest→newest |
| `transactions` | `GET /transactions?limit=&status=`, `GET /transactions/{id}` | status filtered in Python after limiting |
| `rules` | `GET/POST /rules`, `GET/PUT/DELETE /rules/{id}` | `conditions`/`mappings` persisted as JSON text |
| `mailboxes` | `GET/POST /mailboxes`, `PUT/DELETE /mailboxes/{id}`, `POST /mailboxes/test`, `GET|POST /mailboxes/{id}/sample` | socket check on list, full login on `/test` |
| `firefly` | `GET/PUT /firefly` | base_url, token, timeout, custom_keys |
| `regex_preview` | `POST /regex_preview` | compile + match with a 0.5 s timeout guard |
| `ai` | `POST /ai/regex` | Gemini suggestion, requires `gemini_api_key` setting |
| `settings` | `GET /settings/{key}`, `POST /settings` | masks `*token` and `*api_key` on read |
| `autocomplete` | `GET /autocomplete/{kind}` | proxies Firefly autocomplete for accounts/tags/categories/currencies/transaction_types |

`app/main.py` additionally re-exports a subset of these handlers on legacy paths (`/api/status`, `/api/sync`, `/api/logs`, `/api/transactions[/{id}]`, `/api/rules`, …). The Vue app still calls some legacy paths — `FailedParseDetailView.vue` fetches `/api/transactions/{id}` — so those aliases are load-bearing, not decorative.

## Status and connectivity

`GET /api/v1/status` is the dashboard's single health call. It walks the mailboxes table, opens a raw TCP socket to each host:port (2 s timeout, port defaulting to 993), and reports per-mailbox `connected`/`error`; overall `imap.connected` is true when *any* mailbox is reachable. Firefly is probed only when both base URL and token are configured: the handler builds a client and issues `GET /api/v1/about`, recording latency in milliseconds or the exception text. Stats come from `get_stats_today()` and `latest_run` from the newest `sync_runs` row; `is_running`/`current_run_id` come from the in-process sync lock.

## Mailbox endpoints

Listing mailboxes returns `{"mailboxes": [...]}` where each row is the stored mailbox plus `connected` and `error` from the socket probe. `POST /api/v1/mailboxes/test` accepts an unsaved payload, requires `host`, performs a 3 s socket check and then a real IMAP login when `imap_tools` and credentials are available, always answering `200` with a `{connected, error?|warning?}` body so the UI can render a result without dealing with HTTP errors.

`GET /api/v1/mailboxes/{id}/sample` fetches the single most recent message; `POST /api/v1/mailboxes/{id}/sample` accepts `{"conditions": [...], "condition_mode": "AND|OR"}` and builds the IMAP query with `build_query()`, including the `UNKEYWORD` exclusion for the mailbox's processed tag. Both return the same payload:

```json
{
  "sample_text": "…parser-visible body text (plain part + stripped HTML)…",
  "sample_html": "…raw HTML part, for reference…",
  "sample_meta": {"subject": "…", "from": "…", "to": "…", "cc": "…", "bcc": "…", "date": "…", "message_id": "…"},
  "sample_parts": ["text", "html"]
}
```

`sample_text` is produced by `body_text_from_message()`, the same helper the parser uses, so the wizard can never show a body that sync would not see. `sample_meta.date` matches the `date` key the wizard's IMAP-field column reads — earlier versions returned `sent_date` from the GET variant, which silently rendered `-`. When no message matches, both fields are empty and `sample_parts` is `[]`; a fetch failure is reported as `{"error": "…"}` with HTTP 200 so the wizard can display it inline.

## Rules

`RuleIn` carries `source_name`, `rule_name`, `regex`, `description`, `transaction_type` (default `withdrawal`), `card_last4`, `conditions`, `condition_mode` and `mappings`. On write, `conditions` and `mappings` are serialised to `conditions_json`/`mappings_json`; on read (`GET /rules/{id}`) they are parsed back into objects, while the list endpoint returns only the scalar columns. `GET /rules` returns `{"rules": []}` rather than an error when the table is empty, and wraps database failures in a `500` JSON body.

## Regex preview and AI regex

`POST /api/v1/regex_preview` takes `{regex, sample_text}` and runs the Python `re` module in a single-thread executor with a 0.5 s budget, returning `{"groups": [...], "named": {...}, "groupindex": {...}}`, `{"groups": []}` when nothing matches, `{"error": "compile_error: …"}` for invalid patterns, or `{"error": "timeout"}`. Because it uses Python's engine, `(?P<name>…)` groups are valid input and `groupindex` is exactly what the wizard needs to label group tiles.

`POST /api/v1/ai/regex` requires the `gemini_api_key` setting; it prompts Gemini with a few-shot instruction to emit a single-line regex using the canonical group names (`currency`, `amount`, `account_ending`, `vpa`, `merchant`, `date`, `reference`), then tries a list of models in order (`gemini-3.1-flash-lite`, `gemini-2.5-flash-lite`, `gemini-3.5-flash`, `gemini-3-flash`, `gemini-2.5-flash`), retrying only on quota/rate-limit errors and returning `{"regex": "…"}`. Missing key → `400`; exhausted quota → `502`; other failures → `500`.

## Firefly settings and autocomplete

`GET/PUT /api/v1/firefly` is the only endpoint that reads/writes the Firefly connection (`firefly.base_url`, `firefly.token`, `firefly.timeout`, and `firefly.custom_keys` as JSON). `GET /api/v1/settings/{key}` is the generic escape hatch for everything else, and it deliberately hides secrets.

`GET /api/v1/autocomplete/{kind}` validates `kind` against a fixed set (`accounts`, `tags`, `categories`, `currencies`, `transaction_types`), returns `[]` when Firefly is unconfigured, and otherwise proxies Firefly's `/v1/autocomplete/{kind}` with `query`, `limit` and optional `date`. This is what powers the "Firefly Value" mapping picker in the rule wizard.
