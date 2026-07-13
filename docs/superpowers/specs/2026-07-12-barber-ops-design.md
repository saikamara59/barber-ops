# Barber Ops — Design Spec

**Date:** 2026-07-12
**Status:** Approved
**Scope:** Starter-tier demo package for a fractional AI ops service, built as Claude Cowork skills over Gmail + Google Calendar connectors.

## Decisions (settled during brainstorming)

1. **Skills-first, shared lib.** No FastAPI/Twilio bot. The deliverable is a skills package plus a small shared Python library. A bot can be added later without rework.
2. **Connector-fed pure-logic scripts.** Claude fetches calendar events and creates Gmail drafts via Cowork connectors. Skill scripts are pure functions over JSON: no network, no credentials, no state.
3. **No-show detection: marker convention + candidates.** The barber tags completed events with `[showed]` and known misses with `[no-show]` in the event title. Past events tagged `[no-show]` are confirmed no-shows. Past untagged events are *candidates* only — the skill must get owner confirmation before drafting any rebook message.
4. **Gmail scope: drafts only.** The skill never sends. Email follow-ups are created as Gmail drafts via the connector; SMS follow-ups are rendered as copy-paste text. Reschedule requests enter the conversation as pasted/forwarded text from the owner.
5. **Demo mode: JSON fixtures + optional calendar seeder.** Scripts run identically on fixture JSON or connector-fetched JSON. `tools/seed_calendar.py` (runs on the operator's machine, never inside a skill) can push the fixture into a real Google Calendar for a live connector demo.

## Architecture

Barber Ops is a Cowork skills package, not a service. Claude is the runtime:

```
Cowork conversation
 ├─ Google Calendar connector ──> events JSON ──┐
 ├─ Gmail connector <── drafts (never send) <───┤
 └─ Skill (SKILL.md procedure) ── invokes ──> scripts/*.py (pure logic, barber_ops lib)
```

Connectors do all I/O. SKILL.md files carry the procedure and guardrails. Python scripts handle everything that must be exact: date math, money, gap analysis, classification. Because scripts are pure, the same code path serves live demos, offline demos, and tests.

## Components

### `barber_ops/` — shared library

- **`models.py`** — `Booking` dataclass and a normalizer from Google Calendar event JSON (or fixture JSON in the same shape) to `Booking`. Parses the title convention `"<Service> — <Customer Name> [marker]"`, e.g. `"Fade — Marcus J [showed]"`. Marker is one of `[showed]`, `[no-show]`, or absent. Cancelled events are recognized via the Calendar `status: "cancelled"` field.
- **`services.py`** — loads `data/services.yaml` mapping service → `{duration_min, price}`. Demo menu: Haircut $35 (30m), Fade $45 (45m), Kids Cut $25 (30m), Beard Trim $20 (20m), Cut + Beard $50 (60m), Design $60 (60m).
- **`drafting.py`** — channel-neutral draft objects `{channel: "sms"|"email", to, subject?, body}` rendered from templates. No send capability exists anywhere in the package.

### `skills/appointment-management/` — built first

`SKILL.md` in Agent Skills format (YAML frontmatter with `name` and `description`, then procedure) — valid for both Cowork and Claude Code. Scripts:

- **`detect_no_shows.py`** — stdin/file: events JSON + an "as of" timestamp; stdout: `{confirmed: [...], candidates: [...]}`. Only past events are classified; tagged `[no-show]` → confirmed, untagged past → candidate.
- **`propose_slots.py`** — inputs: events JSON, service name, date range; output: free slots long enough for the service's duration within business hours (from `data/config.yaml`).
- **`draft_followup.py`** — inputs: confirmed no-shows (or a reschedule confirmation) + channel preference; output: draft objects.

SKILL.md guardrails (hard rules stated in the procedure):
- Candidates are never acted on without explicit owner confirmation in the conversation.
- Drafts are never sent; email drafts go to the Gmail drafts surface only.
- Events the scripts reject as malformed are reported to the owner, not silently dropped.

### `skills/weekly-summary/` — built second, after review of skill 1

Scripts for weekly revenue rollup (bookings × price map, split by showed/no-show/unmarked), empty-slot and gap-pattern analysis, and a one-page Markdown owner report. Detailed design deferred to phase 2; the shared lib (`models.py`, `services.py`) is designed to serve it as-is.

### Demo assets

- **`data/demo/week_fixture.json`** — one realistic week for the persona "Sharp Cuts Barbershop": ~25 bookings mixing `[showed]`, `[no-show]`, untagged, and cancelled events, with a deliberate Tuesday-afternoon gap pattern for the weekly summary to find. Shape matches Google Calendar `events.list` items (subset of fields: `id`, `summary`, `description`, `start`, `end`, `status`, plus attendee email/phone in `description`).
- **`tools/seed_calendar.py`** — standalone operator-machine script using `google-api-python-client` with OAuth; pushes the fixture into a named Google Calendar. The only file in the repo that touches Google APIs.

## Data flow — appointment-management happy path

1. Owner asks "any no-shows this week?" → skill directs Claude to fetch the week's events via the Calendar connector (demo mode: read `week_fixture.json`).
2. Claude runs `detect_no_shows.py` on the events JSON → confirmed + candidates.
3. Claude presents both lists; owner confirms/rejects candidates.
4. `draft_followup.py` renders a rebook draft per confirmed no-show; email drafts are created in Gmail as drafts, SMS drafts shown as text to copy.
5. Reschedule path: owner pastes the customer's message → Claude extracts intent conversationally (no separate intent-parsing module) → `propose_slots.py` → owner picks a slot → Claude updates the event via the connector → confirmation draft produced.

## Error handling

- Scripts validate input and exit non-zero with a specific message on malformed events (missing start/end, unparseable title) — no guessing.
- Timezone: taken from the calendar's `timeZone` field when present, else `data/config.yaml`. All past/future comparisons are timezone-aware; no naive-UTC logic.
- The "as of" timestamp is always passed in explicitly (by Claude or tests), never read from the system clock inside classification logic, so runs are reproducible.

## Testing

- `pytest` over the pure scripts, with `week_fixture.json` as shared test data.
- Coverage targets: every marker state in no-show classification; slot proposal edges (overlapping events, business-hour boundaries, service too long for gap); price lookups including unknown services; draft rendering for both channels.
- No mocks — nothing under test performs I/O.
- Final manual pass: run each script CLI-style on the fixture, exactly as Claude would in Cowork.

## Directory layout

```
barber-ops/
├── barber_ops/              # shared lib: models.py, services.py, drafting.py
├── skills/
│   ├── appointment-management/{SKILL.md, scripts/}
│   └── weekly-summary/{SKILL.md, scripts/}      # phase 2
├── data/{services.yaml, config.yaml, demo/week_fixture.json}
├── tools/seed_calendar.py
├── tests/
└── README.md                # demo runbook: offline path + live-calendar path
```

## Build order

1. Shared lib + `services.yaml` + `config.yaml` + demo fixture.
2. `appointment-management` skill end to end (scripts, SKILL.md, tests, runbook section).
3. **Owner review checkpoint.**
4. `weekly-summary` skill.
5. `tools/seed_calendar.py` + live-demo runbook section (can land alongside step 4).

## Out of scope

- Sending any message automatically (structurally impossible in this package).
- Twilio/FastAPI inbound booking bot.
- Reading the Gmail inbox.
- Multi-barber/multi-calendar support (single calendar, single persona for Starter tier).
