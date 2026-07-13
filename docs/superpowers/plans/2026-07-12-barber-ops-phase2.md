# Barber Ops Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `weekly-summary` Cowork skill (revenue rollup, gap analysis, one-page Markdown owner report) and the standalone `tools/seed_calendar.py` live-demo seeder.

**Architecture:** Same as phase 1 — pure-logic scripts over JSON, all analysis math in the `barber_ops` library (new `reporting.py` module reusing `slots.free_windows`). Two composable CLIs: `weekly_summary.py` (events JSON → combined summary JSON) piped into `render_report.py` (summary JSON → Markdown). `seed_calendar.py` is the ONE file in the repo allowed to touch Google APIs; it runs on the operator's machine only, with lazy imports so the repo tests never need Google libraries.

**Tech Stack:** Python ≥3.10, PyYAML, pytest. Google client libraries are NOT package dependencies — `seed_calendar.py` instructs the operator to install them separately.

**Spec:** `docs/superpowers/specs/2026-07-12-barber-ops-design.md` (phase 2 items: weekly-summary components + demo assets)

## Global Constraints

- All phase 1 Global Constraints still bind (no send capability, no network I/O in lib/skill scripts, tz-aware datetimes, explicit as-of, rejected list never dropped, pyyaml/pytest only in pyproject).
- `tools/seed_calendar.py` is the ONLY file that may touch Google APIs. Its google imports must be lazy (inside functions / guarded in main), so importing the module for tests works without Google libraries installed. Google libs must NOT be added to pyproject.toml.
- Revenue semantics (from fixture truth, week Mon 2026-07-06 → Sun 2026-07-12, as-of 2026-07-12T09:00:00-04:00): realized = `[showed]` bookings ($680, 16); missed = `[no-show]` ($90, 3); unconfirmed = untagged past ($105, 3); cancelled counted but $0 (1); upcoming = future non-cancelled in week ($0 for this week; $100/3 for week starting Jul 13).
- Gap semantics: business hours from `data/config.yaml`; cancelled bookings don't block; free windows listed at ≥ `--min-gap-minutes` (default 60); largest gap in fixture week = Tue 2026-07-07 12:00–18:00 (360 min); quietest daypart = tue afternoon (360 free min). Daypart split at 12:00 (morning = open→12:00, afternoon = 12:00→close).
- Utilization = round(100 × booked_minutes / open_minutes, 1); booked minutes exclude cancelled and are clipped to business hours. Fixture: mon 125/540=23.1, tue 90/540=16.7, wed 180/540=33.3, thu 155/600=25.8, fri 165/600=27.5, sat 165/480=34.4, sun open_minutes 0 → 0.0.
- Unknown service names are reported in `unknown_services` (event_id + service), never guessed, never counted in revenue.
- `credentials.json` and `token.json` must be gitignored.
- Demo persona unchanged: Sharp Cuts Barbershop, America/New_York, demo "today" Sun 2026-07-12.

---

### Task 1: Revenue rollup (`barber_ops.reporting.revenue_rollup`)

**Files:**
- Create: `barber_ops/reporting.py`
- Test: `tests/test_reporting_revenue.py`

**Interfaces:**
- Consumes: `Booking` (models), `Service`/`load_services` (services — dict keys are lowercased service names).
- Produces: `revenue_rollup(bookings: list[Booking], services: dict[str, Service], week_start: datetime.date, as_of: datetime) -> dict` with keys `week_start`, `week_end` (ISO strings, week = week_start..week_start+6), `realized`, `missed`, `unconfirmed`, `upcoming` (ints, dollars), `counts` (dict: showed/no_show/unconfirmed/cancelled/upcoming), `by_service` (service display name → {"showed": n, "revenue": $} for showed bookings only), `unknown_services` (list of {"event_id","service"}). Task 3 consumes this verbatim.

- [ ] **Step 1: Write the failing test**

`tests/test_reporting_revenue.py`:
```python
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
```

Run: `.venv/bin/pytest tests/test_reporting_revenue.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'barber_ops.reporting'`

- [ ] **Step 2: Implement `barber_ops/reporting.py`**

