---
type: workflow
title: Rule authoring wizard
description: The four-step Vue wizard that creates a parsing rule — basic info, trigger conditions, pattern matching against a live email sample with regex preview and AI suggestion, and destination mapping to Firefly fields — plus how the rule is validated and persisted.
tags: [frontend, vue, wizard, regex, rules, mappings]
verified:
  - by: openwiki/0.9.0
    at: 2026-11-25T06:25:34.695Z
sources:
  - id: openwiki-source-9b3495cfcfdaa7e2c3574164
    resource: repo://frontend/src/views/AddParsingRuleView.vue
  - id: openwiki-source-da933dd51a05f90fc1ff1c55
    resource: repo://frontend/src/views/ParsingRulesView.vue
generated: { by: "omp", at: "2026-11-25T06:25:34.695Z" }
---

# Rule authoring wizard

`frontend/src/views/AddParsingRuleView.vue` is a single component that both creates and edits a rule, driven by a four-step `step` ref. `ParsingRulesView.vue` renders the list (`GET /api/rules`, the legacy alias) and deletes rules via `DELETE /api/v1/rules/{id}`, re-fetching every 30 s and whenever the shared store's `refreshTrigger` changes.

Routing is `/#/parsing-rules/add` for creation and `/#/parsing-rules/add?id=<id>` for editing — the component reads `route.query.id` on mount and calls `loadExistingRule()`. There is no separate edit route.

## Reactive form state

```js
form = reactive({
  rule_name, description, source_name, source_id,
  conditions: [{ not:false, field:'from', operator:'equals', value:'', timeframe:null }],
  condition_mode: 'AND',
  regex, sample_text, sample_meta, mappings: [],
  transaction_type: 'withdrawal', card_last4, destination_account,
})
```

`mappings` starts with a single `amount` row created by `ensureMapping('amount')`; everything else is added on demand from the 42-entry Firefly field list imported from `frontend/src/data/firefly_fields.json`.

Two watchers create the cross-step coupling:

* `watch(step, …)` loads Firefly custom keys when entering step 4 and calls `loadSample()` when entering step 3;
* `watch([form.regex, form.sample_text], …)` debounces (300 ms) a call to `fetchServerPreview()`.

## Step 1 — basic information

Rule name (required to advance), description, and mailbox selector. The selector binds `form.source_id` to a mailbox `id` but keeps `form.source_name` as the mailbox `name`, because rules are matched to mailboxes by name at sync time. On save, `source_name` defaults to `mailbox:<source_id>` when empty — a name no mailbox has, so the worker will log "No mailbox found for rule …" and skip it.

## Step 2 — trigger conditions

Conditions are rows of `{not, field, operator, value, connector}` with `field` limited to `from`, `to`, `subject`, `text`, `date`. The operator is fixed by field: `Equals` for `from`/`to` (with client-side email validation feedback), `Contains` for `subject`/`text`, and a `>=`/`<` select for `date` that switches the input to a date picker.

The AND/OR buttons set `condition_mode`, which only affects *newly added* conditions (they inherit it as their `connector`); the connector between two existing conditions is toggled independently through the button rendered between rows (`toggleConnector(i+1)`). The server ignores `condition_mode` and folds per-condition connectors, so the per-row buttons are the real control.

These same `conditions` are what the sample loader POSTs when entering step 3, so a rule with conditions that match nothing yields an empty sample.

## Step 3 — pattern matching

Entering the step triggers `loadSample()`, which POSTs `{conditions, condition_mode}` to `/api/v1/mailboxes/{source_id}/sample` and assigns `data.sample_text` **verbatim** — the server already returns the parser-visible body (plain part plus stripped HTML), so the browser must not strip it again. The response also provides `sample_meta` (for the IMAP-field preview column) and `sample_parts`, which is rendered as a hint: "Loaded from MIME part(s): text + html — identical to the text the parser will match against", plus a note when the email has no HTML part. A fetch error is shown inline under the textarea instead of being written into the sample.

A second hint appears when the loaded body contains keyed table rows (`hasSampleTables`, i.e. the text contains `table: `): it explains that table rows are appended as `table: Header=value | Header=value` lines and shows an example column-name regex such as `Withdrawals=(?P<amount>[\d.,]+)`. This is how an operator discovers that a transaction table can be matched by header rather than by column position.

The textarea remains editable, which is how an operator can paste a different email or trim a long statement.

Three helpers consume `sample_text`:

1. **Server preview (authoritative).** `POST /api/v1/regex_preview` with `{regex, sample_text}` returns `groups`, `named` and `groupindex`; the wizard keeps `serverPreview`, `serverNamed`, `serverGroupIndex` and renders group tiles from them.
2. **Client fallback.** If the server has no answer, `previewGroups` runs the regex in the browser with `new RegExp()`, after converting Python-style `(?P<name>…)` to JS `(?<name>…)`. `groupCount` mirrors it for the "available groups" list.
3. **AI suggestion.** `aiSuggest()` posts the sample to `/api/v1/ai/regex` and drops the returned string straight into the regex box.

Group availability for the mapping step is `availableGroups()`: the higher of the server preview length minus one and the client group count, capped at 12, plus any group numbers restored from an already-saved rule (so editing a rule without loading a sample still shows its groups).

## Step 4 — destination mapping

Each mapping row renders the Firefly field name, a source-type selector, and a value editor that switches on the type:

| Source type | Editor | Persisted field |
| --- | --- | --- |
| `regex_group` | group select (labelled with named groups when known) | `group` |
| `fixed` | free text | `value` |
| `custom_key` | select of keys from `GET /api/v1/firefly` → `custom_keys` | `custom_key` |
| `imap` | select of subject/from/to/cc/bcc/date/message_id | `imap_field` |
| `firefly` | debounced autocomplete against `/api/v1/autocomplete/{accounts,tags,categories,currencies,transaction-types}` | `value` (id for `*_id` fields, name otherwise) |

Custom keys added as a mapping default to source type `fixed` with the configured key value pre-filled — a pragmatic shortcut because, as noted in the Firefly page, `custom_key` has no server-side resolver.

`fieldToAutocompleteEndpoint()` decides which Firefly autocomplete collection a field belongs to by substring matching on the field key, so `source_id`, `destination_id`, `tags`, `category_*`, `currency_*` and `type` all resolve correctly while any other field simply shows no suggestions.

## Validation and save

`submitRule()` enforces one rule: an `amount` mapping must exist, and if it is `regex_group` it must reference a group greater than zero; a `fixed` amount must be non-empty. Everything else (merchant, description, card, date) is optional — the parser supplies defaults.

The POST/PUT body carries `source_name`, `rule_name`, `description`, `regex`, `transaction_type`, `card_last4`, `conditions`, `condition_mode` and the narrowed `mappings` array (`fieldKey`, `field`, `source_type`, `value`, `group`, plus `custom_key`/`imap_field` where relevant). On success the wizard navigates back to the rules list; failures surface the API's `detail` message.

Editing an existing rule rehydrates `firefly_selected` for `firefly`-type mappings from the stored `value`, including the legacy `firefly_id`/`firefly_name` shape, and repopulates `extraGroups` from saved `group` values.
