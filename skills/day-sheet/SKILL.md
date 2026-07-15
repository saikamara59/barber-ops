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
