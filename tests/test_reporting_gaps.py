from datetime import date
from pathlib import Path

from barber_ops.config import load_config
from barber_ops.models import normalize_events
from barber_ops.reporting import gap_analysis

ROOT = Path(__file__).resolve().parents[1]


def _gaps(week_data, min_minutes=60):
    bookings, rejected = normalize_events(week_data["events"], week_data["timeZone"])
    assert rejected == []
    cfg = load_config(ROOT / "data" / "config.yaml")
    return gap_analysis(bookings, cfg, date(2026, 7, 6), min_minutes)


def test_largest_gap_is_tuesday_afternoon(week_data):
    g = _gaps(week_data)
    assert g["largest_gap"]["date"] == "2026-07-07"
    assert g["largest_gap"]["minutes"] == 360
    assert g["largest_gap"]["start"].endswith("T12:00:00-04:00")


def test_quietest_daypart(week_data):
    g = _gaps(week_data)
    assert g["quietest_daypart"] == {"weekday": "tue", "daypart": "afternoon", "free_minutes": 360}


def test_per_day_utilization(week_data):
    g = _gaps(week_data)
    by_day = {d["weekday"]: d for d in g["per_day"]}
    assert by_day["mon"]["booked_minutes"] == 125
    assert by_day["mon"]["utilization_pct"] == 23.1
    assert by_day["tue"]["utilization_pct"] == 16.7
    assert by_day["wed"]["booked_minutes"] == 180  # cancelled Luis G excluded
    assert by_day["sat"]["open_minutes"] == 480
    assert by_day["sun"]["open"] is None
    assert by_day["sun"]["utilization_pct"] == 0.0


def test_min_minutes_filters_windows(week_data):
    g = _gaps(week_data, min_minutes=60)
    tue = next(d for d in g["per_day"] if d["weekday"] == "tue")
    assert [w["minutes"] for w in tue["free_windows"]] == [60, 360]
