#!/usr/bin/env python3
"""Seed demo tenants and availability slots for local development and phone demos."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from db import init_db, seed_availability_slots, seed_tenant

# Demo timezone for spoken labels (US Central — matches portfolio owner)
DEMO_TZ = ZoneInfo("America/Chicago")

DAVE_HVAC = {
    "tenant_id": "daves-hvac",
    "business_name": "Dave's HVAC",
    "greeting": "Hi, thanks for calling Dave's HVAC. This is Mira. How can I help you today?",
    "hours": "Monday–Friday 7am–6pm, Saturday 8am–2pm. After-hours emergency line available.",
    "services": "HVAC repair, AC install, furnace service, emergency plumbing referrals",
    "service_area": "Greater Springfield and within 25 miles",
    "owner_sms_phone": "+15551234567",
    "owner_email": "dave@daves-hvac.example",
    "faq": [
        {"q": "What are your hours?", "a": "We're open Mon–Fri 7–6 and Sat 8–2."},
        {"q": "Do you offer emergency service?", "a": "Yes, we offer 24/7 emergency HVAC service."},
        {"q": "What areas do you serve?", "a": "Greater Springfield and within 25 miles."},
    ],
    "emergency_keywords": [
        "flooding",
        "flood",
        "gas leak",
        "no heat",
        "carbon monoxide",
        "water everywhere",
        "burst pipe",
    ],
}

PEST_PROS = {
    "tenant_id": "pest-pros",
    "business_name": "Pest Pros Exterminating",
    "greeting": "Thanks for calling Pest Pros. This is Mira. How can I help you today?",
    "hours": "Monday–Saturday 8am–6pm. Emergency pest response available after hours.",
    "services": "Ant, rodent, and termite treatment, bed bug removal, wildlife exclusion",
    "service_area": "Metro area and suburbs within 30 miles",
    "owner_sms_phone": "+15559876543",
    "owner_email": "dispatch@pestpros.example",
    "faq": [
        {"q": "Do you handle bed bugs?", "a": "Yes, we offer full bed bug inspection and treatment."},
        {"q": "Are your treatments pet safe?", "a": "We use pet-safe options whenever possible."},
        {"q": "How soon can someone come out?", "a": "Same-day for urgent issues when slots are open."},
    ],
    "emergency_keywords": [
        "wasps",
        "hornet",
        "swarm",
        "snake",
        "raccoon",
        "infestation",
        "bed bugs everywhere",
    ],
}

MIKES_PLUMBING = {
    "tenant_id": "mikes-plumbing",
    "business_name": "Mike's Plumbing",
    "greeting": "Mike's Plumbing, this is Mira speaking. What can I help you with?",
    "hours": "Monday–Friday 7am–7pm, 24/7 emergency line for active leaks.",
    "services": "Leak repair, drain cleaning, water heater install, sewer line service",
    "service_area": "City and surrounding county",
    "owner_sms_phone": "+15552223333",
    "owner_email": "mike@mikesplumbing.example",
    "faq": [
        {"q": "Do you offer emergency service?", "a": "Yes, 24/7 for active leaks and burst pipes."},
        {"q": "What are your rates?", "a": "We provide upfront estimates before work begins."},
        {"q": "Do you install water heaters?", "a": "Yes, repair and full replacement."},
    ],
    "emergency_keywords": [
        "burst pipe",
        "flooding",
        "water everywhere",
        "sewage",
        "no water",
        "active leak",
        "water damage",
    ],
}

ALL_DEMO_TENANTS = [DAVE_HVAC, PEST_PROS, MIKES_PLUMBING]

# Phone IVR: one Twilio number, caller presses 1/2/3
IVR_TENANT_MAP: dict[str, str] = {
    "1": DAVE_HVAC["tenant_id"],
    "2": PEST_PROS["tenant_id"],
    "3": MIKES_PLUMBING["tenant_id"],
}

IVR_PROMPT = (
    "Welcome to the Mira AI receptionist demo. "
    "Press 1 for Dave's HVAC, 2 for Pest Pros, or 3 for Mike's Plumbing."
)

# Weekday morning / afternoon windows (local demo TZ)
_SLOT_HOURS = (9, 13)


def _format_clock(local_start: datetime) -> str:
    hour = local_start.hour % 12 or 12
    ampm = "A.M." if local_start.hour < 12 else "P.M."
    return f"{hour} {ampm}"


def _spoken_label(local_start: datetime, today: datetime) -> str:
    period = "morning" if local_start.hour < 12 else "afternoon"
    clock = _format_clock(local_start)
    day_delta = (local_start.date() - today.date()).days
    if day_delta == 0:
        day_part = "today"
    elif day_delta == 1:
        day_part = "tomorrow"
    else:
        day_part = local_start.strftime("%A")
    return f"{day_part} {period} at {clock}"


def build_availability_slots(
    *,
    days_ahead: int = 7,
    now: datetime | None = None,
) -> list[dict[str, str]]:
    """Generate open weekday slots for the next N days."""
    local_now = now.astimezone(DEMO_TZ) if now else datetime.now(DEMO_TZ)
    today = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    slots: list[dict[str, str]] = []

    for day_offset in range(0, days_ahead + 1):
        day = today + timedelta(days=day_offset)
        if day.weekday() >= 5:  # skip Sat/Sun
            continue
        for hour in _SLOT_HOURS:
            start_local = day.replace(hour=hour, minute=0)
            if start_local <= local_now:
                continue
            end_local = start_local + timedelta(hours=2)
            start_utc = start_local.astimezone(timezone.utc)
            end_utc = end_local.astimezone(timezone.utc)
            slot_id = start_utc.strftime("%Y-%m-%dT%H:%M")
            slots.append(
                {
                    "slot_id": slot_id,
                    "starts_at": start_utc.replace(microsecond=0).isoformat(),
                    "ends_at": end_utc.replace(microsecond=0).isoformat(),
                    "label": _spoken_label(start_local, today),
                    "status": "open",
                }
            )
    return slots


def main() -> None:
    init_db()
    slots = build_availability_slots()
    for tenant in ALL_DEMO_TENANTS:
        seed_tenant(tenant)
        seed_availability_slots(tenant["tenant_id"], slots)
        print(
            f"Seeded tenant: {tenant['business_name']} ({tenant['tenant_id']}) "
            f"with {len(slots)} open slots"
        )


if __name__ == "__main__":
    main()
