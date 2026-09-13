"""Configuration: credentials, endpoint paths, and HTML selectors.

Every ERP renders its pages differently. Nothing in the client is
hardcoded to one system: the login form, the session cookie name, the
work-order detail selectors and the list-table selectors all come from
``ErpConfig``. Defaults are deliberately generic placeholders; override
them with a JSON file (``ERP_CONFIG_FILE``) that matches your ERP.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, fields, replace
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Endpoints:
    """Relative paths on the ERP. ``work_order`` is a format string."""

    login: str = "/login"
    work_order: str = "/wo/{wo_number}"
    work_order_search: str = "/wo/search"
    work_order_note: str = "/wo/note"


@dataclass(frozen=True)
class Selectors:
    """CSS selectors and form field names. Adapt per ERP."""

    # login form
    csrf_input: str = 'input[name="csrf_token"]'
    csrf_form_field: str = "csrf_token"
    username_field: str = "username"
    password_field: str = "password"
    session_cookie: str = "session"

    # work-order detail page: output key -> CSS selector
    detail_fields: dict[str, str] = field(
        default_factory=lambda: {
            "status": "#wo-status",
            "technician": "#wo-technician",
            "scheduled": "#wo-scheduled",
            "nte": "#wo-nte",
            "customer": "#wo-customer",
            "location": "#wo-location",
            "description": "#wo-description",
            "parent_wo": "#wo-parent",
        }
    )

    # work-order list page
    list_rows: str = "table.wo-list tbody tr"
    list_number_cell: str = "td.wo-num"
    list_status_cell: str = "td.wo-status"
    pending_statuses: tuple[str, ...] = ("PENDING DISPATCH", "IN PROGRESS")

    # note submission form
    note_field_prefix: str = "closeout_"
    note_type_field: str = "note_type"
    note_type_value: str = "CLOSEOUT"
    note_wo_field: str = "wo_number"


@dataclass(frozen=True)
class ErpConfig:
    base_url: str
    username: str
    password: str
    endpoints: Endpoints = field(default_factory=Endpoints)
    selectors: Selectors = field(default_factory=Selectors)

    @classmethod
    def from_env(cls, config_file: str | os.PathLike[str] | None = None) -> "ErpConfig":
        """Build from ``ERP_BASE_URL`` / ``ERP_USERNAME`` / ``ERP_PASSWORD``.

        If ``config_file`` (or ``ERP_CONFIG_FILE``) points at a JSON file,
        its ``endpoints`` and ``selectors`` objects are merged over the
        defaults. See ``examples/erp_config.example.json``.
        """
        base_url = (os.getenv("ERP_BASE_URL") or "").rstrip("/")
        username = os.getenv("ERP_USERNAME") or ""
        password = os.getenv("ERP_PASSWORD") or ""
        cfg = cls(base_url=base_url, username=username, password=password)

        path = config_file or os.getenv("ERP_CONFIG_FILE")
        if path:
            cfg = cfg.with_overrides(json.loads(Path(path).read_text(encoding="utf-8")))
        return cfg

    def with_overrides(self, data: dict[str, Any]) -> "ErpConfig":
        """Return a copy with ``endpoints`` / ``selectors`` keys merged in."""
        endpoints = _merge(self.endpoints, data.get("endpoints", {}))
        selectors = _merge(self.selectors, data.get("selectors", {}))
        return replace(self, endpoints=endpoints, selectors=selectors)

    @property
    def is_complete(self) -> bool:
        return bool(self.base_url and self.username and self.password)


def _merge(obj: Any, overrides: dict[str, Any]) -> Any:
    """Shallow-merge a dict of overrides into a frozen dataclass."""
    known = {f.name for f in fields(obj)}
    unknown = set(overrides) - known
    if unknown:
        raise ValueError(
            f"Unknown config keys for {type(obj).__name__}: {sorted(unknown)}"
        )
    clean: dict[str, Any] = {}
    for k, v in overrides.items():
        current = getattr(obj, k)
        if isinstance(current, dict) and isinstance(v, dict):
            clean[k] = {**current, **v}
        elif isinstance(current, tuple) and isinstance(v, list):
            clean[k] = tuple(v)
        else:
            clean[k] = v
    return replace(obj, **clean)
