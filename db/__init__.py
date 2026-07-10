"""Database backend router — DynamoDB (default) or SQLite (tests)."""

from __future__ import annotations

import os
from typing import Any

_IMPL = None

_PUBLIC_NAMES = (
    "count_notifications",
    "get_call_record",
    "get_lead",
    "get_session_created_at",
    "get_session_tenant_id",
    "get_tenant",
    "get_tool_calls",
    "init_db",
    "list_call_records",
    "load_session_state",
    "log_notification",
    "log_tool_call",
    "save_call_record",
    "save_session_state",
    "seed_tenant",
    "upsert_lead",
)


def _backend() -> str:
    return os.environ.get("MIRA_DB_BACKEND", "dynamodb").strip().lower()


def _impl():
    global _IMPL
    backend = _backend()
    if backend == "sqlite":
        if _IMPL is None or _IMPL.__name__ != "db.sqlite":
            import db.sqlite as mod

            _IMPL = mod
        return _IMPL
    if backend == "dynamodb":
        if _IMPL is None or _IMPL.__name__ != "db.dynamodb":
            import db.dynamodb as mod

            _IMPL = mod
        return _IMPL
    raise ValueError(
        f"Unknown MIRA_DB_BACKEND={backend!r}. Use 'dynamodb' or 'sqlite'."
    )


def __getattr__(name: str) -> Any:
    if name in _PUBLIC_NAMES:
        return getattr(_impl(), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = list(_PUBLIC_NAMES)
