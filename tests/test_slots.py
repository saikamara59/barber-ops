from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from barber_ops.config import load_config
from barber_ops.models import normalize_events
from barber_ops.slots import free_windows, windows_for_range

ROOT = Path(__file__).resolve().parents[1]
TZ = ZoneInfo("America/New_York")


def _bookings(week_data):
    bookings, rejected = normalize_events(week_data["events"], week_data["timeZone"])
    assert rejected == []
    return bookings


def _cfg():
    return load_config(ROOT / "data" / "config.yaml")


def test_free_windows_monday_fade(week_data):
    # Mon Jul 13: busy 10:00-10:45 and 14:00-14:30, hours 09:00-18:00.
    windows = free_windows(_bookings(week_data), _cfg(), date(2026, 7, 13), 45)
    assert windows == [
        (datetime(2026, 7, 13, 9, 0, tzinfo=TZ), datetime(2026, 7, 13, 10, 0, tzinfo=TZ)),
        (datetime(2026, 7, 13, 10, 45, tzinfo=TZ), datetime(2026, 7, 13, 14, 0, tzinfo=TZ)),
        (datetime(2026, 7, 13, 14, 30, tzinfo=TZ), datetime(2026, 7, 13, 18, 0, tzinfo=TZ)),
    ]


def test_exact_fit_window_included(week_data):
    # Design needs 60 min; the 09:00-10:00 window is exactly 60 min and qualifies.
    windows = free_windows(_bookings(week_data), _cfg(), date(2026, 7, 13), 60)
    assert windows[0] == (datetime(2026, 7, 13, 9, 0, tzinfo=TZ), datetime(2026, 7, 13, 10, 0, tzinfo=TZ))
    assert len(windows) == 3


def test_window_too_short_for_service_excluded(week_data):
    # A 90-min need excludes the 60-min 09:00-10:00 window.
    windows = free_windows(_bookings(week_data), _cfg(), date(2026, 7, 13), 90)
    assert windows[0][0] == datetime(2026, 7, 13, 10, 45, tzinfo=TZ)
    assert len(windows) == 2


def test_closed_day_has_no_windows(week_data):
    assert free_windows(_bookings(week_data), _cfg(), date(2026, 7, 12), 30) == []


def test_cancelled_bookings_do_not_block(week_data):
    # Wed Jul 8: Luis G 14:00-14:30 is cancelled, so 13:00-16:00 is one free window.
    windows = free_windows(_bookings(week_data), _cfg(), date(2026, 7, 8), 30)
    assert (datetime(2026, 7, 8, 13, 0, tzinfo=TZ), datetime(2026, 7, 8, 16, 0, tzinfo=TZ)) in windows


def test_windows_for_range(week_data):
    windows = windows_for_range(_bookings(week_data), _cfg(), date(2026, 7, 13), date(2026, 7, 14), 45)
    assert len(windows) == 4  # 3 on Mon + 1 on Tue (09:20-18:00)
    assert windows[-1][0] == datetime(2026, 7, 14, 9, 20, tzinfo=TZ)
