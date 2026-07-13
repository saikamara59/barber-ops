---
name: appointment-management
description: Detect no-shows from Google Calendar state, handle reschedule requests, and draft (never send) SMS/email follow-ups for a barber shop. Use when the shop owner asks about no-shows, missed appointments, rebooking, rescheduling, or customer follow-up messages.
---

# Appointment Management

Manages appointments for a single-calendar barber shop. Booking events use the
title convention `<Service> — <Customer Name> [marker]` (em dash), where the
marker is `[showed]`, `[no-show]`, or absent. Customer contact info lives in
the event description as `phone: ...` and `email: ...` lines. The service
menu and business hours live in `data/services.yaml` and `data/config.yaml`.

## Hard rules

1. **NEVER send a message.** Email output goes to Gmail as a DRAFT only
   (create the draft via the Gmail connector; do not send it). SMS output is
   text for the owner to copy into their phone. Do not use any send
   capability even if one is available.
2. **Untagged past events are no-show CANDIDATES, not no-shows.** Always show
   candidates to the owner and get explicit confirmation before drafting
   anything for them.
3. **Report rejected events.** If a script output contains a non-empty
   `rejected` list, show it to the owner. Never silently drop events.

## Getting events

- **Live:** fetch the relevant date range from the Google Calendar connector
  and save it as JSON shaped like `{"timeZone": "...", "events": [...]}`,
  where each event keeps its `id`, `summary`, `description`, `start`, `end`,
  and `status` fields.
- **Demo mode:** use `data/demo/week_fixture.json` (a seeded week for the
  demo shop "Sharp Cuts Barbershop"; "today" in the demo is Sun 2026-07-12).

**Note:** the scripts require `pyyaml`. Install with `python3 -m pip install pyyaml`.

## Workflow 1: No-show review

1. Get events for the period the owner asked about.
2. Run (from the repo root):
   `python3 skills/appointment-management/scripts/detect_no_shows.py <events.json> --as-of <current time, ISO with UTC offset>`
3. Present `confirmed` (tagged `[no-show]`) and `candidates` (untagged past
   events) as two separate lists, with dates, services, and contact info.
4. Ask the owner which candidates were actually no-shows. Only
   owner-confirmed candidates join the rebook list.

## Workflow 2: Draft rebook follow-ups

1. Build the payload from Workflow 1 results:
   `{"mode": "rebook", "channel_preference": "sms", "bookings": [<confirmed + owner-approved candidates>]}`
   (ask the owner whether they prefer sms or email as the primary channel).
2. Run: `python3 skills/appointment-management/scripts/draft_followup.py` with
   the payload on stdin (or a file argument).
3. For each draft: `channel: "email"` → create a Gmail DRAFT via the
   connector; `channel: "sms"` → show the text for the owner to copy.
4. Report any `skipped` entries (customers with no contact info) to the owner.

## Workflow 3: Reschedule request

1. The owner pastes or forwards the customer's message. Extract the customer
   name, the service, and any timing constraints conversationally.
2. Find the customer's existing event in the fetched events (match by
   customer name in the title).
3. Run: `python3 skills/appointment-management/scripts/propose_slots.py <events.json> --service <Service> --from <YYYY-MM-DD> --to <YYYY-MM-DD>`
4. Offer the owner 2-3 concrete start times inside the returned windows.
5. After the owner picks a time: update the calendar event via the connector
   (keep the title convention; do not add a marker to future events).
6. Draft a confirmation:
   `{"mode": "reschedule", "channel_preference": "sms", "booking": {...}, "new_start": "<ISO>"}`
   through `draft_followup.py`, then handle the draft per Hard rule 1.
