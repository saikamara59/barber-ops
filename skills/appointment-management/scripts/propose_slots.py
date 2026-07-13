#!/usr/bin/env python3
"""Propose free booking windows for a service over a date range.

Input (file arg or stdin): {"timeZone": str, "events": [...]} in Google
events.list shape, or a bare event list.
Output (stdout): {"service", "duration_min", "windows": [{"start","end"}], "rejected"}.

Windows fall inside business hours (data/config.yaml), exclude non-cancelled
bookings, and are at least the service's duration long. This script never
contacts any external service.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from barber_ops.config import load_config  # noqa: E402
from barber_ops.models import normalize_events  # noqa: E402
from barber_ops.services import get_service, load_services  # noqa: E402
from barber_ops.slots import windows_for_range  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("events_file", nargs="?", help="events JSON file (default: stdin)")
    parser.add_argument("--service", required=True)
    parser.add_argument("--from", dest="from_day", required=True, help="YYYY-MM-DD")
    parser.add_argument("--to", dest="to_day", required=True, help="YYYY-MM-DD")
    parser.add_argument("--config", default=str(REPO_ROOT / "data" / "config.yaml"))
    parser.add_argument("--services", default=str(REPO_ROOT / "data" / "services.yaml"))
    args = parser.parse_args()

    cfg = load_config(args.config)
    try:
        service = get_service(load_services(args.services), args.service)
    except KeyError as exc:
        print(f"error: {exc.args[0]}", file=sys.stderr)
        return 2

    try:
        first, last = date.fromisoformat(args.from_day), date.fromisoformat(args.to_day)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if last < first:
        print(f"error: invalid range {args.from_day}..{args.to_day}", file=sys.stderr)
        return 2

    raw = json.loads(Path(args.events_file).read_text()) if args.events_file else json.load(sys.stdin)
    events = raw["events"] if isinstance(raw, dict) else raw
    default_tz = (raw.get("timeZone") if isinstance(raw, dict) else None) or cfg.timezone

    bookings, rejected = normalize_events(events, default_tz)
    windows = windows_for_range(bookings, cfg, first, last, service.duration_min)

    json.dump(
        {
            "service": service.name,
            "duration_min": service.duration_min,
            "windows": [{"start": s.isoformat(), "end": e.isoformat()} for s, e in windows],
            "rejected": rejected,
        },
        sys.stdout, indent=2,
    )
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
