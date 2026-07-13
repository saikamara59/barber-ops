# Barber Ops — Live Cowork Demo Runbook

Stage a live demo of both skills against a real Google Calendar and Gmail,
via Cowork's connectors. Offline fallback: the README runbook needs none of this.

## Verified platform facts (2026-07-13)

- **Cowork custom skills**: managed under **Customize > Skills** — upload a ZIP
  of the skill folder, or place folders in `~/.claude/skills/<name>/`.
- **Gmail connector**: reads/searches mail and **creates drafts; it cannot
  send**. This matches the skills' never-send guardrail exactly — say so in
  the demo.
- **Google Calendar connector**: view events (incl. shared calendars),
  **create/update/delete events** — covers the reschedule flow.
- **Cowork folder access**: Claude reads/writes only folders you connect.
  Connect the `barber-ops` repo folder so the skills' scripts, library, and
  data files are available; SKILL.md commands run from the repo root.

## One-time setup

### 1. Google Cloud OAuth client (operator machine, ~5 min)

1. [console.cloud.google.com](https://console.cloud.google.com) → new project
   (e.g. `barber-ops-demo`).
2. APIs & Services → Library → enable **Google Calendar API**.
3. OAuth consent screen → External → add yourself as a test user.
4. Credentials → Create credentials → **OAuth client ID → Desktop app** →
   download JSON → save as `credentials.json` in the repo root (gitignored).

### 2. Demo calendar

In Google Calendar, create a **dedicated calendar** named `Sharp Cuts Demo`
(Settings → Add calendar). Copy its **Calendar ID** from the calendar's
settings page (looks like `...@group.calendar.google.com`). Never seed your
personal calendar — the seeder inserts 25 events and re-running it duplicates
them. To reset a demo, delete and recreate the calendar.

### 3. Seed it

```bash
.venv/bin/python tools/seed_calendar.py --calendar-id <CALENDAR_ID>
```

(Google libs are installed in `.venv`; a browser window opens once for OAuth,
then the token is cached in `token.json`.)

**Date alignment rule:** the fixture's week is Mon 2026-07-06 → Sat, with
follow-on bookings Mon/Tue. Pass `--week-of <Monday of LAST week relative to
demo day>` so "last week" in the demo matches the seeded data. Demoing during
the week of 2026-07-13: no flag needed (default already aligns). Demo slips a
week: `--week-of 2026-07-13`. Expect `created 25 events, skipped 1 cancelled`.

### 4. Cowork workspace

1. Claude desktop app → Cowork → connect the `barber-ops` repo folder.
2. Settings → Connectors: connect **Google Calendar** and **Gmail** with the
   demo Google account.
3. Customize > Skills → upload `dist/appointment-management-skill.zip` and
   `dist/weekly-summary-skill.zip` (built by `scripts/build_skill_zips.sh`,
   see below) and toggle them on. (Alternative: copy the two folders under
   `skills/` into `~/.claude/skills/`.)

## Demo script (~10 min)

Keep asks scoped to **last week** — the fixture's untagged bookings on demo
day itself would otherwise show up as extra no-show candidates.

1. **Weekly report** — "How did last week go at the shop?"
   → Claude fetches the week via the Calendar connector, runs the
   weekly-summary pipeline, presents the one-pager: $680 realized, $90 lost
   to no-shows, $105 unconfirmed, Tuesday afternoon wide open.
   *Point out:* every number came from a deterministic script, not the model.

2. **No-show review** — "Any no-shows last week?"
   → 3 confirmed (Alan, Chris, Ethan), 3 candidates needing your call.
   Confirm one candidate, reject the others.
   *Point out:* untagged ≠ no-show; the skill refuses to act without owner
   confirmation.

3. **The wow moment** — "Draft rebooking messages, email where possible."
   → Chris O has an email on file: a draft appears in **Gmail's Drafts
   folder**. Open Gmail live and show it sitting there unsent.
   *Point out:* structurally unable to send — connector has no send, scripts
   have no send, SKILL.md forbids it. Three layers.

4. **Reschedule** — paste: *"Hey it's Marcus, can't make my fade Monday,
   any time Tuesday?"*
   → propose_slots offers Tuesday windows; pick one; Claude updates the
   calendar event via the connector. Show the moved event in Google Calendar.

5. **Close** — "This is the Starter tier: two workflows, your calendar, your
   inbox, drafts-only by design. Runs the same on a seeded demo calendar or
   your real one."

## Troubleshooting

- **OAuth error `access_denied`**: you forgot to add yourself as a test user
  on the consent screen.
- **Skill scripts fail in Cowork**: confirm the repo folder is connected and
  commands run from its root; system `python3` needs pyyaml
  (`python3 -m pip install --user pyyaml`).
- **Wrong week in report**: recheck the `--week-of` alignment rule and the
  `--week-start` you tell Claude to use.
- **Duplicate events**: you seeded twice — delete and recreate the demo
  calendar.
