"""Read-only owner console API for the Mira portfolio website."""

from __future__ import annotations

import hmac
import os
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from db import get_tenant, list_appointments, list_call_records
from scripts.seed import ALL_DEMO_TENANTS

router = APIRouter(prefix="/owner", tags=["owner"])


def require_owner_key(
    x_mira_owner_key: Annotated[str | None, Header(alias="X-Mira-Owner-Key")] = None,
) -> None:
    expected = os.environ.get("MIRA_OWNER_API_KEY", "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="Owner API key is not configured")
    provided = (x_mira_owner_key or "").strip()
    if not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing owner API key")


@router.get("/tenants")
def owner_list_tenants(_: None = Depends(require_owner_key)) -> dict:
    tenants = []
    for seeded in ALL_DEMO_TENANTS:
        row = get_tenant(seeded["tenant_id"]) or seeded
        tenants.append(
            {
                "tenant_id": row["tenant_id"],
                "business_name": row.get("business_name", seeded["business_name"]),
            }
        )
    return {"tenants": tenants}


@router.get("/tenants/{tenant_id}/calls")
def owner_list_calls(
    tenant_id: str,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    _: None = Depends(require_owner_key),
) -> dict:
    if not get_tenant(tenant_id):
        raise HTTPException(status_code=404, detail=f"Tenant not found: {tenant_id}")
    return {"tenant_id": tenant_id, "calls": list_call_records(tenant_id, limit=limit)}


@router.get("/tenants/{tenant_id}/appointments")
def owner_list_appointments(
    tenant_id: str,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    _: None = Depends(require_owner_key),
) -> dict:
    if not get_tenant(tenant_id):
        raise HTTPException(status_code=404, detail=f"Tenant not found: {tenant_id}")
    return {
        "tenant_id": tenant_id,
        "appointments": list_appointments(tenant_id, limit=limit),
    }
