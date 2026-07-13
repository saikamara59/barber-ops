---
name: weekly-summary
description: Build a one-page weekly owner report for a barber shop from Google Calendar bookings — revenue estimated from the service price map, no-show costs, schedule utilization, and gap patterns. Use when the owner asks for a weekly report, revenue summary, how the week went, or where the empty slots are.
---

# Weekly Summary

Produces a one-page Markdown report for a single-calendar barber shop.
Booking events use the title convention `<Service> — <Customer Name> [marker]`
(em dash), where the marker is `[showed]`, `[no-show]`, or absent. The service
menu and prices live in `data/services.yaml`; business hours in
`data/config.yaml`.

## Hard rules

1. **Never invent numbers.** Every figure in the report comes from the
   scripts' output. If a number is not in the JSON, do not state it.
2. **Report rejected events.** If the summary JSON has a non-empty `rejected`
   list, show it to the owner — those events are excluded from all figures.
3. **Unconfirmed ≠ no-show.** Untagged past appointments are reported as
   unconfirmed revenue. Suggest tagging them; offer the appointment-management
   skill for no-show follow-ups. Do not draft messages from this skill.

## Getting events

- **Live:** fetch the report week (Monday through Sunday) from the Google
  Calendar connector as `{"timeZone": "...", "events": [...]}` with each
  event's `id`, `summary`, `description`, `start`, `end`, `status`.
- **Demo mode:** use `data/demo/week_fixture.json` (report week
  `--week-start 2026-07-06`, "today" is Sun 2026-07-12). Requires pyyaml for
  system python3 (`python3 -m pip install --user pyyaml`).

## Workflow

1. Get events for the week the owner asked about.
2. Run (from the repo root):
   `python3 skills/weekly-summary/scripts/weekly_summary.py <events.json> --week-start <monday YYYY-MM-DD> --as-of <current time, ISO with UTC offset>`
3. Pipe (or pass) the JSON through the renderer:
   `python3 skills/weekly-summary/scripts/render_report.py`
4. Present the rendered Markdown report to the owner verbatim, then offer:
   - tagging help for unconfirmed appointments,
   - the appointment-management skill for no-show rebooking drafts,
   - deeper detail on any day's free windows (they are in the JSON under
     `gaps.per_day[].free_windows`).
