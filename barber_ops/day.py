"""Day-sheet math: today's lineup, now/next, and walk-in windows."""
from __future__ import annotations

from datetime import date, datetime

from .config import ShopConfig
from .models import Booking
from .services import Service
from .slots import WEEKDAY_KEYS, free_windows


def _appt(b: Booking) -> dict:
    return {
        "start": b.start.isoformat(),
        "end": b.end.isoformat(),
        "service": b.service,
        "customer": b.customer,
        "duration_min": int((b.end - b.start).total_seconds() // 60),
        "status": b.status,
        "marker": b.marker,
    }


def build_day_sheet(
    bookings: list[Booking],
    cfg: ShopConfig,
    services: dict[str, Service],
    day: date,
    as_of: datetime,
) -> dict:
    weekday = WEEKDAY_KEYS[day.weekday()]
    hours = cfg.hours.get(weekday)
    base = {"shop_name": cfg.shop_name, "date": day.isoformat(), "weekday": weekday}
    if hours is None:
        return {**base, "closed": True, "open": None, "close": None,
                "appointments": [], "booked_minutes": 0, "now": None, "next": None,
                "walkin_windows": []}

    todays = sorted(
        (b for b in bookings if b.status != "cancelled" and b.start.date() == day),
        key=lambda b: b.start,
    )
    booked_minutes = sum(int((b.end - b.start).total_seconds() // 60) for b in todays)
    in_chair = next((b for b in todays if b.start <= as_of < b.end), None)
    upcoming = next((b for b in todays if b.start > as_of), None)

    min_duration = min(s.duration_min for s in services.values())
    windows = []
    for s, e in free_windows(bookings, cfg, day, min_duration):
        if e <= as_of:
            continue
        start = max(s, as_of)
        minutes = int((e - start).total_seconds() // 60)
        if minutes < min_duration:
            continue
        fits = sorted(svc.name for svc in services.values() if svc.duration_min <= minutes)
        windows.append({
            "start": start.isoformat(), "end": e.isoformat(), "minutes": minutes,
            "fits": fits, "fits_all": len(fits) == len(services),
        })

    return {
        **base, "closed": False,
        "open": hours.open.isoformat(timespec="minutes"),
        "close": hours.close.isoformat(timespec="minutes"),
        "appointments": [_appt(b) for b in todays],
        "booked_minutes": booked_minutes,
        "now": _appt(in_chair) if in_chair else None,
        "next": _appt(upcoming) if upcoming else None,
        "walkin_windows": windows,
    }
