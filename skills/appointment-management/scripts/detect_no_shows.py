#!/usr/bin/env python3
"""Classify past calendar bookings as confirmed no-shows or candidates.

Input (file arg or stdin): {"timeZone": str, "events": [...]} in Google
events.list shape, or a bare event list.
Output (stdout): {"as_of", "confirmed", "candidates", "rejected"}.

Rules: only events that ended before --as-of are classified. [no-show] tag ->
confirmed; untagged -> candidate (owner must confirm); [showed] and cancelled
events are excluded. This script never contacts any external service.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from barber_ops.config import load_config  # noqa: E402
from barber_ops.models import normalize_events  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("events_file", nargs="?", help="events JSON file (default: stdin)")
    parser.add_argument("--as-of", required=True, help="ISO timestamp with UTC offset")
    parser.add_argument("--config", default=str(REPO_ROOT / "data" / "config.yaml"))
    args = parser.parse_args()

    try:
        as_of = datetime.fromisoformat(args.as_of)
    except ValueError:
        print(f"error: invalid --as-of {args.as_of!r}", file=sys.stderr)
        return 2
    if as_of.tzinfo is None:
        print("error: --as-of must include a UTC offset, e.g. 2026-07-12T09:00:00-04:00", file=sys.stderr)
        return 2

    raw = json.loads(Path(args.events_file).read_text()) if args.events_file else json.load(sys.stdin)
    events = raw["events"] if isinstance(raw, dict) else raw
    default_tz = (raw.get("timeZone") if isinstance(raw, dict) else None) or load_config(args.config).timezone

    bookings, rejected = normalize_events(events, default_tz)
    confirmed, candidates = [], []
    for b in bookings:
        if b.status == "cancelled" or b.end >= as_of or b.marker == "showed":
            continue
        (confirmed if b.marker == "no-show" else candidates).append(b.to_dict())

    json.dump(
        {"as_of": as_of.isoformat(), "confirmed": confirmed, "candidates": candidates, "rejected": rejected},
        sys.stdout, indent=2,
    )
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
