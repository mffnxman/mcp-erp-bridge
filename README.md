# mcp-erp-bridge

> A Model Context Protocol server that wraps a session-cookie-authenticated
> enterprise web app (an ERP, a work-order system, a ticketing portal) and
> exposes structured tools to any MCP-compatible client.

This is a **reference implementation** of a deployment pattern: turning an
internal-only enterprise web app with no API into an MCP server so
non-technical operators can drive it with Claude Code, Claude Desktop, or
any other MCP client.

The pattern is deliberately generic. Endpoint paths, login form fields, the
session cookie name, and every HTML selector live in one config object
(`ErpConfig`) and can be overridden from a JSON file, so the same code
adapts to any system with a cookie-based auth flow and HTML pages.

---

## Why this exists

Most MCP examples wrap clean SaaS APIs (Slack, Linear, GitHub).
The real deployment surface in the messy middle of the economy is
**internal enterprise tools with no public API and a session cookie for auth.**
This server is a worked example of how to wrap one.

The shape: a server, a handful of tools, a typed schema on every call, and
an opinionated deterministic-core / probabilistic-edge split.

---

## Tool status

| Tool | Status |
|---|---|
| `get_work_order` | Implemented |
| `list_pending_work` | Implemented |
| `add_closeout_note` | Implemented |
| `find_field_schedule` | Designed (schema + overtime walk-back logic ready; schedule-export parser not bundled) |
| `detect_overtime` | Designed (schema ready; awaits roster iteration on a real backend) |

Three tools are fully wired against the HTTP client. The two scheduling
tools have schemas and supporting logic in `schemas.py` and `overtime.py`,
but the schedule-export parser is intentionally not bundled: every system
serves schedules differently, and shipping a stub would be dishonest.

---

## Features

- **Three production-ready tools** plus two designed-but-unbundled
- **Session-cookie + CSRF auth** with automatic refresh on 401
- **SQLite cookie cache** so re-auth happens once per session window,
  not per call
- **Selector-driven parsing**: every CSS selector, form field, and endpoint
  path is configuration, not code
- **Pydantic schemas** on every tool input/output: Claude sees a typed
  contract, not a free-form dict
- **Stdio transport** for Claude Code / Claude Desktop integration
- **Injectable HTTP transport** so the whole client is testable offline
- **MIT licensed**: fork it, point it at your own system

---

## Install

From source:

```bash
git clone https://github.com/mffnxman/mcp-erp-bridge
cd mcp-erp-bridge
pip install -e ".[dev]"
```

## Configure

Credentials come from the environment:

```bash
export ERP_USERNAME="your.login@example.com"
export ERP_PASSWORD="..."
export ERP_BASE_URL="https://erp.example.com"
```

Endpoints and selectors come from an optional JSON file. Copy
`examples/erp_config.example.json`, edit it to match your system's markup,
and point at it:

```bash
export ERP_CONFIG_FILE="/path/to/erp_config.json"
```

Any key you leave out keeps its default. Unknown keys raise at startup so
typos don't silently fall back to placeholders.

```json
{
  "endpoints": { "login": "/account/signin", "work_order": "/orders/{wo_number}" },
  "selectors": {
    "session_cookie": "ASPSESSIONID",
    "detail_fields": { "status": "span.order-state", "technician": "#assigned-to" },
    "list_rows": "table#orders tr.row"
  }
}
```

## Use with Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`
(or the Windows equivalent at `%APPDATA%\Claude\claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "erp-bridge": {
      "command": "python",
      "args": ["-m", "mcp_erp_bridge"],
      "env": {
        "ERP_USERNAME": "your.login@example.com",
        "ERP_PASSWORD": "...",
        "ERP_BASE_URL": "https://erp.example.com",
        "ERP_CONFIG_FILE": "/path/to/erp_config.json"
      }
    }
  }
}
```

## Use with Claude Code

```bash
claude mcp add erp-bridge python -m mcp_erp_bridge \
  -e ERP_USERNAME=your.login@example.com \
  -e ERP_PASSWORD=... \
  -e ERP_BASE_URL=https://erp.example.com \
  -e ERP_CONFIG_FILE=/path/to/erp_config.json
```

---

## Tools

### `get_work_order(wo_number: str) -> WorkOrder`

Fetches a single work order by number. Returns the full structured record:
status, assigned technician, schedule, NTE, customer, location, parent work
order, and the close-out fields.

```
get_work_order("12345678")
-> WorkOrder(
    number="12345678",
    status="In Progress",
    technician="Doe, Jane",
    scheduled="2026-05-08 14:00",
    nte=850.00,
    closeout_fields={...}
  )
```

### `list_pending_work(manager: str = None) -> List[WorkOrder]`

Returns all work orders currently pending dispatch or in progress,
optionally filtered to a single manager.

```
list_pending_work(manager="Doe, Jane")
-> [WorkOrder(...), WorkOrder(...), ...]
```

### `add_closeout_note(wo_number: str, fields: CloseoutFields) -> NoteResult`

Adds a close-out note to a work order with all required fields templated
from structured input. Validates every field before submission; raises
rather than silently submitting an incomplete note.

---

## Architecture

```
+-----------------+   stdio   +-----------------+
|   MCP Client    |<--------->| mcp-erp-bridge  |
| (Claude Code)   |           |  server         |
+-----------------+           +--------+--------+
                                       | tool calls
                              +--------v--------+
                              |   ErpClient     |
                              | (httpx + SQLite |
                              |  cookie cache)  |
                              +--------+--------+
                                       | HTTPS
                                       v
                              +-----------------+
                              | Enterprise ERP  |
                              | (session cookie |
                              |  + CSRF)        |
                              +-----------------+
```

The deliberate choice: **all "right-answer" logic is deterministic Python.**
Claude is only on the probabilistic edge: drafting prose, summarizing,
matching intent. Tool calls go straight to deterministic Python. This is the
pattern that survives production.

---

## Project structure

```
mcp-erp-bridge/
+-- README.md
+-- LICENSE
+-- pyproject.toml
+-- src/
|   +-- mcp_erp_bridge/
|       +-- __init__.py
|       +-- __main__.py
|       +-- server.py        # MCP server + tool registration
|       +-- erp_client.py    # HTTP client w/ cookie cache
|       +-- config.py        # endpoints, selectors, credentials
|       +-- schemas.py       # Pydantic models
|       +-- overtime.py      # overtime walk-back recovery logic
+-- examples/
|   +-- claude_desktop_config.json
|   +-- erp_config.example.json
|   +-- usage.md
+-- tests/
    +-- test_client.py       # login, cookie cache, 401 re-auth, parsing (mocked HTTP)
    +-- test_schemas.py      # input validation
    +-- test_overtime.py     # walk-back logic
```

## Tests

```bash
python -m pytest -q
```

The client tests run against `httpx.MockTransport`; no network, no real
system.

---

## Background

This is a reference implementation, not a product. The shape (a session-cookie
login, a CSRF token, HTML pages instead of an API, a handful of typed tools with
a deterministic core and a probabilistic edge) is the shape of most internal
enterprise tools, so anyone wrapping one can fork this and swap the selectors.
Every URL, field name, cookie name, and selector is a configurable placeholder;
none of them point at a real system.

## License

MIT (c) 2026 Rafael Garcia
