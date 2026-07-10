"""DynamoDB persistence for Mira tenants, sessions, leads, and notifications."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import boto3
from botocore.exceptions import ClientError

_TABLE_SUFFIXES = (
    "tenants",
    "sessions",
    "leads",
    "notifications",
    "tool-calls",
    "call-records",
    "ws-connections",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def get_table_prefix() -> str:
    return os.environ.get("MIRA_TABLE_PREFIX", "mira").strip() or "mira"


def table_name(suffix: str) -> str:
    return f"{get_table_prefix()}-{suffix}"


def _get_region() -> str:
    return os.environ.get("AWS_REGION", "us-east-1").strip() or "us-east-1"


def _resource():
    return boto3.resource("dynamodb", region_name=_get_region())


def _client():
    return boto3.client("dynamodb", region_name=_get_region())


def init_db() -> None:
    client = _client()
    missing: list[str] = []
    for suffix in _TABLE_SUFFIXES:
        name = table_name(suffix)
        try:
            client.describe_table(TableName=name)
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ResourceNotFoundException":
                missing.append(name)
            else:
                raise
    if missing:
        names = ", ".join(missing)
        raise RuntimeError(
            f"DynamoDB table(s) not found: {names}. "
            "Run: cd infra && npm install && npx cdk bootstrap && npx cdk deploy"
        )


def get_tenant(tenant_id: str) -> dict[str, Any] | None:
    table = _resource().Table(table_name("tenants"))
    response = table.get_item(Key={"tenant_id": tenant_id})
    item = response.get("Item")
    if not item:
        return None
    tenant = dict(item)
    tenant["faq"] = json.loads(tenant.pop("faq_json", "[]"))
    tenant["emergency_keywords"] = json.loads(
        tenant.pop("emergency_keywords", "[]")
    )
    return tenant


def seed_tenant(tenant: dict[str, Any]) -> None:
    table = _resource().Table(table_name("tenants"))
    table.put_item(
        Item={
            "tenant_id": tenant["tenant_id"],
            "business_name": tenant["business_name"],
            "greeting": tenant["greeting"],
            "hours": tenant["hours"],
            "services": tenant["services"],
            "service_area": tenant["service_area"],
            "faq_json": json.dumps(tenant.get("faq", [])),
            "owner_sms_phone": tenant.get("owner_sms_phone"),
            "owner_email": tenant.get("owner_email"),
            "emergency_keywords": json.dumps(tenant.get("emergency_keywords", [])),
        }
    )


def save_session_state(
    session_id: str,
    tenant_id: str,
    state: dict[str, Any],
    messages: list[dict[str, Any]],
) -> None:
    table = _resource().Table(table_name("sessions"))
    now = _utc_now()
    existing = table.get_item(Key={"session_id": session_id}).get("Item")
    table.put_item(
        Item={
            "session_id": session_id,
            "tenant_id": tenant_id,
            "state_json": json.dumps(state),
            "messages_json": json.dumps(messages),
            "created_at": existing.get("created_at", now) if existing else now,
            "updated_at": now,
        }
    )


def load_session_state(
    session_id: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]] | None:
    table = _resource().Table(table_name("sessions"))
    item = table.get_item(Key={"session_id": session_id}).get("Item")
    if not item:
        return None
    return json.loads(item["state_json"]), json.loads(item["messages_json"])


def get_session_created_at(session_id: str) -> str | None:
    table = _resource().Table(table_name("sessions"))
    item = table.get_item(Key={"session_id": session_id}).get("Item")
    return item.get("created_at") if item else None


def get_session_tenant_id(session_id: str) -> str | None:
    table = _resource().Table(table_name("sessions"))
    item = table.get_item(Key={"session_id": session_id}).get("Item")
    return item.get("tenant_id") if item else None


def upsert_lead(
    session_id: str,
    tenant_id: str,
    fields: dict[str, Any],
) -> dict[str, Any]:
    table = _resource().Table(table_name("leads"))
    existing = table.get_item(Key={"session_id": session_id}).get("Item") or {}
    merged = dict(existing)
    merged.update({k: v for k, v in fields.items() if v is not None})
    merged.update(
        {
            "session_id": session_id,
            "tenant_id": tenant_id,
            "updated_at": _utc_now(),
        }
    )
    table.put_item(Item=merged)
    return dict(merged)


def get_lead(session_id: str) -> dict[str, Any] | None:
    table = _resource().Table(table_name("leads"))
    item = table.get_item(Key={"session_id": session_id}).get("Item")
    return dict(item) if item else None


def log_notification(
    tenant_id: str,
    session_id: str | None,
    message: str,
    channel: str = "mock_sms",
) -> int:
    notification_id = str(uuid.uuid4())
    table = _resource().Table(table_name("notifications"))
    table.put_item(
        Item={
            "notification_id": notification_id,
            "tenant_id": tenant_id,
            "session_id": session_id or "",
            "message": message,
            "channel": channel,
            "created_at": _utc_now(),
        }
    )
    return hash(notification_id) % (2**31)


def count_notifications(session_id: str) -> int:
    table = _resource().Table(table_name("notifications"))
    response = table.query(
        IndexName="session-index",
        KeyConditionExpression="session_id = :sid",
        ExpressionAttributeValues={":sid": session_id},
        Select="COUNT",
    )
    return int(response.get("Count", 0))


def log_tool_call(session_id: str, tool_name: str, args: dict[str, Any]) -> None:
    table = _resource().Table(table_name("tool-calls"))
    now = _utc_now()
    table.put_item(
        Item={
            "session_id": session_id,
            "sk": f"{now}#{tool_name}",
            "tool_name": tool_name,
            "args_json": json.dumps(args),
            "created_at": now,
        }
    )


def get_tool_calls(session_id: str) -> list[str]:
    table = _resource().Table(table_name("tool-calls"))
    response = table.query(
        KeyConditionExpression="session_id = :sid",
        ExpressionAttributeValues={":sid": session_id},
        ScanIndexForward=True,
    )
    return [item["tool_name"] for item in response.get("Items", [])]


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
    table = _resource().Table(table_name("call-records"))
    ended_at = _utc_now()
    item = {
        "call_id": call_id,
        "tenant_id": tenant_id,
        "transcript": transcript,
        "summary": summary,
        "lead_json": json.dumps(lead),
        "urgency": urgency or lead.get("urgency"),
        "intent": intent or lead.get("intent"),
        "started_at": started_at,
        "ended_at": ended_at,
    }
    table.put_item(Item=item)
    record = dict(item)
    record["lead"] = lead
    record.pop("lead_json")
    return record


def get_call_record(call_id: str) -> dict[str, Any] | None:
    table = _resource().Table(table_name("call-records"))
    item = table.get_item(Key={"call_id": call_id}).get("Item")
    if not item:
        return None
    record = dict(item)
    record["lead"] = json.loads(record.pop("lead_json", "{}"))
    return record


def list_call_records(tenant_id: str, limit: int = 20) -> list[dict[str, Any]]:
    table = _resource().Table(table_name("call-records"))
    response = table.query(
        IndexName="tenant-index",
        KeyConditionExpression="tenant_id = :tid",
        ExpressionAttributeValues={":tid": tenant_id},
        ScanIndexForward=False,
        Limit=limit,
    )
    records: list[dict[str, Any]] = []
    for item in response.get("Items", []):
        record = dict(item)
        record["lead"] = json.loads(record.pop("lead_json", "{}"))
        records.append(record)
    return records


def put_ws_connection(
    connection_id: str,
    *,
    session_id: str,
    tenant_id: str,
    ttl_seconds: int = 86400,
) -> None:
    import time

    table = _resource().Table(table_name("ws-connections"))
    table.put_item(
        Item={
            "connection_id": connection_id,
            "session_id": session_id,
            "tenant_id": tenant_id,
            "created_at": _utc_now(),
            "ttl": int(time.time()) + ttl_seconds,
        }
    )


def get_ws_connection(connection_id: str) -> dict[str, Any] | None:
    table = _resource().Table(table_name("ws-connections"))
    item = table.get_item(Key={"connection_id": connection_id}).get("Item")
    return dict(item) if item else None


def delete_ws_connection(connection_id: str) -> None:
    table = _resource().Table(table_name("ws-connections"))
    table.delete_item(Key={"connection_id": connection_id})
