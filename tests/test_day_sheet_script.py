import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "day-sheet" / "scripts" / "day_sheet.py"
FIXTURE = ROOT / "data" / "demo" / "week_fixture.json"
MORNING = "2026-07-13T08:00:00-04:00"


def run(*argv):
    return subprocess.run([sys.executable, str(SCRIPT), *argv], capture_output=True, text=True)


def test_json_output():
    r = run(str(FIXTURE), "--date", "2026-07-13", "--as-of", MORNING)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert len(out["appointments"]) == 2
    assert out["next"]["customer"] == "Marcus J"
    assert out["rejected"] == []


def test_text_output_monday():
    r = run(str(FIXTURE), "--date", "2026-07-13", "--as-of", MORNING, "--format", "text")
    assert r.returncode == 0, r.stderr
    assert "TODAY AT SHARP CUTS BARBERSHOP — Mon Jul 13" in r.stdout
    assert "2 appointments · 1h 15m booked" in r.stdout
    assert "10:00 AM  Fade — Marcus J (45m)" in r.stdout
    assert "Next up: Marcus J at 10:00 AM (Fade)" in r.stdout
    assert "9:00 AM–10:00 AM (1h 0m) — any service" in r.stdout


def test_text_output_closed_day():
    r = run(str(FIXTURE), "--date", "2026-07-12", "--as-of", MORNING, "--format", "text")
    assert r.returncode == 0, r.stderr
    assert "Closed today." in r.stdout


def test_naive_as_of_rejected():
    r = run(str(FIXTURE), "--date", "2026-07-13", "--as-of", "2026-07-13T08:00:00")
    assert r.returncode == 2
    assert "UTC offset" in r.stderr


def test_bad_date_rejected():
    r = run(str(FIXTURE), "--date", "July 13", "--as-of", MORNING)
    assert r.returncode == 2
    assert "date" in r.stderr