```python
"""Weekly revenue rollup and gap analysis."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from .models import Booking
from .services import Service


def revenue_rollup(
    bookings: list[Booking],
    services: dict[str, Service],
    week_start: date,
    as_of: datetime,
) -> dict:
    first, last = week_start, week_start + timedelta(days=6)
    totals = {"realized": 0, "missed": 0, "unconfirmed": 0, "upcoming": 0}
    counts = {"showed": 0, "no_show": 0, "unconfirmed": 0, "cancelled": 0, "upcoming": 0}
    by_service: dict[str, dict] = {}
    unknown: list[dict] = []
    for b in bookings:
        if not (first <= b.start.date() <= last):
            continue
        if b.status == "cancelled":
            counts["cancelled"] += 1
            continue
        svc = services.get(b.service.strip().lower())
        if svc is None:
            unknown.append({"event_id": b.event_id, "service": b.service})
            continue
        if b.end >= as_of:
            counts["upcoming"] += 1
            totals["upcoming"] += svc.price
        elif b.marker == "showed":
            counts["showed"] += 1
            totals["realized"] += svc.price
            entry = by_service.setdefault(svc.name, {"showed": 0, "revenue": 0})
            entry["showed"] += 1
            entry["revenue"] += svc.price
        elif b.marker == "no-show":
            counts["no_show"] += 1
            totals["missed"] += svc.price
        else:
            counts["unconfirmed"] += 1
            totals["unconfirmed"] += svc.price
    return {
        "week_start": first.isoformat(),
        "week_end": last.isoformat(),
        **totals,
        "counts": counts,
        "by_service": by_service,
        "unknown_services": unknown,
    }
```

- [ ] **Step 3: Run tests**

Run: `.venv/bin/pytest tests/test_reporting_revenue.py -v`
Expected: 4 passed

- [ ] **Step 4: Commit**

```bash
git add barber_ops/reporting.py tests/test_reporting_revenue.py
git commit -m "feat: add weekly revenue rollup"
```

---

### Task 2: Gap analysis (`barber_ops.reporting.gap_analysis`)

**Files:**
- Modify: `barber_ops/reporting.py`
- Test: `tests/test_reporting_gaps.py`

**Interfaces:**
- Consumes: `free_windows` and `WEEKDAY_KEYS` from `barber_ops.slots`, `ShopConfig`/`DayHours` (config).
- Produces: `gap_analysis(bookings: list[Booking], cfg: ShopConfig, week_start: date, min_minutes: int = 60) -> dict` with keys:
  - `min_minutes`
  - `per_day`: 7 entries, each `{"date","weekday","open","close","open_minutes","booked_minutes","utilization_pct","free_windows":[{"start","end","minutes"}]}`; closed day → open/close `None`, zeros, `[]`; `open`/`close` are `"HH:MM"` strings.
  - `largest_gap`: `{"date","start","end","minutes"}` (max-minutes free window across the week at ≥ min_minutes; `None` if none)
  - `quietest_daypart`: `{"weekday","daypart","free_minutes"}` where daypart is `"morning"` (open→12:00) or `"afternoon"` (12:00→close); free minutes from ALL gaps (no min filter); `None` if week fully closed.
  Task 3 consumes this verbatim.

- [ ] **Step 1: Write the failing test**

`tests/test_reporting_gaps.py`:
```python
from datetime import date
from pathlib import Path

from barber_ops.config import load_config
from barber_ops.models import normalize_events
from barber_ops.reporting import gap_analysis

ROOT = Path(__file__).resolve().parents[1]


def _gaps(week_data, min_minutes=60):
    bookings, rejected = normalize_events(week_data["events"], week_data["timeZone"])
    assert rejected == []
    cfg = load_config(ROOT / "data" / "config.yaml")
    return gap_analysis(bookings, cfg, date(2026, 7, 6), min_minutes)


def test_largest_gap_is_tuesday_afternoon(week_data):
    g = _gaps(week_data)
    assert g["largest_gap"]["date"] == "2026-07-07"
    assert g["largest_gap"]["minutes"] == 360
    assert g["largest_gap"]["start"].endswith("T12:00:00-04:00")


def test_quietest_daypart(week_data):
    g = _gaps(week_data)
    assert g["quietest_daypart"] == {"weekday": "tue", "daypart": "afternoon", "free_minutes": 360}


def test_per_day_utilization(week_data):
    g = _gaps(week_data)
    by_day = {d["weekday"]: d for d in g["per_day"]}
    assert by_day["mon"]["booked_minutes"] == 125
    assert by_day["mon"]["utilization_pct"] == 23.1
    assert by_day["tue"]["utilization_pct"] == 16.7
    assert by_day["wed"]["booked_minutes"] == 180  # cancelled Luis G excluded
    assert by_day["sat"]["open_minutes"] == 480
    assert by_day["sun"]["open"] is None
    assert by_day["sun"]["utilization_pct"] == 0.0


def test_min_minutes_filters_windows(week_data):
    g = _gaps(week_data, min_minutes=60)
    tue = next(d for d in g["per_day"] if d["weekday"] == "tue")
    assert [w["minutes"] for w in tue["free_windows"]] == [60, 360]
```

