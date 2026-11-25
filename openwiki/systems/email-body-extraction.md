---
type: concept
title: Email body extraction contract
description: How Mail2Firefly turns an email into the text a rule regex matches against — the plain part and the HTML part concatenated, why the plain part alone breaks bank alerts, and the invariant that the rule wizard's sample text is produced by the same helper as the sync pipeline.
tags: [parsing, email, html, imap, invariant, bugfix]
verified:
  - by: openwiki/0.9.0
    at: 2026-11-25T04:51:17.394Z
sources:
  - id: openwiki-source-833fc642bfe0c1d5bb06b763
    resource: repo://app/api/v1/endpoints/mailboxes.py
  - id: openwiki-source-a8047a190df69a0969f10e04
    resource: repo://app/services/email_body.py
  - id: openwiki-source-dd4e9388d1ad0a8dafd32128
    resource: repo://app/services/parser.py
  - id: openwiki-source-08628abdfe83c50c2702a735
    resource: repo://app/services/service.py
  - id: openwiki-source-9b3495cfcfdaa7e2c3574164
    resource: repo://frontend/src/views/AddParsingRuleView.vue
  - id: openwiki-source-7b05dab96e231da3a0584fc2
    resource: repo://tests/test_email_body.py
generated: { by: "omp", at: "2026-11-25T04:51:17.394Z" }
---

# Email body extraction contract

`app/services/email_body.py` is the single source of truth for converting a message into matchable text. It is deliberately dependency-free (stdlib only: `email`, `html`, `re`) so the parser, the HTTP sample endpoints and the transaction log can all import it without pulling FastAPI, `imap_tools` or `app.config` into the import graph.

## The invariant

> `body_text_from_message(msg)` returns exactly the string `extract_transaction()` applies its patterns to, and the rule wizard's "Sample Text" box displays that same string.

Everything else in this page explains why that sentence needs writing down.

## Why both MIME parts

Bank and UPI alerts are usually `multipart/alternative`: a `text/plain` part and a `text/html` part carrying the same content. Some senders ship a *transaction-less* plain part that exists only to tell old clients to render HTML:

```
For easy reading and better experience, this email is sent in HTML format.
Please use HTML enabled email client to view this email.
```

With the real amount, merchant and reference number only in the HTML part. An extractor that prefers the plain part (and falls back to HTML only when the plain part is missing) therefore yields a body that matches nothing — so a rule author sees a useless sample, "AI Suggest" produces a regex for the wrong text, the wizard's group tiles stay empty, and sync logs "Could not find a supported transaction pattern".

The fix is not "prefer HTML" but "include both": `body_text_from_message()` coerces each part and joins them with a newline, so a pattern written against either rendering still matches, and a pattern that depends on context from both still works.

## The four functions

| Function | Behaviour |
| --- | --- |
| `strip_html(text)` | HTML-unescape, drop `<style>`/`<script>` blocks, strip remaining tags, collapse all whitespace to single spaces, trim. Returns `""` for falsy input. |
| `extract_text_from_message(mime)` | Walk a parsed `email.message.Message`, skip non-text and multipart containers, decode each payload with its declared charset (falling back to UTF-8), run `strip_html` for `text/html`, join parts with newlines. |
| `coerce_text_content(raw)` | Normalise an arbitrary string: if it looks like a full MIME message (a `From:`/`To:`/`Subject:`/`Date:`/`Message-ID:`/`Content-Type:` header at line start) re-parse it as MIME; else if it contains `<html`/`<body` strip it; else return it unchanged. |
| `body_text_from_message(msg)` | Read `msg.text` and `msg.html` (attribute access, so any imap_tools-like object works), coerce each, join non-empty results with `\n`. Empty message → `""`. |

A companion helper, `body_parts_from_message(msg)`, reports which attributes actually contributed (`["text"]`, `["html"]` or `["text", "html"]`); the sample endpoint returns it as `sample_parts`, and the wizard uses it to tell the operator what they are looking at.

## Where the contract is enforced

* **Parser.** `app/services/parser.py` delegates to the module and keeps thin aliases (`_strip_html`, `_extract_text_from_message`, `_coerce_text_content`) so older imports keep working. `_body_text_from_source()` is the single branch point: bytes and existing paths are parsed as MIME, strings run through `coerce_text_content`, objects exposing `.text`/`.html` go through `body_text_from_message`, anything else raises `TypeError`. Both `extract_transaction()` and `extract_transaction_details()` call it, replacing the body-building block that used to be duplicated in each.
* **Sample endpoint.** `_sample_payload()` in `app/api/v1/endpoints/mailboxes.py` builds `sample_text` with `body_text_from_message(msg)` and `sample_parts` with `body_parts_from_message(msg)`; both the GET and POST sample routes return it, so the wizard's sample cannot drift from parser input.
* **Failure log.** The worker stores `raw_email = body_text_from_message(message) or None` at all three logging sites (parser exception, no-match, and success), which is why the Failed Parse detail view shows readable text rather than raw HTML.
* **Frontend.** `AddParsingRuleView.vue` assigns `data.sample_text` verbatim. It no longer runs the browser-side `stripHtml()` over it (that helper is retained only as a legacy fallback for a payload that carries `sample_html` alone), so text containing `<` is no longer mangled and HTML is not stripped twice.

## Consequences to keep in mind

* Whitespace is flattened by `strip_html`, so a regex cannot rely on newlines *inside* the HTML part. Multi-line matching only works across the `\n` that joins the two parts.
* Both parts are present in the body, so a pattern expecting one line can still match inside a duplicated rendering. Anchor with distinctive text (amount + reference) rather than relying on a single occurrence.
* Ordering is fixed: plain part first, then HTML. Anybody adding a third source (for example decoded attachments) should extend `body_text_from_message()` rather than special-casing a caller.
* The extracted body is what reaches the database via `raw_email`, so changing this function changes the diagnostics surface too.

`tests/test_email_body.py` pins the behaviour: the boilerplate-plus-HTML regression, equality between a fake message and the equivalent raw MIME bytes, the parts report, and an end-to-end `extract_transaction_details()` assertion on the same input.
