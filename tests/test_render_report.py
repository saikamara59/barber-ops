import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "skills" / "weekly-summary" / "scripts" / "weekly_summary.py"
RENDER = ROOT / "skills" / "weekly-summary" / "scripts" / "render_report.py"
FIXTURE = ROOT / "data" / "demo" / "week_fixture.json"


def _report():
    s = subprocess.run(
        [sys.executable, str(SUMMARY), str(FIXTURE),
         "--week-start", "2026-07-06", "--as-of", "2026-07-12T09:00:00-04:00"],
        capture_output=True, text=True, check=True,
    )
    r = subprocess.run([sys.executable, str(RENDER)], capture_output=True, text=True, input=s.stdout)
    assert r.returncode == 0, r.stderr
    return r.stdout


def test_report_headline_numbers():
    md = _report()
    assert "# Sharp Cuts Barbershop" in md
    assert "$680" in md
    assert "$90" in md
    assert "$105" in md
    assert "| Fade | 6 | $270 |" in md


def test_report_gap_and_actions():
    md = _report()
    assert "Tue Jul 7" in md
    assert "6h 0m" in md
    assert "## Suggested actions" in md
    assert "appointment-management" in md
    assert "Tuesday afternoon" in md
