import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "appointment-management" / "scripts" / "detect_no_shows.py"
FIXTURE = ROOT / "data" / "demo" / "week_fixture.json"
AS_OF = "2026-07-12T09:00:00-04:00"


def run(*argv, stdin=None):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *argv], capture_output=True, text=True, input=stdin
    )


def test_classifies_fixture_week():
    r = run(str(FIXTURE), "--as-of", AS_OF)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert [b["customer"] for b in out["confirmed"]] == ["Alan R", "Chris O", "Ethan Q"]
    assert [b["customer"] for b in out["candidates"]] == ["Nick D", "Jordan F", "Rob T"]
    assert out["rejected"] == []


def test_reads_stdin():
    r = run("--as-of", AS_OF, stdin=FIXTURE.read_text())
    assert r.returncode == 0, r.stderr
    assert len(json.loads(r.stdout)["confirmed"]) == 3


def test_malformed_event_reported_not_dropped():
    payload = {
        "timeZone": "America/New_York",
        "events": [{"id": "evt-bad", "summary": "Staff meeting", "start": {"dateTime": "2026-07-06T09:00:00-04:00"}, "end": {"dateTime": "2026-07-06T10:00:00-04:00"}, "status": "confirmed"}],
    }
    r = run("--as-of", AS_OF, stdin=json.dumps(payload))
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["rejected"][0]["event_id"] == "evt-bad"


def test_naive_as_of_rejected():
    r = run(str(FIXTURE), "--as-of", "2026-07-12T09:00:00")
    assert r.returncode == 2
    assert "UTC offset" in r.stderr
