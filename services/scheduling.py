"""Candidate appointment slots — computed from per-tenant scheduling rules."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

# Defaults when a tenant has no / partial scheduling config
DEMO_TZ = ZoneInfo("America/Chicago")
DEFAULT_DAYS_AHEAD = 14
DEFAULT_WEEKDAYS = (0, 1, 2, 3, 4)  # Mon–Fri
DEFAULT_SLOT_HOURS = (9, 13)
DEFAULT_SLOT_DURATION_HOURS = 2


def _format_clock(local_start: datetime) -> str:
    hour = local_start.hour % 12 or 12
    ampm = "A.M." if local_start.hour < 12 else "P.M."
    return f"{hour} {ampm}"


def spoken_label(local_start: datetime, today: datetime) -> str:
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


def resolve_scheduling(scheduling: dict[str, Any] | None = None) -> dict[str, Any]:
    """Merge tenant scheduling with defaults."""
    cfg = scheduling or {}
    tz_name = cfg.get("timezone") or "America/Chicago"
    weekdays = cfg.get("weekdays")
    slot_hours = cfg.get("slot_hours")
    return {
        "timezone": ZoneInfo(tz_name),
        "days_ahead": int(cfg.get("days_ahead") or DEFAULT_DAYS_AHEAD),
        "weekdays": tuple(weekdays) if weekdays is not None else DEFAULT_WEEKDAYS,
        "slot_hours": tuple(slot_hours) if slot_hours is not None else DEFAULT_SLOT_HOURS,
        "slot_duration_hours": int(
            cfg.get("slot_duration_hours") or DEFAULT_SLOT_DURATION_HOURS
        ),
    }


def build_candidate_slots(
    *,
    scheduling: dict[str, Any] | None = None,
    days_ahead: int | None = None,
    now: datetime | None = None,
) -> list[dict[str, str]]:
    """Generate open candidate slots from scheduling rules."""
    resolved = resolve_scheduling(scheduling)
    if days_ahead is not None:
        resolved["days_ahead"] = days_ahead

    tz: ZoneInfo = resolved["timezone"]
    local_now = now.astimezone(tz) if now else datetime.now(tz)
    today = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    slots: list[dict[str, str]] = []
    duration = timedelta(hours=resolved["slot_duration_hours"])

    for day_offset in range(0, resolved["days_ahead"] + 1):
        day = today + timedelta(days=day_offset)
        if day.weekday() not in resolved["weekdays"]:
            continue
        for hour in resolved["slot_hours"]:
            start_local = day.replace(hour=int(hour), minute=0)
            if start_local <= local_now:
                continue
            end_local = start_local + duration
            start_utc = start_local.astimezone(timezone.utc)
            end_utc = end_local.astimezone(timezone.utc)
            slot_id = start_utc.strftime("%Y-%m-%dT%H:%M")
            slots.append(
                {
                    "slot_id": slot_id,
                    "starts_at": start_utc.replace(microsecond=0).isoformat(),
                    "ends_at": end_utc.replace(microsecond=0).isoformat(),
                    "label": spoken_label(start_local, today),
                }
            )
    return slots


def get_candidate_slot(
    slot_id: str,
    *,
    scheduling: dict[str, Any] | None = None,
    days_ahead: int | None = None,
    now: datetime | None = None,
) -> dict[str, str] | None:
    """Return a candidate slot by id, or None if outside the bookable window."""
    for slot in build_candidate_slots(
        scheduling=scheduling, days_ahead=days_ahead, now=now
    ):
        if slot["slot_id"] == slot_id:
            return slot
    return None
