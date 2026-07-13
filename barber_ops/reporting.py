"""Weekly revenue rollup and gap analysis."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .config import ShopConfig
from .models import Booking
from .services import Service
from .slots import WEEKDAY_KEYS, free_windows


def revenue_rollup(
    bookings: list[Booking],
    services: dict[str, Service],
    week_start: date,
    as_of: datetime,
) -> dict:
    """Aggregate one week of bookings into revenue totals, counts, and per-service breakdown."""
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


def _overlap_minutes(s: datetime, e: datetime, lo: datetime, hi: datetime) -> int:
    start, end = max(s, lo), min(e, hi)
    return max(0, int((end - start).total_seconds() // 60))


def gap_analysis(
    bookings: list[Booking],
    cfg: ShopConfig,
    week_start: date,
    min_minutes: int = 60,
) -> dict:
    tz = ZoneInfo(cfg.timezone)
    noon = time(12, 0)
    per_day: list[dict] = []
    largest: dict | None = None
    quietest: dict | None = None
    for i in range(7):
        day = week_start + timedelta(days=i)
        weekday = WEEKDAY_KEYS[day.weekday()]
        hours = cfg.hours.get(weekday)
        if hours is None:
            per_day.append({
                "date": day.isoformat(), "weekday": weekday, "open": None, "close": None,
                "open_minutes": 0, "booked_minutes": 0, "utilization_pct": 0.0,
                "free_windows": [],
            })
            continue
        day_start = datetime.combine(day, hours.open, tzinfo=tz)
        day_end = datetime.combine(day, hours.close, tzinfo=tz)
        open_minutes = int((day_end - day_start).total_seconds() // 60)
        booked = sum(
            _overlap_minutes(b.start, b.end, day_start, day_end)
            for b in bookings
            if b.status != "cancelled" and b.start < day_end and b.end > day_start
        )
        all_gaps = free_windows(bookings, cfg, day, 0)
        windows = [
            {"start": s.isoformat(), "end": e.isoformat(),
             "minutes": int((e - s).total_seconds() // 60)}
            for s, e in all_gaps
            if (e - s) >= timedelta(minutes=min_minutes)
        ]
        for w in windows:
            if largest is None or w["minutes"] > largest["minutes"]:
                largest = {"date": day.isoformat(), **w}
        split = datetime.combine(day, noon, tzinfo=tz)
        dayparts = {
            "morning": sum(_overlap_minutes(s, e, day_start, min(split, day_end)) for s, e in all_gaps),
            "afternoon": sum(_overlap_minutes(s, e, max(split, day_start), day_end) for s, e in all_gaps),
        }
        for part, minutes in dayparts.items():
            if quietest is None or minutes > quietest["free_minutes"]:
                quietest = {"weekday": weekday, "daypart": part, "free_minutes": minutes}
        per_day.append({
            "date": day.isoformat(), "weekday": weekday,
            "open": hours.open.isoformat(timespec="minutes"),
            "close": hours.close.isoformat(timespec="minutes"),
            "open_minutes": open_minutes, "booked_minutes": booked,
            "utilization_pct": round(100 * booked / open_minutes, 1) if open_minutes else 0.0,
            "free_windows": windows,
        })
    return {"min_minutes": min_minutes, "per_day": per_day,
            "largest_gap": largest, "quietest_daypart": quietest}