Run: `.venv/bin/pytest tests/test_reporting_gaps.py -v`
Expected: FAIL — `ImportError: cannot import name 'gap_analysis'`

- [ ] **Step 2: Extend `barber_ops/reporting.py`**

Add to the imports:
```python
from datetime import time
from zoneinfo import ZoneInfo

from .config import ShopConfig
from .slots import WEEKDAY_KEYS, free_windows
```

Append:
```python
def _overlap_minutes(s: datetime, e: datetime, lo: datetime, hi: datetime) -> int:
    start, end = max(s, lo), min(e, hi)
    return max(0, int((end - start).total_seconds() // 60))


def gap_analysis(
    bookings: list[Booking],
    cfg: ShopConfig,
    week_start: date,
    min_minutes: int = 60,
) -> dict:
    tz = ZoneInfo(cfg.timezone)
    noon = time(12, 0)
    per_day: list[dict] = []
    largest: dict | None = None
    quietest: dict | None = None
    for i in range(7):
        day = week_start + timedelta(days=i)
        weekday = WEEKDAY_KEYS[day.weekday()]
        hours = cfg.hours.get(weekday)
        if hours is None:
            per_day.append({
                "date": day.isoformat(), "weekday": weekday, "open": None, "close": None,
                "open_minutes": 0, "booked_minutes": 0, "utilization_pct": 0.0,
                "free_windows": [],
            })
            continue
        day_start = datetime.combine(day, hours.open, tzinfo=tz)
        day_end = datetime.combine(day, hours.close, tzinfo=tz)
        open_minutes = int((day_end - day_start).total_seconds() // 60)
        booked = sum(
            _overlap_minutes(b.start, b.end, day_start, day_end)
            for b in bookings
            if b.status != "cancelled" and b.start < day_end and b.end > day_start
        )
        all_gaps = free_windows(bookings, cfg, day, 0)
        windows = [
            {"start": s.isoformat(), "end": e.isoformat(),
             "minutes": int((e - s).total_seconds() // 60)}
            for s, e in all_gaps
            if (e - s) >= timedelta(minutes=min_minutes)
        ]
        for w in windows:
            if largest is None or w["minutes"] > largest["minutes"]:
                largest = {"date": day.isoformat(), **w}
        split = datetime.combine(day, noon, tzinfo=tz)
        dayparts = {
            "morning": sum(_overlap_minutes(s, e, day_start, min(split, day_end)) for s, e in all_gaps),
            "afternoon": sum(_overlap_minutes(s, e, max(split, day_start), day_end) for s, e in all_gaps),
        }
        for part, minutes in dayparts.items():
            if quietest is None or minutes > quietest["free_minutes"]:
                quietest = {"weekday": weekday, "daypart": part, "free_minutes": minutes}
        per_day.append({
            "date": day.isoformat(), "weekday": weekday,
            "open": hours.open.isoformat(timespec="minutes"),
            "close": hours.close.isoformat(timespec="minutes"),
            "open_minutes": open_minutes, "booked_minutes": booked,
            "utilization_pct": round(100 * booked / open_minutes, 1) if open_minutes else 0.0,
            "free_windows": windows,
        })
    return {"min_minutes": min_minutes, "per_day": per_day,
            "largest_gap": largest, "quietest_daypart": quietest}
```

- [ ] **Step 3: Run tests**

