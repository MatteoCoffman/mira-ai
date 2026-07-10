"""SQLite persistence for Mira tenants, sessions, leads, and notifications."""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator

def get_db_path() -> Path:
    configured = os.environ.get("MIRA_DB_PATH", "").strip()
    return Path(configured) if configured else Path(".mira/mira.db")


@contextmanager
def get_connection() -> Generator[sqlite3.Connection, None, None]:
    path = get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tenants (
                tenant_id TEXT PRIMARY KEY,
                business_name TEXT NOT NULL,
                greeting TEXT NOT NULL,
                hours TEXT NOT NULL,
                services TEXT NOT NULL,
                service_area TEXT NOT NULL,
                faq_json TEXT NOT NULL DEFAULT '[]',
                owner_sms_phone TEXT,
                owner_email TEXT,
                emergency_keywords TEXT NOT NULL DEFAULT '[]'
            );

            CREATE TABLE IF NOT EXISTS call_sessions (
                session_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
                state_json TEXT NOT NULL DEFAULT '{}',
                messages_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS leads (
                session_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
                caller_name TEXT,
                phone TEXT,
                address TEXT,
                urgency TEXT,
                reason TEXT,
                intent TEXT,
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
                session_id TEXT,
                message TEXT NOT NULL,
                channel TEXT NOT NULL DEFAULT 'mock_sms',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS tool_calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                args_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS call_records (
                call_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
                transcript TEXT NOT NULL,
                summary TEXT NOT NULL,
                lead_json TEXT NOT NULL DEFAULT '{}',
                urgency TEXT,
                intent TEXT,
                started_at TEXT,
                ended_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS ws_connections (
                connection_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """
        )


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


def get_tenant(tenant_id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM tenants WHERE tenant_id = ?", (tenant_id,)
        ).fetchone()
    tenant = row_to_dict(row)
    if tenant:
        tenant["faq"] = json.loads(tenant.pop("faq_json"))
        tenant["emergency_keywords"] = json.loads(tenant.pop("emergency_keywords"))
    return tenant


def save_session_state(
    session_id: str,
    tenant_id: str,
    state: dict[str, Any],
    messages: list[dict[str, Any]],
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO call_sessions (session_id, tenant_id, state_json, messages_json)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                state_json = excluded.state_json,
                messages_json = excluded.messages_json,
                updated_at = datetime('now')
            """,
            (session_id, tenant_id, json.dumps(state), json.dumps(messages)),
        )


def load_session_state(session_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]] | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT state_json, messages_json FROM call_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    if row is None:
        return None
    return json.loads(row["state_json"]), json.loads(row["messages_json"])


def get_session_created_at(session_id: str) -> str | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT created_at FROM call_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    return row["created_at"] if row else None


def get_session_tenant_id(session_id: str) -> str | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT tenant_id FROM call_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    return row["tenant_id"] if row else None


def upsert_lead(
    session_id: str,
    tenant_id: str,
    fields: dict[str, Any],
) -> dict[str, Any]:
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT * FROM leads WHERE session_id = ?", (session_id,)
        ).fetchone()
        merged = dict(row_to_dict(existing) or {})
        merged.update({k: v for k, v in fields.items() if v is not None})
        conn.execute(
            """
            INSERT INTO leads (
                session_id, tenant_id, caller_name, phone, address,
                urgency, reason, intent, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(session_id) DO UPDATE SET
                caller_name = COALESCE(excluded.caller_name, leads.caller_name),
                phone = COALESCE(excluded.phone, leads.phone),
                address = COALESCE(excluded.address, leads.address),
                urgency = COALESCE(excluded.urgency, leads.urgency),
                reason = COALESCE(excluded.reason, leads.reason),
                intent = COALESCE(excluded.intent, leads.intent),
                updated_at = datetime('now')
            """,
            (
                session_id,
                tenant_id,
                merged.get("caller_name"),
                merged.get("phone"),
                merged.get("address"),
                merged.get("urgency"),
                merged.get("reason"),
                merged.get("intent"),
            ),
        )
        row = conn.execute(
            "SELECT * FROM leads WHERE session_id = ?", (session_id,)
        ).fetchone()
    return row_to_dict(row) or {}


def get_lead(session_id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM leads WHERE session_id = ?", (session_id,)
        ).fetchone()
    return row_to_dict(row)


def log_notification(
    tenant_id: str,
    session_id: str | None,
    message: str,
    channel: str = "mock_sms",
) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO notifications (tenant_id, session_id, message, channel)
            VALUES (?, ?, ?, ?)
            """,
            (tenant_id, session_id, message, channel),
        )
        return int(cursor.lastrowid)


def log_tool_call(session_id: str, tool_name: str, args: dict[str, Any]) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO tool_calls (session_id, tool_name, args_json)
            VALUES (?, ?, ?)
            """,
            (session_id, tool_name, json.dumps(args)),
        )


