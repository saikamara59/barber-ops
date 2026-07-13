import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "appointment-management" / "scripts" / "draft_followup.py"

ALAN = {
    "event_id": "evt-003", "service": "Haircut", "customer": "Alan R", "marker": "no-show",
    "start": "2026-07-06T13:00:00-04:00", "end": "2026-07-06T13:30:00-04:00",
    "status": "confirmed", "contact": {"phone": "(555) 010-1003"},
}
NO_CONTACT = dict(ALAN, event_id="evt-x", customer="Ghost B", contact={})


def run(payload):
    return subprocess.run(
        [sys.executable, str(SCRIPT)], capture_output=True, text=True, input=json.dumps(payload)
    )


def test_rebook_drafts_sms():
    r = run({"mode": "rebook", "channel_preference": "sms", "bookings": [ALAN]})
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["skipped"] == []
    assert out["drafts"][0]["channel"] == "sms"
    assert out["drafts"][0]["to"] == "(555) 010-1003"
    assert "Alan" in out["drafts"][0]["body"]


def test_falls_back_to_other_channel():
    r = run({"mode": "rebook", "channel_preference": "email", "bookings": [ALAN]})
    out = json.loads(r.stdout)
    assert out["drafts"][0]["channel"] == "sms"  # no email on file, falls back


def test_no_contact_is_skipped_with_reason():
    r = run({"mode": "rebook", "channel_preference": "sms", "bookings": [ALAN, NO_CONTACT]})
    out = json.loads(r.stdout)
    assert len(out["drafts"]) == 1
    assert out["skipped"] == [{"event_id": "evt-x", "reason": "no contact info for Ghost B"}]


def test_reschedule_confirmation():
    r = run({
        "mode": "reschedule", "channel_preference": "sms",
        "booking": ALAN, "new_start": "2026-07-14T10:00:00-04:00",
    })
    out = json.loads(r.stdout)
    assert "Tue Jul 14 at 10:00 AM" in out["drafts"][0]["body"]


def test_reschedule_booking_missing_key_exits_2():
    incomplete = {k: v for k, v in ALAN.items() if k != "end"}
    r = run({
        "mode": "reschedule", "channel_preference": "sms",
        "booking": incomplete, "new_start": "2026-07-14T10:00:00-04:00",
    })
    assert r.returncode == 2
    assert "required" in r.stderr


def test_bad_mode_exits_2():
    r = run({"mode": "send-everything", "bookings": []})
    assert r.returncode == 2
    assert "mode" in r.stderr


def test_bad_channel_preference_exits_2():
    r = run({"mode": "rebook", "channel_preference": "fax", "bookings": [ALAN]})
    assert r.returncode == 2
    assert "channel_preference" in r.stderr


def test_naive_new_start_exits_2():
    r = run({
        "mode": "reschedule", "channel_preference": "sms",
        "booking": ALAN, "new_start": "2026-07-14T10:00:00",
    })
    assert r.returncode == 2
    assert "UTC offset" in r.stderr