Run: `.venv/bin/pytest tests/test_reporting_gaps.py -v`
Expected: 4 passed

- [ ] **Step 4: Commit**

```bash
git add barber_ops/reporting.py tests/test_reporting_gaps.py
git commit -m "feat: add weekly gap analysis"
```

---

### Task 3: `weekly_summary.py` script

**Files:**
- Create: `skills/weekly-summary/scripts/weekly_summary.py`
- Test: `tests/test_weekly_summary.py`

**Interfaces:**
- Consumes: `revenue_rollup`, `gap_analysis` (Tasks 1-2), `normalize_events`, `load_config`, `load_services`. Same sys.path pattern as phase 1 scripts: `REPO_ROOT = Path(__file__).resolve().parents[3]`.
- Produces: CLI `weekly_summary.py [events.json] --week-start YYYY-MM-DD --as-of ISO [--min-gap-minutes N] [--config PATH] [--services PATH]`. Stdout JSON: `{"shop_name","as_of","revenue":<rollup>,"gaps":<gap_analysis>,"rejected":[...]}`. Exit 2 on invalid/naive --as-of or invalid --week-start. Task 4 consumes this JSON verbatim.

- [ ] **Step 1: Write the failing test**

`tests/test_weekly_summary.py`:
```python
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
```

Run: `.venv/bin/pytest tests/test_weekly_summary.py -v`
Expected: FAIL — script file does not exist

- [ ] **Step 2: Implement `skills/weekly-summary/scripts/weekly_summary.py`**

```python
#!/usr/bin/env python3
"""One-week revenue rollup and gap analysis. Outputs combined JSON for render_report.py.

Input (file arg or stdin): {"timeZone": str, "events": [...]} in Google
events.list shape, or a bare event list.
Output (stdout): {"shop_name", "as_of", "revenue", "gaps", "rejected"}.

This script never contacts any external service.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from barber_ops.config import load_config  # noqa: E402
from barber_ops.models import normalize_events  # noqa: E402
from barber_ops.reporting import gap_analysis, revenue_rollup  # noqa: E402
from barber_ops.services import load_services  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("events_file", nargs="?", help="events JSON file (default: stdin)")
    parser.add_argument("--week-start", required=True, help="first day of the report week, YYYY-MM-DD")
    parser.add_argument("--as-of", required=True, help="ISO timestamp with UTC offset")
    parser.add_argument("--min-gap-minutes", type=int, default=60)
    parser.add_argument("--config", default=str(REPO_ROOT / "data" / "config.yaml"))
    parser.add_argument("--services", default=str(REPO_ROOT / "data" / "services.yaml"))
    args = parser.parse_args()

    try:
        as_of = datetime.fromisoformat(args.as_of)
    except ValueError:
        print(f"error: invalid --as-of {args.as_of!r}", file=sys.stderr)
        return 2
    if as_of.tzinfo is None:
        print("error: --as-of must include a UTC offset, e.g. 2026-07-12T09:00:00-04:00", file=sys.stderr)
        return 2
    try:
        week_start = date.fromisoformat(args.week_start)
    except ValueError:
        print(f"error: invalid --week-start {args.week_start!r} (expected YYYY-MM-DD)", file=sys.stderr)
        return 2

    raw = json.loads(Path(args.events_file).read_text()) if args.events_file else json.load(sys.stdin)
    events = raw["events"] if isinstance(raw, dict) else raw
    cfg = load_config(args.config)
    default_tz = (raw.get("timeZone") if isinstance(raw, dict) else None) or cfg.timezone

    bookings, rejected = normalize_events(events, default_tz)
    services = load_services(args.services)

    json.dump(
        {
            "shop_name": cfg.shop_name,
            "as_of": as_of.isoformat(),
            "revenue": revenue_rollup(bookings, services, week_start, as_of),
            "gaps": gap_analysis(bookings, cfg, week_start, args.min_gap_minutes),
            "rejected": rejected,
        },
        sys.stdout, indent=2,
    )
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Run tests**

Run: `.venv/bin/pytest tests/test_weekly_summary.py -v`
Expected: 4 passed

- [ ] **Step 4: Commit**

```bash
git add skills/weekly-summary/scripts/weekly_summary.py tests/test_weekly_summary.py
git commit -m "feat: add weekly_summary skill script"
```

---

### Task 4: `render_report.py` script

**Files:**
- Create: `skills/weekly-summary/scripts/render_report.py`
- Test: `tests/test_render_report.py`

**Interfaces:**
- Consumes: the combined summary JSON from Task 3 (file arg or stdin). Pure stdlib — needs no barber_ops import (all data is in the JSON).
- Produces: one-page Markdown owner report on stdout with sections: title (`# <shop> — Weekly Report (<Mon d> to <Mon d>)`), `## Revenue` table, `## Revenue by service` table (sorted by revenue desc), `## Schedule utilization` table, `## Gaps` bullets (largest open block, quietest daypart), `## Suggested actions` conditional bullets. If `rejected` is non-empty, a `> ⚠️ N event(s) could not be parsed` blockquote after the title.

