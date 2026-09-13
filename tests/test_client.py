"""ErpClient against httpx.MockTransport: login, cookie cache, 401 re-auth,
selector-driven parsing, close-out note payload. No network."""

from __future__ import annotations

import asyncio
import sqlite3
from urllib.parse import parse_qs

import httpx

from mcp_erp_bridge.config import ErpConfig
from mcp_erp_bridge.erp_client import ErpClient

LOGIN_HTML = '<form><input name="csrf_token" value="tok-1"></form>'
DETAIL_HTML = """
<div id="wo-status">In Progress</div>
<div id="wo-technician">Doe, Jane</div>
<div id="wo-nte">850.00</div>
<div id="wo-customer">Acme Retail Co</div>
"""
LIST_HTML = """
<table class="wo-list"><tbody>
<tr><td class="wo-num">11111111</td><td class="wo-status">PENDING DISPATCH</td></tr>
<tr><td class="wo-num">22222222</td><td class="wo-status">IN PROGRESS</td></tr>
</tbody></table>
"""


class FakeErp:
    """Records requests and plays the role of a cookie-auth web app."""

    def __init__(self, *, first_detail_401: bool = False):
        self.calls: list[tuple[str, str]] = []
        self.posted: list[dict[str, list[str]]] = []
        self.first_detail_401 = first_detail_401

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.calls.append((request.method, path))
        if path == "/login" and request.method == "GET":
            return httpx.Response(200, text=LOGIN_HTML)
        if path == "/login" and request.method == "POST":
            self.posted.append(parse_qs(request.content.decode()))
            return httpx.Response(200, headers={"set-cookie": "session=abc123; Path=/"})
        if path.startswith("/wo/search"):
            return httpx.Response(200, text=LIST_HTML)
        if path == "/wo/note":
            self.posted.append(parse_qs(request.content.decode()))
            return httpx.Response(200, json={"id": 987})
        if path.startswith("/wo/"):
            if self.first_detail_401:
                self.first_detail_401 = False
                return httpx.Response(401)
            return httpx.Response(200, text=DETAIL_HTML)
        return httpx.Response(404)


def make_config(**overrides) -> ErpConfig:
    cfg = ErpConfig(base_url="https://erp.example.com", username="u", password="p")
    return cfg.with_overrides(overrides) if overrides else cfg


def run(coro):
    return asyncio.run(coro)


def test_login_posts_credentials_with_csrf_and_caches_cookie(tmp_path):
    erp = FakeErp()

    async def go():
        async with ErpClient(
            make_config(),
            cache_dir=tmp_path,
            transport=httpx.MockTransport(erp.handler),
        ):
            pass

    run(go())
    assert erp.calls[:2] == [("GET", "/login"), ("POST", "/login")]
    assert erp.posted[0] == {
        "username": ["u"],
        "password": ["p"],
        "csrf_token": ["tok-1"],
    }
    row = (
        sqlite3.connect(tmp_path / "cookies.db")
        .execute("SELECT value FROM cookies WHERE name='session'")
        .fetchone()
    )
    assert row == ("abc123",)


def test_cached_cookie_skips_login(tmp_path):
    erp = FakeErp()

    async def go():
        async with ErpClient(
            make_config(),
            cache_dir=tmp_path,
            transport=httpx.MockTransport(erp.handler),
        ):
            pass
        async with ErpClient(
            make_config(),
            cache_dir=tmp_path,
            transport=httpx.MockTransport(erp.handler),
        ) as c:
            return await c.get_work_order("12345678")

    wo = run(go())
    assert wo["status"] == "In Progress"
    assert erp.calls.count(("POST", "/login")) == 1  # second client reused the cookie


def test_get_work_order_reauths_once_on_401(tmp_path):
    erp = FakeErp(first_detail_401=True)

    async def go():
        async with ErpClient(
            make_config(),
            cache_dir=tmp_path,
            transport=httpx.MockTransport(erp.handler),
        ) as c:
            return await c.get_work_order("12345678")

    wo = run(go())
    assert wo["technician"] == "Doe, Jane"
    assert wo["closeout_fields"] == {}
    assert wo["location"] == ""  # missing selector -> empty string, not None
    assert erp.calls.count(("POST", "/login")) == 2
    assert erp.calls.count(("GET", "/wo/12345678")) == 2


def test_list_pending_parses_rows_and_sends_statuses(tmp_path):
    erp = FakeErp()

    async def go():
        async with ErpClient(
            make_config(),
            cache_dir=tmp_path,
            transport=httpx.MockTransport(erp.handler),
        ) as c:
            return await c.list_pending(manager="Doe, Jane")

    rows = run(go())
    assert [r["number"] for r in rows] == ["11111111", "22222222"]
    assert rows[1]["status"] == "IN PROGRESS"


def test_add_closeout_note_uses_prefix_and_note_type(tmp_path):
    erp = FakeErp()

    async def go():
        async with ErpClient(
            make_config(),
            cache_dir=tmp_path,
            transport=httpx.MockTransport(erp.handler),
        ) as c:
            return await c.add_closeout_note(
                "12345678", {"job_code": "PLUMB-LEAK", "completion": "Y"}
            )

    result = run(go())
    assert result == {"note_id": "987", "success": True}
    note = erp.posted[-1]
    assert note["closeout_job_code"] == ["PLUMB-LEAK"]
    assert note["closeout_completion"] == ["Y"]
    assert note["note_type"] == ["CLOSEOUT"]
    assert note["wo_number"] == ["12345678"]


def test_selectors_and_endpoints_are_configurable(tmp_path):
    """A system with different markup: different cookie name, detail ids, prefix."""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/signin" and request.method == "GET":
            return httpx.Response(200, text='<input name="__token" value="x">')
        if request.url.path == "/signin":
            return httpx.Response(200, headers={"set-cookie": "SID=zzz; Path=/"})
        if request.url.path == "/orders/777777":
            return httpx.Response(200, text='<span class="state">Closed</span>')
        return httpx.Response(404)

    cfg = make_config(
        endpoints={"login": "/signin", "work_order": "/orders/{wo_number}"},
        selectors={
            "csrf_input": 'input[name="__token"]',
            "csrf_form_field": "__token",
            "session_cookie": "SID",
            "detail_fields": {"status": "span.state"},
        },
    )

    async def go():
        async with ErpClient(
            cfg, cache_dir=tmp_path, transport=httpx.MockTransport(handler)
        ) as c:
            return await c.get_work_order("777777")

    wo = run(go())
    assert wo["status"] == "Closed"
    assert wo["technician"] is None  # default selector still present, not found
    assert calls == ["/signin", "/signin", "/orders/777777"]
