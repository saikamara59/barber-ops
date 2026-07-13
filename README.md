# Barber Ops

Starter-tier demo package for a fractional AI ops service: Claude Cowork
skills for a barber shop, built on the Gmail and Google Calendar connectors.

- `skills/appointment-management/` — no-show detection, reschedules, and
  draft-only follow-up messages. See its `SKILL.md`.
- `skills/weekly-summary/` — weekly revenue + gap report. See its `SKILL.md`.
- `barber_ops/` — shared pure-Python library (no network, no credentials).
- `data/demo/week_fixture.json` — a seeded week for "Sharp Cuts Barbershop".

## Setup

    python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
    .venv/bin/pytest

## Demo runbook (offline, no Google account)

"Today" in the demo data is Sunday 2026-07-12.

1. No-show review:

       python3 skills/appointment-management/scripts/detect_no_shows.py \
         data/demo/week_fixture.json --as-of 2026-07-12T09:00:00-04:00

   Expect 3 confirmed no-shows (Alan R, Chris O, Ethan Q) and 3 candidates
   (Nick D, Jordan F, Rob T).

2. Draft rebook messages (pipe step 1's confirmed list in as `bookings`):

       python3 skills/appointment-management/scripts/detect_no_shows.py \
         data/demo/week_fixture.json --as-of 2026-07-12T09:00:00-04:00 \
       | python3 -c "import json,sys; d=json.load(sys.stdin); print(json.dumps({'mode':'rebook','channel_preference':'sms','bookings':d['confirmed']}))" \
       | python3 skills/appointment-management/scripts/draft_followup.py

3. Propose reschedule slots for a Fade early next week:

       python3 skills/appointment-management/scripts/propose_slots.py \
         data/demo/week_fixture.json --service Fade --from 2026-07-13 --to 2026-07-14

4. Weekly owner report:

       python3 skills/weekly-summary/scripts/weekly_summary.py \
         data/demo/week_fixture.json --week-start 2026-07-06 --as-of 2026-07-12T09:00:00-04:00 \
       | python3 skills/weekly-summary/scripts/render_report.py

   Expect: $680 realized, $90 missed to no-shows, $105 unconfirmed, largest
   open block Tue Jul 7 12:00 PM–6:00 PM.

In Cowork, the `appointment-management` skill drives these same scripts with
events fetched live from the Google Calendar connector; email follow-ups are
created as Gmail drafts and are never sent.

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
