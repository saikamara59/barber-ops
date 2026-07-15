from datetime import date, datetime
from pathlib import Path

from barber_ops.config import load_config
from barber_ops.day import build_day_sheet
from barber_ops.models import normalize_events
from barber_ops.services import load_services

ROOT = Path(__file__).resolve().parents[1]
MORNING = datetime.fromisoformat("2026-07-13T08:00:00-04:00")


def _sheet(week_data, day, as_of):
    bookings, rejected = normalize_events(week_data["events"], week_data["timeZone"])
    assert rejected == []
    cfg = load_config(ROOT / "data" / "config.yaml")
    services = load_services(ROOT / "data" / "services.yaml")
    return build_day_sheet(bookings, cfg, services, day, as_of)


def test_monday_morning_sheet(week_data):
    s = _sheet(week_data, date(2026, 7, 13), MORNING)
    assert s["closed"] is False
    assert [a["customer"] for a in s["appointments"]] == ["Marcus J", "Devon P"]
    assert s["booked_minutes"] == 75
    assert s["now"] is None
    assert s["next"]["customer"] == "Marcus J"
    assert [w["minutes"] for w in s["walkin_windows"]] == [60, 195, 210]
    assert all(w["fits_all"] for w in s["walkin_windows"])


def test_midday_clips_current_window(week_data):
    s = _sheet(week_data, date(2026, 7, 13), datetime.fromisoformat("2026-07-13T13:30:00-04:00"))
    w = s["walkin_windows"][0]
    assert w["start"] == "2026-07-13T13:30:00-04:00"
    assert w["minutes"] == 30
    assert w["fits"] == ["Beard Trim", "Haircut", "Kids Cut"]
    assert w["fits_all"] is False
    assert s["next"]["customer"] == "Devon P"


def test_in_the_chair(week_data):
    s = _sheet(week_data, date(2026, 7, 13), datetime.fromisoformat("2026-07-13T10:15:00-04:00"))
    assert s["now"]["customer"] == "Marcus J"
    assert s["now"]["end"] == "2026-07-13T10:45:00-04:00"
    assert s["next"]["customer"] == "Devon P"


def test_closed_day(week_data):
    s = _sheet(week_data, date(2026, 7, 12), MORNING)
    assert s["closed"] is True
    assert s["appointments"] == []
    assert s["walkin_windows"] == []
