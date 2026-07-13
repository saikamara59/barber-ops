from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from barber_ops.models import Booking, normalize_events, parse_contact, parse_summary

TZ = "America/New_York"


def _event(**overrides):
    ev = {
        "id": "evt-x",
        "summary": "Fade — Marcus J [showed]",
        "description": "phone: (555) 010-1001\nemail: marcus@example.com",
        "start": {"dateTime": "2026-07-06T10:00:00-04:00"},
        "end": {"dateTime": "2026-07-06T10:45:00-04:00"},
        "status": "confirmed",
    }
    ev.update(overrides)
    return ev


def test_parse_summary_variants():
    assert parse_summary("Fade — Marcus J [showed]") == ("Fade", "Marcus J", "showed")
    assert parse_summary("Haircut — Nick D") == ("Haircut", "Nick D", None)
    assert parse_summary("Beard Trim — Chris O [no-show]") == ("Beard Trim", "Chris O", "no-show")


def test_parse_summary_rejects_bad_format():
    with pytest.raises(ValueError):
        parse_summary("Team meeting")
    with pytest.raises(ValueError):
        parse_summary(" — Marcus J")


def test_parse_contact():
    assert parse_contact("phone: (555) 010-1001\nemail: m@example.com") == {
        "phone": "(555) 010-1001",
        "email": "m@example.com",
    }
    assert parse_contact(None) == {}


def test_normalize_happy_path_and_roundtrip():
    bookings, rejected = normalize_events([_event()], TZ)
    assert rejected == []
    b = bookings[0]
    assert (b.service, b.customer, b.marker) == ("Fade", "Marcus J", "showed")
    assert b.start == datetime(2026, 7, 6, 10, 0, tzinfo=ZoneInfo(TZ))
    assert Booking.from_dict(b.to_dict()) == b


def test_naive_datetime_gets_default_tz():
    ev = _event(start={"dateTime": "2026-07-06T10:00:00"}, end={"dateTime": "2026-07-06T10:45:00"})
    bookings, rejected = normalize_events([ev], TZ)
    assert rejected == []
    assert bookings[0].start.utcoffset() is not None


def test_all_day_and_inverted_events_rejected():
    all_day = _event(id="evt-a", start={"date": "2026-07-06"}, end={"date": "2026-07-07"})
    inverted = _event(id="evt-b", start={"dateTime": "2026-07-06T11:00:00-04:00"})
    bookings, rejected = normalize_events([all_day, inverted], TZ)
    assert bookings == []
    assert [r["event_id"] for r in rejected] == ["evt-a", "evt-b"]
    assert all(r["reason"] for r in rejected)


def test_cancelled_event_kept_with_status():
    bookings, _ = normalize_events([_event(status="cancelled")], TZ)
    assert bookings[0].status == "cancelled"
