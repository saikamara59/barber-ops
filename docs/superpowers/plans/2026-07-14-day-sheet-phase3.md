# Day Sheet Skill (Phase 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `day-sheet` skill: a morning briefing with today's lineup, now/next, and walk-in windows sized against the service menu.

**Architecture:** Same as phases 1-2 — math in the library (`barber_ops/day.py`, reusing `slots.free_windows`), one thin CLI script (`skills/day-sheet/scripts/day_sheet.py`) with `--format json|text` (no separate renderer: the text output is ~15 lines with zero reuse elsewhere).

**Tech Stack:** Python ≥3.10, PyYAML, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-07-14-day-sheet-design.md`

## Global Constraints

- All prior Global Constraints bind (no send/network, tz-aware, explicit `--as-of` never system clock, cancelled excluded, `rejected` reported, pyyaml/pytest only).
- Walk-in windows: `free_windows` at min = shortest menu duration (20); windows with `end <= as_of` dropped; the current window's start is clipped to `as_of`; after clipping, windows shorter than the shortest service are dropped; `fits` lists service display names (alphabetical) with `duration_min <= window minutes`; `fits_all` true when every menu service fits.
- Fixture truth (date 2026-07-13, as-of 08:00-04:00): appointments Marcus J (Fade 10:00, 45m) then Devon P (Haircut 2:00 PM, 30m); booked 75 min; now null; next Marcus J; windows 60/195/210 min, all `fits_all`. At as-of 13:30: first window clipped to 13:30→14:00 (30 min, fits Beard Trim/Haircut/Kids Cut only); next Devon P. At as-of 10:15: now Marcus J, next Devon P. Date 2026-07-14: Sam K only, one window 9:20 AM–6:00 PM (520 min). Date 2026-07-12: closed.
- Suite grows 57 → 65.

---

### Task 1: Day-sheet math (`barber_ops.day`)

**Files:**
- Create: `barber_ops/day.py`
- Test: `tests/test_day.py`

**Interfaces:**
- Consumes: `Booking`, `ShopConfig`, `Service` dict (lowercased keys), `free_windows`/`WEEKDAY_KEYS` from slots.
- Produces: `build_day_sheet(bookings: list[Booking], cfg: ShopConfig, services: dict[str, Service], day: datetime.date, as_of: datetime) -> dict` exactly per the spec's Output contract (minus `rejected`, which the script attaches). Task 2 consumes it verbatim.

- [ ] **Step 1: Write the failing test**

`tests/test_day.py`:
```python
from datetime import date, datetime
from pathlib import Path

from barber_ops.config import load_config
from barber_ops.day import build_day_sheet
from barber_ops.models import normalize_events
from barber_ops.services import load_services

ROOT = Path(__file__).resolve().parents[1]
MORNING = datetime.fromisoformat("2026-07-13T08:00:00-04:00")


def _sheet(week_data, day, as_of):
    bookings, rejected = normalize_events(week_data["events"], week_data["timeZone"])
    assert rejected == []
    cfg = load_config(ROOT / "data" / "config.yaml")
    services = load_services(ROOT / "data" / "services.yaml")
    return build_day_sheet(bookings, cfg, services, day, as_of)


def test_monday_morning_sheet(week_data):
    s = _sheet(week_data, date(2026, 7, 13), MORNING)
    assert s["closed"] is False
    assert [a["customer"] for a in s["appointments"]] == ["Marcus J", "Devon P"]
    assert s["booked_minutes"] == 75
    assert s["now"] is None
    assert s["next"]["customer"] == "Marcus J"
    assert [w["minutes"] for w in s["walkin_windows"]] == [60, 195, 210]
    assert all(w["fits_all"] for w in s["walkin_windows"])


def test_midday_clips_current_window(week_data):
    s = _sheet(week_data, date(2026, 7, 13), datetime.fromisoformat("2026-07-13T13:30:00-04:00"))
    w = s["walkin_windows"][0]
    assert w["start"] == "2026-07-13T13:30:00-04:00"
    assert w["minutes"] == 30
    assert w["fits"] == ["Beard Trim", "Haircut", "Kids Cut"]
    assert w["fits_all"] is False
    assert s["next"]["customer"] == "Devon P"


def test_in_the_chair(week_data):
    s = _sheet(week_data, date(2026, 7, 13), datetime.fromisoformat("2026-07-13T10:15:00-04:00"))
    assert s["now"]["customer"] == "Marcus J"
    assert s["now"]["end"] == "2026-07-13T10:45:00-04:00"
    assert s["next"]["customer"] == "Devon P"


