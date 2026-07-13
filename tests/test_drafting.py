from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from barber_ops.config import load_config
from barber_ops.drafting import format_slot, render_rebook_draft, render_reschedule_confirmation
from barber_ops.models import Booking

ROOT = Path(__file__).resolve().parents[1]
TZ = ZoneInfo("America/New_York")


def _booking(contact):
    return Booking(
        event_id="evt-003", service="Haircut", customer="Alan R", marker="no-show",
        start=datetime(2026, 7, 6, 13, 0, tzinfo=TZ), end=datetime(2026, 7, 6, 13, 30, tzinfo=TZ),
        status="confirmed", contact=contact,
    )


def _cfg():
    return load_config(ROOT / "data" / "config.yaml")


def test_format_slot():
    assert format_slot(datetime(2026, 7, 14, 14, 0, tzinfo=TZ)) == "Tue Jul 14 at 2:00 PM"
    assert format_slot(datetime(2026, 7, 6, 9, 30, tzinfo=TZ)) == "Mon Jul 6 at 9:30 AM"


def test_rebook_sms():
    draft = render_rebook_draft(_booking({"phone": "(555) 010-1003"}), _cfg(), "sms")
    assert draft.channel == "sms"
    assert draft.to == "(555) 010-1003"
    assert draft.subject is None
    assert "Alan" in draft.body
    assert "Haircut" in draft.body
    assert "Sharp Cuts Barbershop" in draft.body
    assert "Mon Jul 6" in draft.body


def test_rebook_email_has_subject():
    draft = render_rebook_draft(_booking({"email": "alan@example.com"}), _cfg(), "email")
    assert draft.channel == "email"
    assert draft.to == "alan@example.com"
    assert draft.subject == "Let's get you rescheduled at Sharp Cuts Barbershop"


def test_missing_contact_raises():
    with pytest.raises(ValueError, match="no email on file"):
        render_rebook_draft(_booking({"phone": "(555) 010-1003"}), _cfg(), "email")


def test_reschedule_confirmation():
    new_start = datetime(2026, 7, 14, 10, 0, tzinfo=TZ)
    draft = render_reschedule_confirmation(_booking({"phone": "(555) 010-1003"}), new_start, _cfg(), "sms")
    assert "Tue Jul 14 at 10:00 AM" in draft.body
    assert "confirmed" in draft.body.lower()
