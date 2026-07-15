# Day Sheet Skill — Design Spec

**Date:** 2026-07-14
**Status:** Approved (owner: "biggest problem is remembering who's coming and walk-ins")
**Scope:** Third Cowork skill, `day-sheet` — a forward-looking morning briefing that answers the barber's two daily questions: *who's coming today* and *can I take this walk-in right now*.

## Why

The existing skills look backward (last week's no-shows, last week's report). The client's actual daily pain is forward: forgetting booked appointments and taking walk-ins that collide with them. The walk-in question is already solved math — `slots.free_windows` + service durations — pointed at *today* with the current time.

## Decisions

1. **One new skill, one script.** `skills/day-sheet/scripts/day_sheet.py`. Unlike weekly-summary, no separate renderer: the text output is ~15 lines, so the script takes `--format json` (default, for tooling/tests) or `--format text` (the message the owner receives). Splitting would add a file with no reuse.
2. **Logic lives in the library**, same as always: new module `barber_ops/day.py` with `build_day_sheet(bookings, cfg, services, day, as_of) -> dict`. The script is a thin CLI.
3. **Walk-in semantics:** for the given day, take `free_windows(min = shortest service duration)`; drop windows already over (`end <= as_of`); clip the current window to start at `as_of`. For each remaining window, list which services fit its remaining length (`duration_min <= window minutes`); when all fit, the text renderer says "any service".
4. **Now/next:** relative to `as_of` — the booking currently in progress (if any) and the next upcoming booking today.
5. **Same guardrails and conventions** as the other skills: explicit tz-aware `--as-of` (exit 2 if naive), cancelled bookings excluded, `rejected` events reported, no network I/O, title convention unchanged.
6. **Delivery is out of scope for the code.** The SKILL.md tells Claude to produce the text sheet each morning (live: fetch today's events via the Calendar connector; demo: fixture). Whether it's texted by the operator or scheduled in Cowork is a service-delivery choice, not code.

## Output contract (JSON)

```json
{
  "shop_name": "...",
  "date": "2026-07-13", "weekday": "mon",
  "closed": false, "open": "09:00", "close": "18:00",
  "appointments": [
    {"start": iso, "end": iso, "service": "Fade", "customer": "Marcus J",
     "duration_min": 45, "status": "confirmed", "marker": null}
  ],
  "booked_minutes": 75,
  "now": null | {appointment},
  "next": null | {appointment},
  "walkin_windows": [
    {"start": iso, "end": iso, "minutes": 195, "fits": ["Beard Trim", ...], "fits_all": true}
  ],
  "rejected": [...]
}
```

Closed day: `closed: true`, empty lists, `open`/`close` null.

## Text format (representative)

```
TODAY AT SHARP CUTS BARBERSHOP — Mon Jul 13
Hours: 9:00 AM–6:00 PM
2 appointments · 1h 15m booked

Lineup:
  10:00 AM  Fade — Marcus J (45m)
   2:00 PM  Haircut — Devon P (30m)

Next up: Marcus J at 10:00 AM (Fade)

Walk-in room:
  9:00 AM–10:00 AM (1h 0m) — any service
  10:45 AM–2:00 PM (3h 15m) — any service
  2:30 PM–6:00 PM (3h 30m) — any service
```

With a booking in progress, a line `In the chair: <customer> until <end>` appears before `Next up`. Partial windows show remaining time from now. Closed day: header + `Closed today.`

## Demo truth (fixture, no reseeding needed)

- `--date 2026-07-13 --as-of 2026-07-13T08:00:00-04:00`: 2 appointments (Marcus J Fade 10:00, Devon P Haircut 2:00), 75 booked minutes, next = Marcus J, 3 windows (60/195/210 min), all fit every service.
- `--as-of 2026-07-13T13:30:00-04:00`: current window clipped to 1:30–2:00 PM (30 min) — fits Beard Trim, Haircut, Kids Cut only; next = Devon P.
- `--as-of 2026-07-13T10:15:00-04:00`: now = Marcus J (in the chair until 10:45), next = Devon P.
- `--date 2026-07-14`: 1 appointment (Sam K Beard Trim 9:00), one window 9:20 AM–6:00 PM.
- `--date 2026-07-12`: closed.

## Out of scope

- The "Today" web page (Size 2 UI) — revisit after the morning text proves itself.
- Any write-back, reminders, or sending. Drafting confirmations stays in appointment-management.