- [ ] **Step 1: Write the failing test**

`tests/test_render_report.py`:
```python
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
```

Run: `.venv/bin/pytest tests/test_render_report.py -v`
Expected: FAIL — render_report.py does not exist

- [ ] **Step 2: Implement `skills/weekly-summary/scripts/render_report.py`**

```python
#!/usr/bin/env python3
"""Render weekly_summary.py JSON as a one-page Markdown owner report.

Input (file arg or stdin): the combined JSON from weekly_summary.py.
Output (stdout): Markdown. This script never contacts any external service.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, time
from pathlib import Path

WEEKDAY_LABELS = {
    "mon": "Monday", "tue": "Tuesday", "wed": "Wednesday", "thu": "Thursday",
    "fri": "Friday", "sat": "Saturday", "sun": "Sunday",
}


def _money(n: int) -> str:
    return f"${n}"


def _dur(minutes: int) -> str:
    h, m = divmod(minutes, 60)
    return f"{h}h {m}m" if h else f"{m}m"


def _day_label(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.strftime('%a %b')} {d.day}"


def _clock(hhmm: str) -> str:
    t = time.fromisoformat(hhmm)
    hour = t.hour % 12 or 12
    suffix = "AM" if t.hour < 12 else "PM"
    return f"{hour}:{t.minute:02d} {suffix}"


def _clock_iso(iso: str) -> str:
    dt = datetime.fromisoformat(iso)
    return _clock(dt.strftime("%H:%M"))


def render(summary: dict) -> str:
    rev = summary["revenue"]
    gaps = summary["gaps"]
    c = rev["counts"]
    lines = [
        f"# {summary['shop_name']} — Weekly Report ({_day_label(rev['week_start'])} to {_day_label(rev['week_end'])})",
        "",
    ]
    if summary.get("rejected"):
        lines += [f"> ⚠️ {len(summary['rejected'])} event(s) could not be parsed — review them.", ""]
    lines += [
        "## Revenue",
        "| | Count | Amount |",
        "|---|---|---|",
        f"| Showed | {c['showed']} | {_money(rev['realized'])} |",
        f"| No-shows (missed) | {c['no_show']} | {_money(rev['missed'])} |",
        f"| Unconfirmed (past, unmarked) | {c['unconfirmed']} | {_money(rev['unconfirmed'])} |",
        f"| Cancelled | {c['cancelled']} | — |",
        f"| Upcoming this week | {c['upcoming']} | {_money(rev['upcoming'])} |",
        "",
        "## Revenue by service",
        "| Service | Showed | Revenue |",
        "|---|---|---|",
    ]
    for name, e in sorted(rev["by_service"].items(), key=lambda kv: -kv[1]["revenue"]):
        lines.append(f"| {name} | {e['showed']} | {_money(e['revenue'])} |")
    lines += ["", "## Schedule utilization", "| Day | Hours | Booked | Utilization |", "|---|---|---|---|"]
    for d in gaps["per_day"]:
        if d["open"] is None:
            lines.append(f"| {_day_label(d['date'])} | closed | — | — |")
        else:
            lines.append(
                f"| {_day_label(d['date'])} | {_clock(d['open'])}–{_clock(d['close'])} "
                f"| {_dur(d['booked_minutes'])} | {d['utilization_pct']}% |"
            )
    lines += ["", "## Gaps"]
    lg = gaps["largest_gap"]
    if lg:
        lines.append(
            f"- Largest open block: {_day_label(lg['date'])}, "
            f"{_clock_iso(lg['start'])}–{_clock_iso(lg['end'])} ({_dur(lg['minutes'])})"
        )
    qd = gaps["quietest_daypart"]
    if qd:
        lines.append(
            f"- Quietest daypart: {WEEKDAY_LABELS[qd['weekday']]} {qd['daypart']} "
            f"({_dur(qd['free_minutes'])} free)"
        )
    lines += ["", "## Suggested actions"]
    actions = []
    if c["unconfirmed"]:
        actions.append(
            f"- Tag the {c['unconfirmed']} unmarked past appointment(s) as [showed] or [no-show] — "
            f"{_money(rev['unconfirmed'])} of revenue is unaccounted for."
        )
    if c["no_show"]:
        actions.append(
            f"- {c['no_show']} no-show(s) cost {_money(rev['missed'])} — run the "
            f"appointment-management skill to draft rebooking messages."
        )
    if qd and qd["free_minutes"] >= 180:
        actions.append(
            f"- {WEEKDAY_LABELS[qd['weekday']]} {qd['daypart']}s are mostly open "
            f"({_dur(qd['free_minutes'])} free) — consider a promo or accepting walk-ins."
        )
    lines += actions or ["- Solid week — nothing needs attention."]
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("summary_file", nargs="?", help="summary JSON file (default: stdin)")
    args = parser.parse_args()
    summary = json.loads(Path(args.summary_file).read_text()) if args.summary_file else json.load(sys.stdin)
    sys.stdout.write(render(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Run tests**

Run: `.venv/bin/pytest tests/test_render_report.py -v`
Expected: 2 passed

- [ ] **Step 4: Commit**

```bash
git add skills/weekly-summary/scripts/render_report.py tests/test_render_report.py
git commit -m "feat: add weekly report renderer"
```

---

### Task 5: weekly-summary SKILL.md + README runbook + manual verification

**Files:**
- Create: `skills/weekly-summary/SKILL.md`
- Modify: `README.md` (fill in the weekly-summary bullet and add a runbook step)

**Interfaces:**
- Consumes: the two script CLIs exactly as specified in Tasks 3-4.
- Produces: the complete weekly-summary skill, demoable offline.

- [ ] **Step 1: Write `skills/weekly-summary/SKILL.md`**

```markdown
---
name: weekly-summary
description: Build a one-page weekly owner report for a barber shop from Google Calendar bookings — revenue estimated from the service price map, no-show costs, schedule utilization, and gap patterns. Use when the owner asks for a weekly report, revenue summary, how the week went, or where the empty slots are.
---

