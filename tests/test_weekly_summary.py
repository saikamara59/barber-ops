import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "weekly-summary" / "scripts" / "weekly_summary.py"
FIXTURE = ROOT / "data" / "demo" / "week_fixture.json"
AS_OF = "2026-07-12T09:00:00-04:00"


def run(*argv, stdin=None):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *argv], capture_output=True, text=True, input=stdin
    )


def test_summary_on_fixture():
    r = run(str(FIXTURE), "--week-start", "2026-07-06", "--as-of", AS_OF)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["shop_name"] == "Sharp Cuts Barbershop"
    assert out["revenue"]["realized"] == 680
    assert out["gaps"]["largest_gap"]["minutes"] == 360
    assert out["rejected"] == []


def test_reads_stdin():
    r = run("--week-start", "2026-07-06", "--as-of", AS_OF, stdin=FIXTURE.read_text())
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["revenue"]["missed"] == 90


def test_naive_as_of_rejected():
    r = run(str(FIXTURE), "--week-start", "2026-07-06", "--as-of", "2026-07-12T09:00:00")
    assert r.returncode == 2
    assert "UTC offset" in r.stderr


def test_bad_week_start_rejected():
    r = run(str(FIXTURE), "--week-start", "July 6", "--as-of", AS_OF)
    assert r.returncode == 2
    assert "week-start" in r.stderr
