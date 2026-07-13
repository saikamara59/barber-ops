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
