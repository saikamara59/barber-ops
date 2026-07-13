import importlib.util
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("seed_calendar", ROOT / "tools" / "seed_calendar.py")
seed_calendar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seed_calendar)


def test_shift_events_moves_week(week_data):
    shifted = seed_calendar.shift_events(week_data["events"], date(2026, 7, 20))
    assert shifted[0]["start"]["dateTime"] == "2026-07-20T09:00:00-04:00"
    assert shifted[-1]["start"]["dateTime"] == "2026-07-28T09:00:00-04:00"
    assert len(shifted) == len(week_data["events"])


def test_shift_events_does_not_mutate_input(week_data):
    before = week_data["events"][0]["start"]["dateTime"]
    seed_calendar.shift_events(week_data["events"], date(2026, 7, 20))
    assert week_data["events"][0]["start"]["dateTime"] == before
