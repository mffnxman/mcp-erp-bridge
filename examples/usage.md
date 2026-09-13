# Usage examples

Once `mcp-erp-bridge` is installed and configured (see top-level README),
your MCP client (Claude Code, Claude Desktop, etc.) sees three new tools.

## Looking up a work order

> **You:** Pull work-order 12345678 and tell me the status.

The model calls `get_work_order(wo_number="12345678")` and gets back a
typed `WorkOrder` object. It can then summarize for the user:

```
work-order 12345678 is IN PROGRESS, assigned to Doe, Jane, scheduled for
2026-05-08 14:00. NTE is $850, customer is Acme Retail Co at the
Anytown-Main location. Parent WO is 12300000.
```

## Listing pending work for a manager

> **You:** What's still pending dispatch under Doe?

The model calls `list_pending_work(manager="Doe, Jane")` and
returns the list as a markdown table.

## Authoring a close-out note

> **You:** Draft and submit the close-out note for work-order 12345678. Plumber fixed
> a leak under the sink, used a coupling and silicone, no warranty.

The model:

1. Calls `get_work_order(...)` to gather context
2. Composes the required fields from the conversation + work-order context
3. Validates against `CloseoutFields` (all required fields present)
4. Calls `add_closeout_note(wo_number=..., fields=...)`

If a field is missing, the Pydantic validator raises before any HTTP traffic
leaves. The user sees a clear "you need to provide X" message rather than
a silent submission of an incomplete note.

## Adapting to your system

Every selector the client uses is in `ErpConfig` (see `config.py`). Copy
`erp_config.example.json`, change the CSS selectors and endpoint paths to
match your system's pages, and set `ERP_CONFIG_FILE`. The close-out note
form is submitted as `<note_field_prefix><field_name>=value` pairs; change
the prefix (and `CloseoutFields` if your form wants different fields).

## Why this is the pattern

Notice what's NOT happening: the model isn't writing prompts to extract
fields from random HTML. It's calling typed tools that return typed objects.
The probabilistic edge (drafting prose, summarizing, matching intent) is
LLM-native. The deterministic core (HTTP, parsing, validation, submission)
is plain Python.

This is the deployment shape that survives production.