# Weekly Summary

Produces a one-page Markdown report for a single-calendar barber shop.
Booking events use the title convention `<Service> — <Customer Name> [marker]`
(em dash), where the marker is `[showed]`, `[no-show]`, or absent. The service
menu and prices live in `data/services.yaml`; business hours in
`data/config.yaml`.

## Hard rules

1. **Never invent numbers.** Every figure in the report comes from the
   scripts' output. If a number is not in the JSON, do not state it.
2. **Report rejected events.** If the summary JSON has a non-empty `rejected`
   list, show it to the owner — those events are excluded from all figures.
3. **Unconfirmed ≠ no-show.** Untagged past appointments are reported as
   unconfirmed revenue. Suggest tagging them; offer the appointment-management
   skill for no-show follow-ups. Do not draft messages from this skill.

## Getting events

- **Live:** fetch the report week (Monday through Sunday) from the Google
  Calendar connector as `{"timeZone": "...", "events": [...]}` with each
  event's `id`, `summary`, `description`, `start`, `end`, `status`.
- **Demo mode:** use `data/demo/week_fixture.json` (report week
  `--week-start 2026-07-06`, "today" is Sun 2026-07-12). Requires pyyaml for
  system python3 (`python3 -m pip install --user pyyaml`).

## Workflow

1. Get events for the week the owner asked about.
2. Run (from the repo root):
   `python3 skills/weekly-summary/scripts/weekly_summary.py <events.json> --week-start <monday YYYY-MM-DD> --as-of <current time, ISO with UTC offset>`
