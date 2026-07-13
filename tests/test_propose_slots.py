import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "appointment-management" / "scripts" / "propose_slots.py"
FIXTURE = ROOT / "data" / "demo" / "week_fixture.json"


def run(*argv):
    return subprocess.run([sys.executable, str(SCRIPT), *argv], capture_output=True, text=True)


def test_fade_windows_next_two_days():
    r = run(str(FIXTURE), "--service", "Fade", "--from", "2026-07-13", "--to", "2026-07-14")
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["service"] == "Fade"
    assert out["duration_min"] == 45
    assert len(out["windows"]) == 4
    assert out["windows"][0] == {"start": "2026-07-13T09:00:00-04:00", "end": "2026-07-13T10:00:00-04:00"}
    assert out["windows"][3]["start"] == "2026-07-14T09:20:00-04:00"


def test_unknown_service_exits_2_with_menu():
    r = run(str(FIXTURE), "--service", "Perm", "--from", "2026-07-13", "--to", "2026-07-13")
    assert r.returncode == 2
    assert "known services" in r.stderr


def test_inverted_range_exits_2():
    r = run(str(FIXTURE), "--service", "Fade", "--from", "2026-07-14", "--to", "2026-07-13")
    assert r.returncode == 2
    assert "range" in r.stderr
