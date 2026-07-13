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
    if rev.get("unknown_services"):
        names = ", ".join(u["service"] for u in rev["unknown_services"])
        lines += [
            f"> ⚠️ {len(rev['unknown_services'])} booking(s) use services not in the price map "
            f"({names}) — excluded from all revenue figures.",
            "",
        ]
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
