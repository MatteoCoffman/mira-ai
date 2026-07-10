#!/usr/bin/env python3
"""Seed demo tenants for local development and phone demos."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from db import init_db, seed_tenant

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
    "scheduling": {
        "timezone": "America/Chicago",
        "days_ahead": 14,
        "weekdays": [0, 1, 2, 3, 4],
        "slot_hours": [9, 13],
        "slot_duration_hours": 2,
    },
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
    "scheduling": {
        "timezone": "America/Chicago",
        "days_ahead": 14,
        "weekdays": [0, 1, 2, 3, 4, 5],
        "slot_hours": [10, 14],
        "slot_duration_hours": 2,
    },
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
    "scheduling": {
        "timezone": "America/Chicago",
        "days_ahead": 14,
        "weekdays": [0, 1, 2, 3, 4],
        "slot_hours": [8, 11, 15],
        "slot_duration_hours": 2,
    },
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


def main() -> None:
    init_db()
    for tenant in ALL_DEMO_TENANTS:
        seed_tenant(tenant)
        print(f"Seeded tenant: {tenant['business_name']} ({tenant['tenant_id']})")


if __name__ == "__main__":
    main()
