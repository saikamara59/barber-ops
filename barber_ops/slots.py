"""Free-window math over bookings and business hours."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .config import ShopConfig
from .models import Booking

WEEKDAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def free_windows(
    bookings: list[Booking], cfg: ShopConfig, day: date, min_minutes: int
) -> list[tuple[datetime, datetime]]:
    hours = cfg.hours.get(WEEKDAY_KEYS[day.weekday()])
    if hours is None:
        return []
    tz = ZoneInfo(cfg.timezone)
    day_start = datetime.combine(day, hours.open, tzinfo=tz)
    day_end = datetime.combine(day, hours.close, tzinfo=tz)
    busy = sorted(
        (max(b.start, day_start), min(b.end, day_end))
        for b in bookings
        if b.status != "cancelled" and b.start < day_end and b.end > day_start
    )
    windows: list[tuple[datetime, datetime]] = []
    cursor = day_start
    for start, end in busy:
        if start > cursor:
            windows.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < day_end:
        windows.append((cursor, day_end))
    need = timedelta(minutes=min_minutes)
    return [(s, e) for s, e in windows if e - s > need]


def windows_for_range(
    bookings: list[Booking], cfg: ShopConfig, first_day: date, last_day: date, min_minutes: int
) -> list[tuple[datetime, datetime]]:
    out: list[tuple[datetime, datetime]] = []
    day = first_day
    while day <= last_day:
        out.extend(free_windows(bookings, cfg, day, min_minutes))
        day += timedelta(days=1)
    return out
