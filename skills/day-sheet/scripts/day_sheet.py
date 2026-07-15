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
