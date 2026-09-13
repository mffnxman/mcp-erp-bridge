"""HTTP client for a session-cookie-authenticated enterprise ERP.

Handles session-cookie + CSRF auth with a SQLite cookie cache so we re-auth
at most once per session window rather than once per call.

Endpoint paths, form field names, and HTML selectors all come from
``ErpConfig`` (see ``config.py``). Nothing here is tied to one vendor's
markup: point the config at your own ERP and the client adapts.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from bs4 import BeautifulSoup

from .config import ErpConfig

log = logging.getLogger(__name__)


class ErpAuthError(RuntimeError):
    """Raised when authentication against the ERP fails."""


class ErpClient:
    """A thin async HTTP client for a session-cookie-auth ERP."""

    DEFAULT_CACHE_DIR = Path.home() / ".cache" / "mcp_erp_bridge"
    COOKIE_TTL_HOURS = 12

    def __init__(
        self,
        config: ErpConfig | None = None,
        *,
        cache_dir: Path | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.config = config or ErpConfig.from_env()
        if not self.config.is_complete:
            raise ErpAuthError("Set ERP_BASE_URL, ERP_USERNAME, ERP_PASSWORD.")

        self.cache_dir = cache_dir or self.DEFAULT_CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._db = self.cache_dir / "cookies.db"
        self._init_db()

        self._transport = transport  # injectable for tests (httpx.MockTransport)
        self._client: httpx.AsyncClient | None = None

    # -- Lifecycle ---------------------------------------------------------

    async def __aenter__(self) -> "ErpClient":
        self._client = httpx.AsyncClient(
            base_url=self.config.base_url,
            timeout=httpx.Timeout(30.0, connect=10.0),
            follow_redirects=True,
            transport=self._transport,
        )
        await self._restore_or_login()
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self._client:
            await self._client.aclose()
        self._client = None

    # -- Public API --------------------------------------------------------

    async def get_work_order(self, wo_number: str) -> dict[str, Any]:
        """Fetch one work order by number. Re-auths once on 401."""
        assert self._client is not None
        url = self.config.endpoints.work_order.format(wo_number=wo_number)
        for attempt in range(2):
            resp = await self._client.get(url)
            if resp.status_code == 401 and attempt == 0:
                log.info("session expired, re-authing")
                await self._login()
                continue
            resp.raise_for_status()
            return self._parse_wo_html(resp.text, wo_number)
        raise ErpAuthError("Auth failed twice; aborting.")

    async def list_pending(self, manager: str | None = None) -> list[dict[str, Any]]:
        """List pending + in-progress work orders, optionally filtered by manager."""
        assert self._client is not None
        sel = self.config.selectors
        params: dict[str, str] = {"status": ",".join(sel.pending_statuses)}
        if manager:
            params["manager"] = manager
        resp = await self._client.get(
            self.config.endpoints.work_order_search, params=params
        )
        resp.raise_for_status()
        return self._parse_wo_list(resp.text)

    async def add_closeout_note(
        self, wo_number: str, fields: dict[str, Any]
    ) -> dict[str, Any]:
        """Submit a fully-validated close-out note. All required fields must be present."""
        assert self._client is not None
        sel = self.config.selectors
        payload = {f"{sel.note_field_prefix}{k}": str(v) for k, v in fields.items()}
        payload[sel.note_wo_field] = wo_number
        payload[sel.note_type_field] = sel.note_type_value
        resp = await self._client.post(
            self.config.endpoints.work_order_note, data=payload
        )
        resp.raise_for_status()
        return {"note_id": str(resp.json().get("id")), "success": True}

    # -- Internals ---------------------------------------------------------

    async def _restore_or_login(self) -> None:
        cookie = self._read_cookie()
        if cookie and not self._cookie_expired(cookie):
            assert self._client is not None
            self._client.cookies.set(
                self.config.selectors.session_cookie, cookie["value"]
            )
            log.debug("restored session cookie from cache")
            return
        await self._login()

    async def _login(self) -> None:
        assert self._client is not None
        sel = self.config.selectors
        ep = self.config.endpoints

        # Step 1 - fetch login page for CSRF token.
        resp = await self._client.get(ep.login)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        token_input = soup.select_one(sel.csrf_input)
        if not token_input:
            raise ErpAuthError("Could not find CSRF token on login page.")
        csrf = token_input["value"]

        # Step 2 - submit credentials.
        resp = await self._client.post(
            ep.login,
            data={
                sel.username_field: self.config.username,
                sel.password_field: self.config.password,
                sel.csrf_form_field: csrf,
            },
        )
        if resp.status_code >= 400:
            raise ErpAuthError(f"Login failed: HTTP {resp.status_code}")

        # Step 3 - persist session cookie.
        session = self._client.cookies.get(sel.session_cookie)
        if not session:
            raise ErpAuthError("Login appeared to succeed but no session cookie set.")
        self._write_cookie(session)
        log.info("login OK; cookie cached")

    def _init_db(self) -> None:
        with sqlite3.connect(self._db) as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS cookies (
                    name TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    saved_at TEXT NOT NULL
                )
                """)

    def _write_cookie(self, value: str) -> None:
        with sqlite3.connect(self._db) as con:
            con.execute(
                "REPLACE INTO cookies (name, value, saved_at) VALUES (?, ?, ?)",
                ("session", value, datetime.utcnow().isoformat()),
            )

    def _read_cookie(self) -> dict[str, str] | None:
        with sqlite3.connect(self._db) as con:
            row = con.execute(
                "SELECT value, saved_at FROM cookies WHERE name = 'session'"
            ).fetchone()
        if not row:
            return None
        return {"value": row[0], "saved_at": row[1]}

    def _cookie_expired(self, cookie: dict[str, str]) -> bool:
        saved = datetime.fromisoformat(cookie["saved_at"])
        return datetime.utcnow() - saved > timedelta(hours=self.COOKIE_TTL_HOURS)

    # -- HTML parsing (selector-driven; adapt via ErpConfig) ---------------

    def _parse_wo_html(self, html: str, wo_number: str) -> dict[str, Any]:
        soup = BeautifulSoup(html, "html.parser")
        sel = self.config.selectors
        out: dict[str, Any] = {"number": wo_number}
        for key, css in sel.detail_fields.items():
            out[key] = self._extract(soup, css)
        out["status"] = out.get("status") or "Unknown"
        for key in ("customer", "location", "description"):
            out[key] = out.get(key) or ""
        out["closeout_fields"] = {}
        return out

    def _parse_wo_list(self, html: str) -> list[dict[str, Any]]:
        soup = BeautifulSoup(html, "html.parser")
        sel = self.config.selectors
        out: list[dict[str, Any]] = []
        for r in soup.select(sel.list_rows):
            num_el = r.select_one(sel.list_number_cell)
            status_el = r.select_one(sel.list_status_cell)
            out.append(
                {
                    "number": num_el.get_text(strip=True) if num_el else "",
                    "status": status_el.get_text(strip=True) if status_el else "",
                }
            )
        return out

    @staticmethod
    def _extract(soup: BeautifulSoup, css: str) -> str | None:
        el = soup.select_one(css)
        return el.get_text(strip=True) if el else None