def test_closed_day(week_data):
    s = _sheet(week_data, date(2026, 7, 12), MORNING)
    assert s["closed"] is True
    assert s["appointments"] == []
    assert s["walkin_windows"] == []
```

Run: `.venv/bin/pytest tests/test_day.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'barber_ops.day'`

- [ ] **Step 2: Implement `barber_ops/day.py`**

```python
"""Day-sheet math: today's lineup, now/next, and walk-in windows."""
from __future__ import annotations

from datetime import date, datetime

from .config import ShopConfig
from .models import Booking
from .services import Service
from .slots import WEEKDAY_KEYS, free_windows


def _appt(b: Booking) -> dict:
    return {
        "start": b.start.isoformat(),
        "end": b.end.isoformat(),
        "service": b.service,
        "customer": b.customer,
        "duration_min": int((b.end - b.start).total_seconds() // 60),
        "status": b.status,
        "marker": b.marker,
    }


def build_day_sheet(
    bookings: list[Booking],
    cfg: ShopConfig,
    services: dict[str, Service],
    day: date,
    as_of: datetime,
) -> dict:
    weekday = WEEKDAY_KEYS[day.weekday()]
    hours = cfg.hours.get(weekday)
    base = {"shop_name": cfg.shop_name, "date": day.isoformat(), "weekday": weekday}
    if hours is None:
        return {**base, "closed": True, "open": None, "close": None,
                "appointments": [], "booked_minutes": 0, "now": None, "next": None,
                "walkin_windows": []}

    todays = sorted(
        (b for b in bookings if b.status != "cancelled" and b.start.date() == day),
        key=lambda b: b.start,
    )
    booked_minutes = sum(int((b.end - b.start).total_seconds() // 60) for b in todays)
    in_chair = next((b for b in todays if b.start <= as_of < b.end), None)
    upcoming = next((b for b in todays if b.start > as_of), None)

    min_duration = min(s.duration_min for s in services.values())
    windows = []
    for s, e in free_windows(bookings, cfg, day, min_duration):
        if e <= as_of:
            continue
        start = max(s, as_of)
        minutes = int((e - start).total_seconds() // 60)
        if minutes < min_duration:
            continue
        fits = sorted(svc.name for svc in services.values() if svc.duration_min <= minutes)
        windows.append({
            "start": start.isoformat(), "end": e.isoformat(), "minutes": minutes,
            "fits": fits, "fits_all": len(fits) == len(services),
        })

    return {
        **base, "closed": False,
        "open": hours.open.isoformat(timespec="minutes"),
        "close": hours.close.isoformat(timespec="minutes"),
        "appointments": [_appt(b) for b in todays],
        "booked_minutes": booked_minutes,
        "now": _appt(in_chair) if in_chair else None,
        "next": _appt(upcoming) if upcoming else None,
        "walkin_windows": windows,
    }
```

- [ ] **Step 3: Run tests**

Run: `.venv/bin/pytest tests/test_day.py -v`
Expected: 4 passed

- [ ] **Step 4: Commit**

```bash
git add barber_ops/day.py tests/test_day.py
git commit -m "feat: add day-sheet math"
```

---

### Task 2: `day_sheet.py` script

**Files:**
- Create: `skills/day-sheet/scripts/day_sheet.py`
- Test: `tests/test_day_sheet_script.py`

**Interfaces:**
- Consumes: `build_day_sheet` (Task 1), `normalize_events`, `load_config`, `load_services`. sys.path pattern `parents[3]` (script sits at `skills/day-sheet/scripts/`).
- Produces: CLI `day_sheet.py [events.json] --date YYYY-MM-DD --as-of ISO [--format json|text] [--config PATH] [--services PATH]`. `--format json` (default): the `build_day_sheet` dict plus `"rejected"`. `--format text`: the spec's message format. Exit 2 on invalid/naive `--as-of` or invalid `--date`.

- [ ] **Step 1: Write the failing test**

`tests/test_day_sheet_script.py`:
```python
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
```

Run: `.venv/bin/pytest tests/test_day_sheet_script.py -v`
Expected: FAIL — script file does not exist

- [ ] **Step 2: Implement `skills/day-sheet/scripts/day_sheet.py`**

```python
#!/usr/bin/env python3
"""Morning day sheet: today's lineup, who's next, and walk-in room.

Input (file arg or stdin): {"timeZone": str, "events": [...]} in Google
events.list shape, or a bare event list.
Output: --format json (default) per the day-sheet contract, or --format text
(the message the owner receives). This script never contacts any external
service.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from barber_ops.config import load_config  # noqa: E402
from barber_ops.day import build_day_sheet  # noqa: E402
from barber_ops.models import normalize_events  # noqa: E402
from barber_ops.services import load_services  # noqa: E402


def _clock(dt: datetime) -> str:
    hour = dt.hour % 12 or 12
    return f"{hour}:{dt.minute:02d} {'AM' if dt.hour < 12 else 'PM'}"


def _clock_hhmm(hhmm: str) -> str:
    t = time.fromisoformat(hhmm)
    hour = t.hour % 12 or 12
    return f"{hour}:{t.minute:02d} {'AM' if t.hour < 12 else 'PM'}"


def _dur(minutes: int) -> str:
    h, m = divmod(minutes, 60)
    return f"{h}h {m}m" if h else f"{m}m"


def render_text(sheet: dict) -> str:
    d = date.fromisoformat(sheet["date"])
    header = f"TODAY AT {sheet['shop_name'].upper()} — {d.strftime('%a %b')} {d.day}"
    if sheet["closed"]:
        return f"{header}\nClosed today.\n"
    lines = [header,
             f"Hours: {_clock_hhmm(sheet['open'])}–{_clock_hhmm(sheet['close'])}"]
    n = len(sheet["appointments"])
    lines.append(f"{n} appointment{'s' if n != 1 else ''} · {_dur(sheet['booked_minutes'])} booked")
    lines.append("")
    if sheet["appointments"]:
        lines.append("Lineup:")
        for a in sheet["appointments"]:
            start = datetime.fromisoformat(a["start"])
            lines.append(f"  {_clock(start):>8}  {a['service']} — {a['customer']} ({a['duration_min']}m)")
    else:
        lines.append("No appointments booked.")
    lines.append("")
    if sheet["now"]:
        end = datetime.fromisoformat(sheet["now"]["end"])
        lines.append(f"In the chair: {sheet['now']['customer']} until {_clock(end)}")
    if sheet["next"]:
        start = datetime.fromisoformat(sheet["next"]["start"])
        lines.append(f"Next up: {sheet['next']['customer']} at {_clock(start)} ({sheet['next']['service']})")
    elif not sheet["now"]:
        lines.append("No more appointments today.")
    lines.append("")
    lines.append("Walk-in room:")
    if sheet["walkin_windows"]:
        for w in sheet["walkin_windows"]:
            ws = datetime.fromisoformat(w["start"])
            we = datetime.fromisoformat(w["end"])
            fits = "any service" if w["fits_all"] else ", ".join(w["fits"])
            lines.append(f"  {_clock(ws)}–{_clock(we)} ({_dur(w['minutes'])}) — {fits}")
    else:
        lines.append("  None — the book is full.")
    if sheet.get("rejected"):
        lines.append("")
        lines.append(f"⚠ {len(sheet['rejected'])} event(s) could not be parsed — review them.")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("events_file", nargs="?", help="events JSON file (default: stdin)")
    parser.add_argument("--date", dest="day", required=True, help="YYYY-MM-DD")
    parser.add_argument("--as-of", required=True, help="ISO timestamp with UTC offset")
    parser.add_argument("--format", choices=["json", "text"], default="json")
    parser.add_argument("--config", default=str(REPO_ROOT / "data" / "config.yaml"))
    parser.add_argument("--services", default=str(REPO_ROOT / "data" / "services.yaml"))
    args = parser.parse_args()

    try:
        as_of = datetime.fromisoformat(args.as_of)
    except ValueError:
        print(f"error: invalid --as-of {args.as_of!r}", file=sys.stderr)
        return 2
    if as_of.tzinfo is None:
        print("error: --as-of must include a UTC offset, e.g. 2026-07-13T08:00:00-04:00", file=sys.stderr)
        return 2
    try:
        day = date.fromisoformat(args.day)
    except ValueError:
        print(f"error: invalid --date {args.day!r} (expected YYYY-MM-DD)", file=sys.stderr)
        return 2

    raw = json.loads(Path(args.events_file).read_text()) if args.events_file else json.load(sys.stdin)
    events = raw["events"] if isinstance(raw, dict) else raw
    cfg = load_config(args.config)
    default_tz = (raw.get("timeZone") if isinstance(raw, dict) else None) or cfg.timezone

    bookings, rejected = normalize_events(events, default_tz)
    services = load_services(args.services)
    sheet = {**build_day_sheet(bookings, cfg, services, day, as_of), "rejected": rejected}

    if args.format == "text":
        sys.stdout.write(render_text(sheet))
    else:
        json.dump(sheet, sys.stdout, indent=2)
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Run tests**

Run: `.venv/bin/pytest tests/test_day_sheet_script.py -v`
Expected: 4 passed

- [ ] **Step 4: Commit**

```bash
git add skills/day-sheet/scripts/day_sheet.py tests/test_day_sheet_script.py
git commit -m "feat: add day_sheet skill script"
```

---

### Task 3: SKILL.md + README + manual verification

**Files:**
- Create: `skills/day-sheet/SKILL.md`
- Modify: `README.md` (skills list bullet + runbook step 5)

- [ ] **Step 1: Write `skills/day-sheet/SKILL.md`**

```markdown
---
name: day-sheet
description: Morning briefing for a barber shop — today's lineup from Google Calendar, who's in the chair and who's next, and which walk-in services fit the open gaps right now. Use when the owner asks what's on today, who's coming, whether they can take a walk-in, or wants the day sheet.
---

# Day Sheet

Answers the owner's two daily questions: who's coming today, and can I take
this walk-in right now. Booking events use the title convention
`<Service> — <Customer Name> [marker]` (em dash); the service menu is
`data/services.yaml`, business hours `data/config.yaml`.

## Hard rules

1. **Never invent bookings or walk-in room.** The lineup and windows come
   from the script's output only.
2. **Report rejected events** — a booking the script couldn't parse is a
   booking the owner might miss. Show any `rejected` entries immediately.
3. **Walk-in answers are time-sensitive.** For "can I take a walk-in?"
   mid-day, re-run the script with the current time as `--as-of` — never
   reuse a stale morning sheet for that answer.

## Getting events

- **Live:** fetch TODAY's events from the Google Calendar connector as
  `{"timeZone": "...", "events": [...]}` (id, summary, description, start,
  end, status).
- **Demo mode:** use `data/demo/week_fixture.json` with
  `--date 2026-07-13 --as-of 2026-07-13T08:00:00-04:00` (a Monday with two
  bookings and three open blocks).

## Workflow

1. Get today's events.
2. Run (from the repo root):
   `python3 skills/day-sheet/scripts/day_sheet.py <events.json> --date <today> --as-of <now, ISO with UTC offset> --format text`
3. Deliver the text sheet verbatim — it is the morning message.
4. For a mid-day walk-in question, re-run with the current `--as-of` and
   answer from `Walk-in room` (e.g. "yes to a haircut, no to a fade —
   Marcus arrives at 2:00").
5. If the owner wants to book the walk-in in, hand off to the
   appointment-management skill's conventions: create the event via the
   Calendar connector with the `<Service> — <Name>` title.
```

- [ ] **Step 2: Update `README.md`**

Add to the skills list (after the weekly-summary bullet):
```markdown
- `skills/day-sheet/` — morning lineup + walk-in room. See its `SKILL.md`.
```

Append runbook step 5:
```markdown
5. Morning day sheet (demo "today" is Mon 2026-07-13 for this one):

       python3 skills/day-sheet/scripts/day_sheet.py \
         data/demo/week_fixture.json --date 2026-07-13 \
         --as-of 2026-07-13T08:00:00-04:00 --format text

   Expect: 2 appointments (Marcus J 10:00 AM, Devon P 2:00 PM) and three
   walk-in windows, all fitting any service.
```

- [ ] **Step 3: Run the full suite**

Run: `.venv/bin/pytest`
Expected: 65 passed

- [ ] **Step 4: Manual verification with system python3 from repo root**

Run the runbook step 5 command, plus the mid-day variant:
```bash
python3 skills/day-sheet/scripts/day_sheet.py data/demo/week_fixture.json --date 2026-07-13 --as-of 2026-07-13T13:30:00-04:00 --format text
```
Expected: morning run matches the spec's text sample; mid-day run shows
`Next up: Devon P at 2:00 PM (Haircut)` and a first window of
`1:30 PM–2:00 PM (30m) — Beard Trim, Haircut, Kids Cut`. No tracebacks.

- [ ] **Step 5: Commit**

```bash
git add skills/day-sheet/SKILL.md README.md
git commit -m "feat: add day-sheet SKILL.md and runbook"
```

**Phase 3 ends here.**
