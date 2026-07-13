#!/usr/bin/env python3
"""Render rebook / reschedule-confirmation drafts. This script NEVER sends anything.

Input (file arg or stdin):
  {"mode": "rebook", "channel_preference": "sms"|"email", "bookings": [...]}
  {"mode": "reschedule", "channel_preference": ..., "booking": {...}, "new_start": iso}
Booking dicts are detect_no_shows.py output items.
Output (stdout): {"drafts": [...], "skipped": [{"event_id","reason"}]}.

Falls back to the other channel when the preferred one has no contact info.
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
from barber_ops.drafting import (  # noqa: E402
    MissingContact,
    render_rebook_draft,
    render_reschedule_confirmation,
)
from barber_ops.models import Booking  # noqa: E402


def _try_channels(render, preferred: str):
    for channel in (preferred, "email" if preferred == "sms" else "sms"):
        try:
            return render(channel)
        except MissingContact:
            continue
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("payload_file", nargs="?", help="payload JSON file (default: stdin)")
    parser.add_argument("--config", default=str(REPO_ROOT / "data" / "config.yaml"))
    args = parser.parse_args()

    payload = json.loads(Path(args.payload_file).read_text()) if args.payload_file else json.load(sys.stdin)
    cfg = load_config(args.config)

    preferred = payload.get("channel_preference", "sms")
    if preferred not in ("sms", "email"):
        print(f"error: channel_preference must be 'sms' or 'email', got {preferred!r}", file=sys.stderr)
        return 2

    mode = payload.get("mode")
    drafts, skipped = [], []
    if mode == "rebook":
        for d in payload.get("bookings", []):
            b = Booking.from_dict(d)
            draft = _try_channels(lambda ch, b=b: render_rebook_draft(b, cfg, ch), preferred)
            if draft is None:
                skipped.append({"event_id": b.event_id, "reason": f"no contact info for {b.customer}"})
            else:
                drafts.append(draft.to_dict())
    elif mode == "reschedule":
        if "booking" not in payload or "new_start" not in payload:
            print("error: reschedule payload requires 'booking' and 'new_start'", file=sys.stderr)
            return 2
        b = Booking.from_dict(payload["booking"])
        try:
            new_start = datetime.fromisoformat(payload["new_start"])
        except (TypeError, ValueError):
            print(f"error: could not parse new_start {payload['new_start']!r}", file=sys.stderr)
            return 2
        if new_start.tzinfo is None:
            print(
                "error: new_start must include a UTC offset, e.g. 2026-07-14T10:00:00-04:00",
                file=sys.stderr,
            )
            return 2
        draft = _try_channels(lambda ch: render_reschedule_confirmation(b, new_start, cfg, ch), preferred)
        if draft is None:
            skipped.append({"event_id": b.event_id, "reason": f"no contact info for {b.customer}"})
        else:
            drafts.append(draft.to_dict())
    else:
        print(f"error: mode must be 'rebook' or 'reschedule', got {mode!r}", file=sys.stderr)
        return 2

    json.dump({"drafts": drafts, "skipped": skipped}, sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
