#!/usr/bin/env python3
"""Seed Dave's HVAC tenant for local development."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from db.sqlite import init_db, seed_tenant

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


def main() -> None:
    init_db()
    seed_tenant(DAVE_HVAC)
    print(f"Seeded tenant: {DAVE_HVAC['business_name']} ({DAVE_HVAC['tenant_id']})")


if __name__ == "__main__":
    main()
