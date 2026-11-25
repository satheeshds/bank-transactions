---
type: system
title: Firefly III transaction building and posting
description: How parsed transaction details plus rule mappings become a Firefly III payload — mapping resolvers (regex group, IMAP field, fixed, Firefly value), placeholder substitution, the Firefly field whitelist loaded from the built frontend bundle, transaction type selection and HTTP error handling.
tags: [firefly, payload, mappings, http, integration]
verified:
  - by: openwiki/0.9.0
    at: 2026-11-25T04:51:17.394Z
sources:
  - id: openwiki-source-d85e29b90d810449d653534a
    resource: repo://app/services/firefly_builder.py
  - id: openwiki-source-bd942826583dbb8b9f4ec1cb
    resource: repo://app/services/firefly_client.py
  - id: openwiki-source-d9baa31399f68a28b825b26c
    resource: repo://app/services/mapping_resolvers.py
  - id: openwiki-source-dd4e9388d1ad0a8dafd32128
    resource: repo://app/services/parser.py
  - id: openwiki-source-08628abdfe83c50c2702a735
    resource: repo://app/services/service.py
  - id: openwiki-source-9b3495cfcfdaa7e2c3574164
    resource: repo://frontend/src/views/AddParsingRuleView.vue
  - id: openwiki-source-c1bd8bd4834d4dc70a8b85cc
    resource: repo://frontend/vite.config.js
generated: { by: "omp", at: "2026-11-25T04:51:17.394Z" }
---

# Firefly III transaction building and posting

`app/services/firefly_builder.py` turns a parsed `TransactionDetails` dictionary into the JSON body Firefly III expects; `app/services/firefly_client.py` sends it; `app/services/mapping_resolvers.py` resolves the per-rule mapping rows that enrich the details. The worker calls this through `TransactionImportService._post_to_firefly()`.

## From mappings to details

Before any Firefly-specific work, `_build_firefly_payload()` looks for `mappings` (or `mappings_json`) on the details dict — the list the rule wizard saved — and runs `apply_mappings()` over it. Each mapping row needs a target key (`fieldKey` preferred, `field` accepted) and a `source_type`; unknown source types and resolver exceptions are logged at DEBUG and skipped rather than aborting the payload.

| `source_type` | Resolver | Value taken from |
| --- | --- | --- |
| `regex_group` | `resolve_regex_group` | `details["groupdict"][group]` first (named groups), then `details["groups"][n-1]` for a 1-based numeric group |
| `imap` | `resolve_imap` | `getattr(message, imap_field)` when the attribute exists, else `details[imap_field]` |
| `fixed` | `resolve_fixed` | the mapping's `value` |
| `firefly` | `resolve_firefly` | the mapping's `value` (a Firefly account/tag/budget identifier chosen through autocomplete) |
| `custom_key` | — | no resolver: the wizard's custom-key source type falls through and the mapping is skipped, so today custom keys only survive if they arrive as a details key already |

`regex_group` therefore depends on `extract_transaction_details()` attaching `groups`/`groupdict` — which is why that function re-runs the matching pattern after `extract_transaction()` rather than only returning the dataclass fields.

## Building the payload

`_build_firefly_transaction(details, message_date, statement_config, message)`:

1. coerces `TransactionDetails` to a dict, reads `amount` as a float, and picks the transaction date: the IMAP message date if given, else `transaction_date`/`date` from the details; datetimes are formatted `%Y-%m-%d %H:%M:%S%z`.
2. calls `_build_firefly_payload()` to produce the field dictionary.
3. wraps everything in Firefly's transaction envelope:

```python
{
  "error_if_duplicate_hash": False,
  "apply_rules": True,
  "fire_webhooks": True,
  "transactions": [{**payload, "notes": "channel=…; ref=…"}],
}
```

`error_if_duplicate_hash: False` is deliberate but consequential: Firefly's duplicate protection is off, and this application has no dedupe of its own, so the only guard against a double import is the IMAP processed tag.

## The field whitelist is loaded from the frontend bundle

`_build_firefly_payload()` iterates `_load_firefly_fields()` (cached at module level) and copies any field whose key exists on the details dict — coercing datetime-likes to strings and cleaning `amount` (`"₹1,455.00"` → `1455.0`).

That list is read from `static/dist/firefly_fields.json`, i.e. from the **built** frontend, because `frontend/public/firefly_fields.json` is copied into the Vite output directory. Two operational consequences:

* If the frontend has never been built (or `static/dist` was wiped), `_load_firefly_fields()` returns `[]`, no fields are copied, and the posted transaction contains only `notes`. The failure is silent at debug level; a run "succeeds" while importing nothing useful.
* The dashboard's field picker data (`frontend/src/data/firefly_fields.json`) and this server-side whitelist are separate copies of the same 42-field list. They must be kept in sync by hand.

The same idea applies to pattern-level Firefly configuration: `_build_firefly_payload()` resolves `details["firefly"]` → `details["firefly_mapping"]` → `statement_config["firefly"]`, substitutes `{key}` placeholders from the details dict and `{account_id}` from the statement config, and leaves unresolved placeholders in place.

`transaction_type` is read from the details (`transaction_type` then `type`), lower-cased, and defaults to `withdrawal` when missing or blank. Nothing derives deposit vs withdrawal automatically: a credit alert is imported as a withdrawal unless the rule or mapping sets the field.

## Posting and error handling

`FireflyClient` is a small `urllib`-based client: it joins `base_url` (trailing slash stripped) with the path, sends `Authorization: Bearer <token>`, `Accept: application/json` and a JSON body, and decodes the response. `create_transaction()` posts to `/api/v1/transactions`. HTTP failures raise `FireflyClientError` with the status code and response body; URL failures raise it with the reason string.

`_post_to_firefly()` returns `(status, payload, error_message)`:

* `rule_name`/`rule_id` are stripped from the details before building, so wizard-only metadata never reaches Firefly;
* with a client: success logs the payload, sets `status = "synced"`, increments `parsed_count` and marks the message processed; `FireflyClientError` logs the failure, sets `status = "error"`, records the message and increments `error_count`;
* without a client (no base URL or token configured): the transaction is logged as `status = "pending"` and counted as parsed, which is the "dry run" mode used when validating rules before pointing at a live Firefly.

Only the success branch tags the message. A Firefly outage therefore leaves the message retryable on the next cron run, while a permanently broken rule would loop forever — that is what the Failed Parses view is for.
