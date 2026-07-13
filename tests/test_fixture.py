from barber_ops.models import normalize_events


def test_fixture_is_fully_normalizable(week_data):
    bookings, rejected = normalize_events(week_data["events"], week_data["timeZone"])
    assert rejected == []
    assert len(bookings) == 26
    assert sum(1 for b in bookings if b.marker == "no-show") == 3
    assert sum(1 for b in bookings if b.marker == "showed") == 16
    assert sum(1 for b in bookings if b.status == "cancelled") == 1
