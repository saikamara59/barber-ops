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
