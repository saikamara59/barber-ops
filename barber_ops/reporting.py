"""Weekly revenue rollup and gap analysis."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from .models import Booking
from .services import Service


def revenue_rollup(
    bookings: list[Booking],
    services: dict[str, Service],
    week_start: date,
    as_of: datetime,
) -> dict:
    first, last = week_start, week_start + timedelta(days=6)
    totals = {"realized": 0, "missed": 0, "unconfirmed": 0, "upcoming": 0}
    counts = {"showed": 0, "no_show": 0, "unconfirmed": 0, "cancelled": 0, "upcoming": 0}
    by_service: dict[str, dict] = {}
    unknown: list[dict] = []
    for b in bookings:
        if not (first <= b.start.date() <= last):
            continue
        if b.status == "cancelled":
            counts["cancelled"] += 1
            continue
        svc = services.get(b.service.strip().lower())
        if svc is None:
            unknown.append({"event_id": b.event_id, "service": b.service})
            continue
        if b.end >= as_of:
            counts["upcoming"] += 1
            totals["upcoming"] += svc.price
        elif b.marker == "showed":
            counts["showed"] += 1
            totals["realized"] += svc.price
            entry = by_service.setdefault(svc.name, {"showed": 0, "revenue": 0})
            entry["showed"] += 1
            entry["revenue"] += svc.price
        elif b.marker == "no-show":
            counts["no_show"] += 1
            totals["missed"] += svc.price
        else:
            counts["unconfirmed"] += 1
            totals["unconfirmed"] += svc.price
    return {
        "week_start": first.isoformat(),
        "week_end": last.isoformat(),
        **totals,
        "counts": counts,
        "by_service": by_service,
        "unknown_services": unknown,
    }
