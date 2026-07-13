from datetime import date, datetime
from pathlib import Path

from barber_ops.models import Booking, normalize_events
from barber_ops.reporting import revenue_rollup
from barber_ops.services import load_services

ROOT = Path(__file__).resolve().parents[1]
AS_OF = datetime.fromisoformat("2026-07-12T09:00:00-04:00")


def _inputs(week_data):
    bookings, rejected = normalize_events(week_data["events"], week_data["timeZone"])
    assert rejected == []
    return bookings, load_services(ROOT / "data" / "services.yaml")


def test_rollup_week_totals(week_data):
    bookings, services = _inputs(week_data)
    r = revenue_rollup(bookings, services, date(2026, 7, 6), AS_OF)
    assert r["week_start"] == "2026-07-06"
    assert r["week_end"] == "2026-07-12"
    assert r["realized"] == 680
    assert r["missed"] == 90
    assert r["unconfirmed"] == 105
    assert r["upcoming"] == 0
    assert r["counts"] == {"showed": 16, "no_show": 3, "unconfirmed": 3, "cancelled": 1, "upcoming": 0}


def test_rollup_by_service(week_data):
    bookings, services = _inputs(week_data)
    r = revenue_rollup(bookings, services, date(2026, 7, 6), AS_OF)
    assert r["by_service"]["Fade"] == {"showed": 6, "revenue": 270}
    assert r["by_service"]["Cut + Beard"] == {"showed": 3, "revenue": 150}
    assert r["unknown_services"] == []


def test_rollup_upcoming_week(week_data):
    bookings, services = _inputs(week_data)
    r = revenue_rollup(bookings, services, date(2026, 7, 13), AS_OF)
    assert r["upcoming"] == 100
    assert r["counts"]["upcoming"] == 3
    assert r["realized"] == 0


def test_week_end_boundary_inclusive(week_data):
    bookings, services = _inputs(week_data)
    sunday = Booking(
        event_id="evt-sun", service="Haircut", customer="Sun D", marker="showed",
        start=datetime.fromisoformat("2026-07-12T07:00:00-04:00"),
        end=datetime.fromisoformat("2026-07-12T07:30:00-04:00"),
        status="confirmed", contact={},
    )
    next_monday = Booking(
        event_id="evt-nextmon", service="Haircut", customer="Mon D", marker="showed",
        start=datetime.fromisoformat("2026-07-13T10:00:00-04:00"),
        end=datetime.fromisoformat("2026-07-13T10:30:00-04:00"),
        status="confirmed", contact={},
    )
    r = revenue_rollup(bookings + [sunday, next_monday], services, date(2026, 7, 6), AS_OF)
    assert r["realized"] == 715  # 680 + Sunday's $35; Monday excluded
    assert r["counts"]["showed"] == 17


def test_unknown_service_reported_not_counted(week_data):
    bookings, services = _inputs(week_data)
    perm = Booking(
        event_id="evt-perm", service="Perm", customer="Q T", marker="showed",
        start=datetime.fromisoformat("2026-07-08T11:00:00-04:00"),
        end=datetime.fromisoformat("2026-07-08T12:00:00-04:00"),
        status="confirmed", contact={},
    )
    r = revenue_rollup(bookings + [perm], services, date(2026, 7, 6), AS_OF)
    assert r["unknown_services"] == [{"event_id": "evt-perm", "service": "Perm"}]
    assert r["realized"] == 680