def get_tool_calls(session_id: str) -> list[str]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT tool_name FROM tool_calls WHERE session_id = ? ORDER BY id",
            (session_id,),
        ).fetchall()
    return [row["tool_name"] for row in rows]


def count_notifications(session_id: str) -> int:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM notifications WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    return int(row["cnt"]) if row else 0


def seed_tenant(tenant: dict[str, Any]) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO tenants (
                tenant_id, business_name, greeting, hours, services,
                service_area, faq_json, owner_sms_phone, owner_email,
                emergency_keywords
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(tenant_id) DO UPDATE SET
                business_name = excluded.business_name,
                greeting = excluded.greeting,
                hours = excluded.hours,
                services = excluded.services,
                service_area = excluded.service_area,
                faq_json = excluded.faq_json,
                owner_sms_phone = excluded.owner_sms_phone,
                owner_email = excluded.owner_email,
                emergency_keywords = excluded.emergency_keywords
            """,
            (
                tenant["tenant_id"],
                tenant["business_name"],
                tenant["greeting"],
                tenant["hours"],
                tenant["services"],
                tenant["service_area"],
                json.dumps(tenant.get("faq", [])),
                tenant.get("owner_sms_phone"),
                tenant.get("owner_email"),
                json.dumps(tenant.get("emergency_keywords", [])),
            ),
        )


def save_call_record(
    call_id: str,
    tenant_id: str,
    transcript: str,
    summary: str,
    lead: dict[str, Any],
    *,
    urgency: str | None = None,
    intent: str | None = None,
    started_at: str | None = None,
) -> dict[str, Any]:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO call_records (
                call_id, tenant_id, transcript, summary, lead_json,
                urgency, intent, started_at, ended_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(call_id) DO UPDATE SET
                transcript = excluded.transcript,
                summary = excluded.summary,
                lead_json = excluded.lead_json,
                urgency = excluded.urgency,
                intent = excluded.intent,
                ended_at = datetime('now')
            """,
            (
                call_id,
                tenant_id,
                transcript,
                summary,
                json.dumps(lead),
                urgency or lead.get("urgency"),
                intent or lead.get("intent"),
                started_at,
            ),
        )
        row = conn.execute(
            "SELECT * FROM call_records WHERE call_id = ?", (call_id,)
        ).fetchone()
    record = row_to_dict(row) or {}
    if record:
        record["lead"] = json.loads(record.pop("lead_json", "{}"))
    return record


def get_call_record(call_id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM call_records WHERE call_id = ?", (call_id,)
        ).fetchone()
    record = row_to_dict(row)
    if record:
        record["lead"] = json.loads(record.pop("lead_json"))
    return record


def list_call_records(tenant_id: str, limit: int = 20) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM call_records
            WHERE tenant_id = ?
            ORDER BY ended_at DESC
            LIMIT ?
            """,
            (tenant_id, limit),
        ).fetchall()
    records = []
    for row in rows:
        record = row_to_dict(row)
        if record:
            record["lead"] = json.loads(record.pop("lead_json"))
            records.append(record)
    return records


def put_ws_connection(
    connection_id: str,
    *,
    session_id: str,
    tenant_id: str,
    ttl_seconds: int = 86400,
) -> None:
    del ttl_seconds  # SQLite tests don't need TTL
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO ws_connections (connection_id, session_id, tenant_id)
            VALUES (?, ?, ?)
            ON CONFLICT(connection_id) DO UPDATE SET
                session_id = excluded.session_id,
                tenant_id = excluded.tenant_id
            """,
            (connection_id, session_id, tenant_id),
        )


def get_ws_connection(connection_id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM ws_connections WHERE connection_id = ?",
            (connection_id,),
        ).fetchone()
    return row_to_dict(row)


def delete_ws_connection(connection_id: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM ws_connections WHERE connection_id = ?",
            (connection_id,),
        )