3. Pipe (or pass) the JSON through the renderer:
   `python3 skills/weekly-summary/scripts/render_report.py`
4. Present the rendered Markdown report to the owner verbatim, then offer:
   - tagging help for unconfirmed appointments,
   - the appointment-management skill for no-show rebooking drafts,
   - deeper detail on any day's free windows (they are in the JSON under
     `gaps.per_day[].free_windows`).
```

- [ ] **Step 2: Update `README.md`**

Change the weekly-summary bullet from "(phase 2)" to:
```markdown
- `skills/weekly-summary/` — weekly revenue + gap report. See its `SKILL.md`.
```

Append to the demo runbook (after step 3):
```markdown
4. Weekly owner report:

       python3 skills/weekly-summary/scripts/weekly_summary.py \
         data/demo/week_fixture.json --week-start 2026-07-06 --as-of 2026-07-12T09:00:00-04:00 \
       | python3 skills/weekly-summary/scripts/render_report.py

   Expect: $680 realized, $90 missed to no-shows, $105 unconfirmed, largest
   open block Tue Jul 7 12:00 PM–6:00 PM.
```

- [ ] **Step 3: Run the full test suite**

Run: `.venv/bin/pytest`
Expected: 53 passed (39 phase 1 + 14 new so far)

- [ ] **Step 4: Manual verification with system python3 (uninstalled), from repo root**

```bash
python3 skills/weekly-summary/scripts/weekly_summary.py data/demo/week_fixture.json --week-start 2026-07-06 --as-of 2026-07-12T09:00:00-04:00 | python3 skills/weekly-summary/scripts/render_report.py
```
Expected: a Markdown report with $680 / $90 / $105, the utilization table
(mon 23.1% … sat 34.4%, Sun closed), largest open block Tue Jul 7
12:00 PM–6:00 PM (6h 0m), and three suggested-action bullets. No tracebacks.

- [ ] **Step 5: Commit**

```bash
git add skills/weekly-summary/SKILL.md README.md
git commit -m "feat: add weekly-summary SKILL.md and runbook"
```

---

### Task 6: `tools/seed_calendar.py` + live-demo docs

**Files:**
- Create: `tools/seed_calendar.py`
- Modify: `.gitignore` (add `credentials.json`, `token.json`), `README.md` (replace the "Live demo (optional, phase 2)" section)
- Test: `tests/test_seed_calendar.py` (pure date-shift logic only — no Google calls)

**Interfaces:**
- Consumes: `data/demo/week_fixture.json`.
- Produces: CLI `seed_calendar.py --calendar-id ID [--fixture PATH] [--week-of YYYY-MM-DD] [--credentials PATH] [--token PATH]`; pure helper `shift_events(events: list[dict], target_monday: date) -> list[dict]` (re-dates the fixture week — Mon 2026-07-06 — onto target_monday; does not mutate input). Google imports are lazy so the module imports cleanly without Google libraries.

- [ ] **Step 1: Write the failing test**

`tests/test_seed_calendar.py`:
```python
import importlib.util
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("seed_calendar", ROOT / "tools" / "seed_calendar.py")
seed_calendar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seed_calendar)


def test_shift_events_moves_week(week_data):
    shifted = seed_calendar.shift_events(week_data["events"], date(2026, 7, 20))
    assert shifted[0]["start"]["dateTime"] == "2026-07-20T09:00:00-04:00"
    assert shifted[-1]["start"]["dateTime"] == "2026-07-28T09:00:00-04:00"
    assert len(shifted) == len(week_data["events"])


def test_shift_events_does_not_mutate_input(week_data):
    before = week_data["events"][0]["start"]["dateTime"]
    seed_calendar.shift_events(week_data["events"], date(2026, 7, 20))
    assert week_data["events"][0]["start"]["dateTime"] == before
```

Run: `.venv/bin/pytest tests/test_seed_calendar.py -v`
Expected: FAIL — `FileNotFoundError` (tools/seed_calendar.py does not exist)

- [ ] **Step 2: Implement `tools/seed_calendar.py`**

```python
#!/usr/bin/env python3
"""Seed a real Google Calendar with the demo fixture (operator machine only).

This is the ONLY file in this repo that touches Google APIs. It is NOT part
of the skills — skills are pure logic; Claude reaches Google via Cowork
connectors. Requires (install separately, never added to pyproject):

    python3 -m pip install --user google-api-python-client google-auth-oauthlib

and an OAuth "Desktop app" client credentials.json from Google Cloud Console
with the Calendar API enabled. On first run a browser window authorizes the
account; the token is cached in token.json. Both files are gitignored.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_MONDAY = date(2026, 7, 6)
SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


def shift_events(events: list[dict], target_monday: date) -> list[dict]:
    """Re-date the fixture week onto the week starting target_monday."""
    delta = target_monday - FIXTURE_MONDAY
    shifted = []
    for ev in events:
        ev = json.loads(json.dumps(ev))
        for field in ("start", "end"):
            dt = datetime.fromisoformat(ev[field]["dateTime"])
            ev[field]["dateTime"] = (dt + delta).isoformat()
        shifted.append(ev)
    return shifted


def _calendar_service(credentials: Path, token: Path):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    if token.exists():
        creds = Credentials.from_authorized_user_file(str(token), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(credentials), SCOPES)
            creds = flow.run_local_server(port=0)
        token.write_text(creds.to_json())
    return build("calendar", "v3", credentials=creds)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--calendar-id", required=True, help="target Google Calendar ID")
    parser.add_argument("--fixture", default=str(REPO_ROOT / "data" / "demo" / "week_fixture.json"))
    parser.add_argument("--week-of", help="Monday (YYYY-MM-DD) to re-date the demo week onto")
    parser.add_argument("--credentials", default="credentials.json")
    parser.add_argument("--token", default="token.json")
    args = parser.parse_args()

    try:
        import google_auth_oauthlib  # noqa: F401
        import googleapiclient  # noqa: F401
    except ImportError:
        print(
            "error: missing Google libraries — run:\n"
            "  python3 -m pip install --user google-api-python-client google-auth-oauthlib",
            file=sys.stderr,
        )
        return 2

    if not Path(args.credentials).exists():
        print(f"error: {args.credentials} not found (OAuth Desktop-app client from Google Cloud Console)", file=sys.stderr)
        return 2

    events = json.loads(Path(args.fixture).read_text())["events"]
    if args.week_of:
        try:
            target = date.fromisoformat(args.week_of)
        except ValueError:
            print(f"error: invalid --week-of {args.week_of!r} (expected YYYY-MM-DD)", file=sys.stderr)
            return 2
        events = shift_events(events, target)

    service = _calendar_service(Path(args.credentials), Path(args.token))
    created = skipped = 0
    for ev in events:
        if ev.get("status") == "cancelled":
            skipped += 1
            continue
        body = {k: ev[k] for k in ("summary", "description", "start", "end") if k in ev}
        service.events().insert(calendarId=args.calendar_id, body=body).execute()
        created += 1
    print(f"created {created} events, skipped {skipped} cancelled")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Update `.gitignore` and `README.md`**

`.gitignore` — append:
```
credentials.json
token.json
```

`README.md` — replace the "## Live demo (optional, phase 2)" section with:
```markdown
## Live demo (optional)

Seed the demo week into a real Google Calendar, then run the same skills
against events fetched via the Calendar connector:

    python3 -m pip install --user google-api-python-client google-auth-oauthlib
    python3 tools/seed_calendar.py --calendar-id <id> --week-of <last-monday YYYY-MM-DD>

Needs a `credentials.json` (OAuth Desktop-app client, Calendar API enabled)
in the working directory; the OAuth token is cached in `token.json`. Both are
gitignored. `--week-of` re-dates the fixture week onto a real week; pass last
Monday to make "this past week" demos line up. Cancelled fixture events are
skipped (they exist only for offline no-show demos). When running the skills
against the seeded calendar, use a matching `--week-start` and real `--as-of`.
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_seed_calendar.py -v` — Expected: 2 passed
Run: `.venv/bin/pytest` — Expected: 55 passed

- [ ] **Step 5: Commit**

```bash
git add tools/seed_calendar.py tests/test_seed_calendar.py .gitignore README.md
git commit -m "feat: add Google Calendar demo seeder"
```

**Phase 2 ends here — Barber Ops Starter package complete.**
