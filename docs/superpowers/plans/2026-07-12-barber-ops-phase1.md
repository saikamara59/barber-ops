# Barber Ops Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `barber_ops` shared library, demo data, and the complete `appointment-management` Cowork skill (scripts + SKILL.md + tests), ending at the owner review checkpoint.

**Architecture:** Cowork connectors (Google Calendar, Gmail) do all I/O; skill scripts are pure functions over JSON piped in by Claude. A small installed-in-place Python package (`barber_ops`) holds the Booking model/normalizer, service menu, shop config, slot math, and draft rendering. Scripts add the repo root to `sys.path` so they run without installation (as they will inside Cowork).

**Tech Stack:** Python ≥3.10, PyYAML (only runtime dep), pytest (only dev dep), stdlib `zoneinfo` for timezones.

**Spec:** `docs/superpowers/specs/2026-07-12-barber-ops-design.md`

## Global Constraints

- Nothing in this package may send a message. Email output is draft objects only; no Gmail/SMTP/Twilio client code anywhere.
- Scripts and library do no network I/O and read only files passed to them (or the repo's `data/*.yaml` defaults).
- Event title convention: `<Service> — <Customer Name> [marker]` with em-dash separator `" — "`; marker is `[showed]`, `[no-show]`, or absent.
- Untagged past events are no-show **candidates**, never confirmed no-shows.
- All datetime comparisons are timezone-aware; the "as of" timestamp is always an explicit input, never the system clock.
- Malformed events go to a `rejected` list with a reason; never silently dropped, never guessed at.
- Dependencies: `pyyaml` (runtime), `pytest` (dev). Nothing else.
- Demo persona: "Sharp Cuts Barbershop", timezone `America/New_York`, fixture week Mon 2026-07-06 → Tue 2026-07-14.
- Service menu (exact): Haircut $35/30m, Fade $45/45m, Kids Cut $25/30m, Beard Trim $20/20m, Cut + Beard $50/60m, Design $60/60m.

---

### Task 1: Project scaffolding + service menu (`barber_ops.services`)

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `barber_ops/__init__.py`, `data/services.yaml`, `barber_ops/services.py`
- Test: `tests/test_services.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: `Service` frozen dataclass (`name: str`, `duration_min: int`, `price: int`); `load_services(path) -> dict[str, Service]` (keys lowercased); `get_service(services, name) -> Service` (case/whitespace-insensitive, raises `KeyError` listing the menu). Later tasks import these from `barber_ops.services`.

- [ ] **Step 1: Scaffold project files**

`pyproject.toml`:
```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "barber-ops"
version = "0.1.0"
description = "Barber Ops shared library and Cowork skills package"
requires-python = ">=3.10"
dependencies = ["pyyaml>=6.0"]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[tool.setuptools]
packages = ["barber_ops"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

`.gitignore`:
```
.venv/
__pycache__/
*.pyc
*.egg-info/
```

`barber_ops/__init__.py`: empty file.

`data/services.yaml`:
```yaml
services:
  Haircut: {duration_min: 30, price: 35}
  Fade: {duration_min: 45, price: 45}
  Kids Cut: {duration_min: 30, price: 25}
  Beard Trim: {duration_min: 20, price: 20}
  Cut + Beard: {duration_min: 60, price: 50}
  Design: {duration_min: 60, price: 60}
```

Then create the environment:
```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
```
Expected: installs `barber-ops` editable with pyyaml and pytest. (The install will warn until `barber_ops/services.py` exists in Step 3 — that's fine; re-run is not needed because the install is editable.)

- [ ] **Step 2: Write the failing test**

`tests/test_services.py`:
```python
from pathlib import Path

import pytest

from barber_ops.services import get_service, load_services

ROOT = Path(__file__).resolve().parents[1]


def _services():
    return load_services(ROOT / "data" / "services.yaml")


def test_load_services_menu():
    services = _services()
    assert len(services) == 6
    fade = get_service(services, "Fade")
    assert fade.name == "Fade"
    assert fade.duration_min == 45
    assert fade.price == 45


def test_get_service_is_case_and_whitespace_insensitive():
    assert get_service(_services(), "  cut + beard ").price == 50


def test_unknown_service_error_lists_menu():
    with pytest.raises(KeyError) as exc:
        get_service(_services(), "Perm")
    assert "known services" in str(exc.value)
    assert "Fade" in str(exc.value)
```

Run: `.venv/bin/pytest tests/test_services.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'barber_ops.services'`

- [ ] **Step 3: Implement `barber_ops/services.py`**

```python
"""Service menu: name -> duration and price."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Service:
    name: str
    duration_min: int
    price: int


def load_services(path: str | Path) -> dict[str, Service]:
    raw = yaml.safe_load(Path(path).read_text())
    services: dict[str, Service] = {}
    for name, spec in raw["services"].items():
        services[name.lower()] = Service(
            name=name,
            duration_min=int(spec["duration_min"]),
            price=int(spec["price"]),
        )
    return services


def get_service(services: dict[str, Service], name: str) -> Service:
    try:
        return services[name.strip().lower()]
    except KeyError:
        known = ", ".join(sorted(s.name for s in services.values()))
        raise KeyError(f"unknown service {name!r}; known services: {known}") from None
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_services.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .gitignore barber_ops/ data/services.yaml tests/test_services.py
git commit -m "feat: scaffold barber_ops package with service menu"
```

---

### Task 2: Shop config (`barber_ops.config`)

**Files:**
- Create: `data/config.yaml`, `barber_ops/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `DayHours` frozen dataclass (`open: datetime.time`, `close: datetime.time`); `ShopConfig` frozen dataclass (`shop_name: str`, `timezone: str`, `booking_contact: str`, `hours: dict[str, DayHours | None]` keyed `mon`..`sun`, `None` = closed); `load_config(path) -> ShopConfig`. Later tasks import from `barber_ops.config`.

- [ ] **Step 1: Write `data/config.yaml`**

```yaml
shop_name: Sharp Cuts Barbershop
timezone: America/New_York
booking_contact: "(555) 010-7788"
business_hours:
  mon: {open: "09:00", close: "18:00"}
  tue: {open: "09:00", close: "18:00"}
  wed: {open: "09:00", close: "18:00"}
  thu: {open: "09:00", close: "19:00"}
  fri: {open: "09:00", close: "19:00"}
  sat: {open: "08:00", close: "16:00"}
  sun: null
```

- [ ] **Step 2: Write the failing test**

`tests/test_config.py`:
```python
from datetime import time
from pathlib import Path

from barber_ops.config import load_config

ROOT = Path(__file__).resolve().parents[1]


def test_load_config():
    cfg = load_config(ROOT / "data" / "config.yaml")
    assert cfg.shop_name == "Sharp Cuts Barbershop"
    assert cfg.timezone == "America/New_York"
    assert cfg.hours["thu"].close == time(19, 0)
    assert cfg.hours["sat"].open == time(8, 0)
    assert cfg.hours["sun"] is None
```

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'barber_ops.config'`

- [ ] **Step 3: Implement `barber_ops/config.py`**

```python
"""Shop configuration: identity, timezone, business hours."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from pathlib import Path

import yaml


@dataclass(frozen=True)
class DayHours:
    open: time
    close: time


@dataclass(frozen=True)
class ShopConfig:
    shop_name: str
    timezone: str
    booking_contact: str
    hours: dict[str, DayHours | None]


def load_config(path: str | Path) -> ShopConfig:
    raw = yaml.safe_load(Path(path).read_text())
    hours: dict[str, DayHours | None] = {}
    for day, val in raw["business_hours"].items():
        hours[day] = None if val is None else DayHours(
            open=time.fromisoformat(val["open"]),
            close=time.fromisoformat(val["close"]),
        )
    return ShopConfig(
        shop_name=raw["shop_name"],
        timezone=raw["timezone"],
        booking_contact=raw["booking_contact"],
        hours=hours,
    )
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add data/config.yaml barber_ops/config.py tests/test_config.py
git commit -m "feat: add shop config with business hours"
```

---

### Task 3: Booking model and event normalizer (`barber_ops.models`)

**Files:**
- Create: `barber_ops/models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces (all in `barber_ops.models`):
  - `Booking` dataclass: `event_id: str`, `service: str`, `customer: str`, `marker: str | None` (`"showed"`/`"no-show"`/`None`), `start: datetime` (aware), `end: datetime` (aware), `status: str`, `contact: dict[str, str]`; methods `to_dict() -> dict` (ISO strings for start/end) and classmethod `from_dict(d) -> Booking`.
  - `parse_summary(summary: str) -> tuple[str, str, str | None]` — `(service, customer, marker)`; raises `ValueError` on bad format.
  - `parse_contact(description: str | None) -> dict[str, str]` — extracts `email:`/`phone:` lines.
  - `normalize_events(events: list[dict], default_tz: str) -> tuple[list[Booking], list[dict]]` — second element is `rejected`: `[{"event_id": str, "reason": str}]`.

- [ ] **Step 1: Write the failing test**

`tests/test_models.py`:
```python
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from barber_ops.models import Booking, normalize_events, parse_contact, parse_summary

TZ = "America/New_York"


def _event(**overrides):
    ev = {
        "id": "evt-x",
        "summary": "Fade — Marcus J [showed]",
        "description": "phone: (555) 010-1001\nemail: marcus@example.com",
        "start": {"dateTime": "2026-07-06T10:00:00-04:00"},
        "end": {"dateTime": "2026-07-06T10:45:00-04:00"},
        "status": "confirmed",
    }
    ev.update(overrides)
    return ev


def test_parse_summary_variants():
    assert parse_summary("Fade — Marcus J [showed]") == ("Fade", "Marcus J", "showed")
    assert parse_summary("Haircut — Nick D") == ("Haircut", "Nick D", None)
    assert parse_summary("Beard Trim — Chris O [no-show]") == ("Beard Trim", "Chris O", "no-show")


def test_parse_summary_rejects_bad_format():
    with pytest.raises(ValueError):
        parse_summary("Team meeting")
    with pytest.raises(ValueError):
        parse_summary(" — Marcus J")


def test_parse_contact():
    assert parse_contact("phone: (555) 010-1001\nemail: m@example.com") == {
        "phone": "(555) 010-1001",
        "email": "m@example.com",
    }
    assert parse_contact(None) == {}


def test_normalize_happy_path_and_roundtrip():
    bookings, rejected = normalize_events([_event()], TZ)
    assert rejected == []
    b = bookings[0]
    assert (b.service, b.customer, b.marker) == ("Fade", "Marcus J", "showed")
    assert b.start == datetime(2026, 7, 6, 10, 0, tzinfo=ZoneInfo(TZ))
    assert Booking.from_dict(b.to_dict()) == b


def test_naive_datetime_gets_default_tz():
    ev = _event(start={"dateTime": "2026-07-06T10:00:00"}, end={"dateTime": "2026-07-06T10:45:00"})
    bookings, rejected = normalize_events([ev], TZ)
    assert rejected == []
    assert bookings[0].start.utcoffset() is not None


def test_all_day_and_inverted_events_rejected():
    all_day = _event(id="evt-a", start={"date": "2026-07-06"}, end={"date": "2026-07-07"})
    inverted = _event(id="evt-b", start={"dateTime": "2026-07-06T11:00:00-04:00"})
    bookings, rejected = normalize_events([all_day, inverted], TZ)
    assert bookings == []
    assert [r["event_id"] for r in rejected] == ["evt-a", "evt-b"]
    assert all(r["reason"] for r in rejected)


def test_cancelled_event_kept_with_status():
    bookings, _ = normalize_events([_event(status="cancelled")], TZ)
    assert bookings[0].status == "cancelled"
```

Run: `.venv/bin/pytest tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'barber_ops.models'`

- [ ] **Step 2: Implement `barber_ops/models.py`**

```python
"""Booking model and Google Calendar event normalization."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

MARKER_RE = re.compile(r"\[(showed|no-show)\]\s*$")
SEPARATOR = " — "


@dataclass
class Booking:
    event_id: str
    service: str
    customer: str
    marker: str | None
    start: datetime
    end: datetime
    status: str
    contact: dict[str, str]

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "service": self.service,
            "customer": self.customer,
            "marker": self.marker,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "status": self.status,
            "contact": self.contact,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Booking":
        return cls(
            event_id=d["event_id"],
            service=d["service"],
            customer=d["customer"],
            marker=d.get("marker"),
            start=datetime.fromisoformat(d["start"]),
            end=datetime.fromisoformat(d["end"]),
            status=d.get("status", "confirmed"),
            contact=d.get("contact", {}),
        )


def parse_summary(summary: str) -> tuple[str, str, str | None]:
    """'Fade — Marcus J [showed]' -> ('Fade', 'Marcus J', 'showed')."""
    marker = None
    m = MARKER_RE.search(summary)
    if m:
        marker = m.group(1)
        summary = summary[: m.start()].rstrip()
    if SEPARATOR not in summary:
        raise ValueError(f"title does not match '<Service> — <Customer>': {summary!r}")
    service, customer = summary.split(SEPARATOR, 1)
    service, customer = service.strip(), customer.strip()
    if not service or not customer:
        raise ValueError(f"empty service or customer in title: {summary!r}")
    return service, customer, marker


def parse_contact(description: str | None) -> dict[str, str]:
    contact: dict[str, str] = {}
    for line in (description or "").splitlines():
        key, _, value = line.partition(":")
        key, value = key.strip().lower(), value.strip()
        if key in ("email", "phone") and value:
            contact[key] = value
    return contact


def _parse_when(when: dict, default_tz: str) -> datetime:
    if "dateTime" not in when:
        raise ValueError("event has no dateTime (all-day events are not bookings)")
    dt = datetime.fromisoformat(when["dateTime"])
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(when.get("timeZone", default_tz)))
    return dt


def normalize_events(events: list[dict], default_tz: str) -> tuple[list[Booking], list[dict]]:
    bookings: list[Booking] = []
    rejected: list[dict] = []
    for ev in events:
        event_id = ev.get("id", "<missing id>")
        try:
            service, customer, marker = parse_summary(ev.get("summary") or "")
            start = _parse_when(ev.get("start") or {}, default_tz)
            end = _parse_when(ev.get("end") or {}, default_tz)
            if end <= start:
                raise ValueError("end is not after start")
            bookings.append(Booking(
                event_id=event_id,
                service=service,
                customer=customer,
                marker=marker,
                start=start,
                end=end,
                status=ev.get("status", "confirmed"),
                contact=parse_contact(ev.get("description")),
            ))
        except ValueError as exc:
            rejected.append({"event_id": event_id, "reason": str(exc)})
    return bookings, rejected
```

- [ ] **Step 3: Run tests**

Run: `.venv/bin/pytest tests/test_models.py -v`
Expected: 7 passed

- [ ] **Step 4: Commit**

```bash
git add barber_ops/models.py tests/test_models.py
git commit -m "feat: add Booking model and calendar event normalizer"
```

---

### Task 4: Demo fixture week

**Files:**
- Create: `data/demo/week_fixture.json`, `tests/conftest.py`
- Test: `tests/test_fixture.py`

**Interfaces:**
- Consumes: `normalize_events` from Task 3.
- Produces: the fixture file (shape `{"timeZone": str, "events": [...]}` with Google `events.list`-style items) and a pytest fixture `week_data` (the parsed JSON dict) that later test files use. Known truth used by later tasks' tests, all with `as_of = 2026-07-12T09:00:00-04:00`: 26 events, 0 rejected; confirmed no-shows in order: Alan R, Chris O, Ethan Q; candidates in order: Nick D, Jordan F, Rob T; 1 cancelled (Luis G); 3 future untagged bookings on Jul 13–14.

- [ ] **Step 1: Write `data/demo/week_fixture.json`**

```json
{
  "timeZone": "America/New_York",
  "events": [
    {"id": "evt-001", "summary": "Haircut — Devon P [showed]", "description": "phone: (555) 010-1001\nemail: devon.p@example.com", "start": {"dateTime": "2026-07-06T09:00:00-04:00"}, "end": {"dateTime": "2026-07-06T09:30:00-04:00"}, "status": "confirmed"},
    {"id": "evt-002", "summary": "Fade — Marcus J [showed]", "description": "phone: (555) 010-1002\nemail: marcus.j@example.com", "start": {"dateTime": "2026-07-06T10:00:00-04:00"}, "end": {"dateTime": "2026-07-06T10:45:00-04:00"}, "status": "confirmed"},
    {"id": "evt-003", "summary": "Haircut — Alan R [no-show]", "description": "phone: (555) 010-1003", "start": {"dateTime": "2026-07-06T13:00:00-04:00"}, "end": {"dateTime": "2026-07-06T13:30:00-04:00"}, "status": "confirmed"},
    {"id": "evt-004", "summary": "Beard Trim — Sam K [showed]", "description": "phone: (555) 010-1004", "start": {"dateTime": "2026-07-06T15:00:00-04:00"}, "end": {"dateTime": "2026-07-06T15:20:00-04:00"}, "status": "confirmed"},
    {"id": "evt-005", "summary": "Kids Cut — Tyler W [showed]", "description": "phone: (555) 010-1005", "start": {"dateTime": "2026-07-07T09:30:00-04:00"}, "end": {"dateTime": "2026-07-07T10:00:00-04:00"}, "status": "confirmed"},
    {"id": "evt-006", "summary": "Cut + Beard — Omar B [showed]", "description": "phone: (555) 010-1006\nemail: omar.b@example.com", "start": {"dateTime": "2026-07-07T11:00:00-04:00"}, "end": {"dateTime": "2026-07-07T12:00:00-04:00"}, "status": "confirmed"},
    {"id": "evt-007", "summary": "Fade — Jerome T [showed]", "description": "phone: (555) 010-1007", "start": {"dateTime": "2026-07-08T09:00:00-04:00"}, "end": {"dateTime": "2026-07-08T09:45:00-04:00"}, "status": "confirmed"},
    {"id": "evt-008", "summary": "Haircut — Nick D", "description": "email: nick.d@example.com", "start": {"dateTime": "2026-07-08T10:00:00-04:00"}, "end": {"dateTime": "2026-07-08T10:30:00-04:00"}, "status": "confirmed"},
    {"id": "evt-009", "summary": "Design — Kevin M [showed]", "description": "phone: (555) 010-1009", "start": {"dateTime": "2026-07-08T12:00:00-04:00"}, "end": {"dateTime": "2026-07-08T13:00:00-04:00"}, "status": "confirmed"},
    {"id": "evt-010", "summary": "Haircut — Luis G", "description": "phone: (555) 010-1010", "start": {"dateTime": "2026-07-08T14:00:00-04:00"}, "end": {"dateTime": "2026-07-08T14:30:00-04:00"}, "status": "cancelled"},
    {"id": "evt-011", "summary": "Fade — Andre S [showed]", "description": "phone: (555) 010-1011", "start": {"dateTime": "2026-07-08T16:00:00-04:00"}, "end": {"dateTime": "2026-07-08T16:45:00-04:00"}, "status": "confirmed"},
    {"id": "evt-012", "summary": "Haircut — Paul V [showed]", "description": "phone: (555) 010-1012", "start": {"dateTime": "2026-07-09T09:00:00-04:00"}, "end": {"dateTime": "2026-07-09T09:30:00-04:00"}, "status": "confirmed"},
    {"id": "evt-013", "summary": "Beard Trim — Chris O [no-show]", "description": "phone: (555) 010-1013\nemail: chris.o@example.com", "start": {"dateTime": "2026-07-09T11:00:00-04:00"}, "end": {"dateTime": "2026-07-09T11:20:00-04:00"}, "status": "confirmed"},
    {"id": "evt-014", "summary": "Fade — Marcus J [showed]", "description": "phone: (555) 010-1002\nemail: marcus.j@example.com", "start": {"dateTime": "2026-07-09T13:00:00-04:00"}, "end": {"dateTime": "2026-07-09T13:45:00-04:00"}, "status": "confirmed"},
    {"id": "evt-015", "summary": "Cut + Beard — Dre W [showed]", "description": "phone: (555) 010-1015", "start": {"dateTime": "2026-07-09T17:00:00-04:00"}, "end": {"dateTime": "2026-07-09T18:00:00-04:00"}, "status": "confirmed"},
    {"id": "evt-016", "summary": "Kids Cut — Mia L [showed]", "description": "phone: (555) 010-1016", "start": {"dateTime": "2026-07-10T09:00:00-04:00"}, "end": {"dateTime": "2026-07-10T09:30:00-04:00"}, "status": "confirmed"},
    {"id": "evt-017", "summary": "Haircut — Jordan F", "description": "phone: (555) 010-1017", "start": {"dateTime": "2026-07-10T10:00:00-04:00"}, "end": {"dateTime": "2026-07-10T10:30:00-04:00"}, "status": "confirmed"},
    {"id": "evt-018", "summary": "Design — Trey B [showed]", "description": "phone: (555) 010-1018", "start": {"dateTime": "2026-07-10T12:00:00-04:00"}, "end": {"dateTime": "2026-07-10T13:00:00-04:00"}, "status": "confirmed"},
    {"id": "evt-019", "summary": "Fade — Isaiah C [showed]", "description": "phone: (555) 010-1019", "start": {"dateTime": "2026-07-10T15:00:00-04:00"}, "end": {"dateTime": "2026-07-10T15:45:00-04:00"}, "status": "confirmed"},
    {"id": "evt-020", "summary": "Fade — Malik H [showed]", "description": "phone: (555) 010-1020", "start": {"dateTime": "2026-07-11T08:00:00-04:00"}, "end": {"dateTime": "2026-07-11T08:45:00-04:00"}, "status": "confirmed"},
    {"id": "evt-021", "summary": "Haircut — Ethan Q [no-show]", "description": "phone: (555) 010-1021", "start": {"dateTime": "2026-07-11T09:00:00-04:00"}, "end": {"dateTime": "2026-07-11T09:30:00-04:00"}, "status": "confirmed"},
    {"id": "evt-022", "summary": "Cut + Beard — Victor N [showed]", "description": "phone: (555) 010-1022", "start": {"dateTime": "2026-07-11T11:00:00-04:00"}, "end": {"dateTime": "2026-07-11T12:00:00-04:00"}, "status": "confirmed"},
    {"id": "evt-023", "summary": "Haircut — Rob T", "description": "phone: (555) 010-1023\nemail: rob.t@example.com", "start": {"dateTime": "2026-07-11T13:00:00-04:00"}, "end": {"dateTime": "2026-07-11T13:30:00-04:00"}, "status": "confirmed"},
    {"id": "evt-024", "summary": "Fade — Marcus J", "description": "phone: (555) 010-1002\nemail: marcus.j@example.com", "start": {"dateTime": "2026-07-13T10:00:00-04:00"}, "end": {"dateTime": "2026-07-13T10:45:00-04:00"}, "status": "confirmed"},
    {"id": "evt-025", "summary": "Haircut — Devon P", "description": "phone: (555) 010-1001\nemail: devon.p@example.com", "start": {"dateTime": "2026-07-13T14:00:00-04:00"}, "end": {"dateTime": "2026-07-13T14:30:00-04:00"}, "status": "confirmed"},
    {"id": "evt-026", "summary": "Beard Trim — Sam K", "description": "phone: (555) 010-1004", "start": {"dateTime": "2026-07-14T09:00:00-04:00"}, "end": {"dateTime": "2026-07-14T09:20:00-04:00"}, "status": "confirmed"}
  ]
}
```

Story built into the data: Tue Jul 7 afternoon is empty (the gap pattern for weekly-summary later); 3 tagged no-shows spread across the week; 3 untagged past events (candidates); 1 cancelled; 3 upcoming bookings Mon–Tue so slot proposals have real conflicts and no-show detection must ignore future events.

- [ ] **Step 2: Write `tests/conftest.py` and the failing validation test**

`tests/conftest.py`:
```python
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def week_data():
    return json.loads((ROOT / "data" / "demo" / "week_fixture.json").read_text())
```

`tests/test_fixture.py`:
```python
from barber_ops.models import normalize_events


def test_fixture_is_fully_normalizable(week_data):
    bookings, rejected = normalize_events(week_data["events"], week_data["timeZone"])
    assert rejected == []
    assert len(bookings) == 26
    assert sum(1 for b in bookings if b.marker == "no-show") == 3
    assert sum(1 for b in bookings if b.marker == "showed") == 16
    assert sum(1 for b in bookings if b.status == "cancelled") == 1
```

Run: `.venv/bin/pytest tests/test_fixture.py -v`
Expected: PASS immediately if fixture and Step 1 are correct (this test validates data, not new code; a failure means the fixture has a typo — fix the fixture).

- [ ] **Step 3: Commit**

```bash
git add data/demo/week_fixture.json tests/conftest.py tests/test_fixture.py
git commit -m "feat: add Sharp Cuts demo week fixture"
```

---

### Task 5: Slot math (`barber_ops.slots`)

**Files:**
- Create: `barber_ops/slots.py`
- Test: `tests/test_slots.py`

**Interfaces:**
- Consumes: `Booking` (Task 3), `ShopConfig`/`DayHours` (Task 2), `week_data` fixture (Task 4).
- Produces (in `barber_ops.slots`): `free_windows(bookings: list[Booking], cfg: ShopConfig, day: datetime.date, min_minutes: int) -> list[tuple[datetime, datetime]]` and `windows_for_range(bookings, cfg, first_day: date, last_day: date, min_minutes: int) -> list[tuple[datetime, datetime]]`. Windows are within business hours, exclude non-cancelled bookings, and are at least `min_minutes` long. (Note: this module is a small addition beyond the spec's three named lib modules — it exists so phase 2's gap analysis reuses the same math.)

- [ ] **Step 1: Write the failing test**

`tests/test_slots.py`:
```python
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from barber_ops.config import load_config
from barber_ops.models import normalize_events
from barber_ops.slots import free_windows, windows_for_range

ROOT = Path(__file__).resolve().parents[1]
TZ = ZoneInfo("America/New_York")


def _bookings(week_data):
    bookings, rejected = normalize_events(week_data["events"], week_data["timeZone"])
    assert rejected == []
    return bookings


def _cfg():
    return load_config(ROOT / "data" / "config.yaml")


def test_free_windows_monday_fade(week_data):
    # Mon Jul 13: busy 10:00-10:45 and 14:00-14:30, hours 09:00-18:00.
    windows = free_windows(_bookings(week_data), _cfg(), date(2026, 7, 13), 45)
    assert windows == [
        (datetime(2026, 7, 13, 9, 0, tzinfo=TZ), datetime(2026, 7, 13, 10, 0, tzinfo=TZ)),
        (datetime(2026, 7, 13, 10, 45, tzinfo=TZ), datetime(2026, 7, 13, 14, 0, tzinfo=TZ)),
        (datetime(2026, 7, 13, 14, 30, tzinfo=TZ), datetime(2026, 7, 13, 18, 0, tzinfo=TZ)),
    ]


def test_window_too_short_for_service_excluded(week_data):
    # Design needs 60 min; the 09:00-10:00 window no longer qualifies.
    windows = free_windows(_bookings(week_data), _cfg(), date(2026, 7, 13), 60)
    assert windows[0][0] == datetime(2026, 7, 13, 10, 45, tzinfo=TZ)
    assert len(windows) == 2


def test_closed_day_has_no_windows(week_data):
    assert free_windows(_bookings(week_data), _cfg(), date(2026, 7, 12), 30) == []


def test_cancelled_bookings_do_not_block(week_data):
    # Wed Jul 8: Luis G 14:00-14:30 is cancelled, so 13:00-16:00 is one free window.
    windows = free_windows(_bookings(week_data), _cfg(), date(2026, 7, 8), 30)
    assert (datetime(2026, 7, 8, 13, 0, tzinfo=TZ), datetime(2026, 7, 8, 16, 0, tzinfo=TZ)) in windows


def test_windows_for_range(week_data):
    windows = windows_for_range(_bookings(week_data), _cfg(), date(2026, 7, 13), date(2026, 7, 14), 45)
    assert len(windows) == 4  # 3 on Mon + 1 on Tue (09:20-18:00)
    assert windows[-1][0] == datetime(2026, 7, 14, 9, 20, tzinfo=TZ)
```

Run: `.venv/bin/pytest tests/test_slots.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'barber_ops.slots'`

- [ ] **Step 2: Implement `barber_ops/slots.py`**

```python
"""Free-window math over bookings and business hours."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .config import ShopConfig
from .models import Booking

WEEKDAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def free_windows(
    bookings: list[Booking], cfg: ShopConfig, day: date, min_minutes: int
) -> list[tuple[datetime, datetime]]:
    hours = cfg.hours.get(WEEKDAY_KEYS[day.weekday()])
    if hours is None:
        return []
    tz = ZoneInfo(cfg.timezone)
    day_start = datetime.combine(day, hours.open, tzinfo=tz)
    day_end = datetime.combine(day, hours.close, tzinfo=tz)
    busy = sorted(
        (max(b.start, day_start), min(b.end, day_end))
        for b in bookings
        if b.status != "cancelled" and b.start < day_end and b.end > day_start
    )
    windows: list[tuple[datetime, datetime]] = []
    cursor = day_start
    for start, end in busy:
        if start > cursor:
            windows.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < day_end:
        windows.append((cursor, day_end))
    need = timedelta(minutes=min_minutes)
    return [(s, e) for s, e in windows if e - s >= need]


def windows_for_range(
    bookings: list[Booking], cfg: ShopConfig, first_day: date, last_day: date, min_minutes: int
) -> list[tuple[datetime, datetime]]:
    out: list[tuple[datetime, datetime]] = []
    day = first_day
    while day <= last_day:
        out.extend(free_windows(bookings, cfg, day, min_minutes))
        day += timedelta(days=1)
    return out
```

- [ ] **Step 3: Run tests**

Run: `.venv/bin/pytest tests/test_slots.py -v`
Expected: 5 passed

- [ ] **Step 4: Commit**

```bash
git add barber_ops/slots.py tests/test_slots.py
git commit -m "feat: add free-window slot math"
```

---

### Task 6: Draft rendering (`barber_ops.drafting`)

**Files:**
- Create: `barber_ops/drafting.py`
- Test: `tests/test_drafting.py`

**Interfaces:**
- Consumes: `Booking` (Task 3), `ShopConfig` (Task 2).
- Produces (in `barber_ops.drafting`):
  - `Draft` dataclass: `channel: str` (`"sms"`/`"email"`), `to: str`, `subject: str | None` (always `None` for sms), `body: str`; method `to_dict() -> dict`.
  - `format_slot(dt: datetime) -> str` — e.g. `"Tue Jul 14 at 2:00 PM"` (portable, no `%-d`).
  - `render_rebook_draft(booking: Booking, cfg: ShopConfig, channel: str) -> Draft` — raises `ValueError` if the booking has no contact for that channel or channel is unknown.
  - `render_reschedule_confirmation(booking: Booking, new_start: datetime, cfg: ShopConfig, channel: str) -> Draft` — same error contract.

- [ ] **Step 1: Write the failing test**

`tests/test_drafting.py`:
```python
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from barber_ops.config import load_config
from barber_ops.drafting import format_slot, render_rebook_draft, render_reschedule_confirmation
from barber_ops.models import Booking

ROOT = Path(__file__).resolve().parents[1]
TZ = ZoneInfo("America/New_York")


def _booking(contact):
    return Booking(
        event_id="evt-003", service="Haircut", customer="Alan R", marker="no-show",
        start=datetime(2026, 7, 6, 13, 0, tzinfo=TZ), end=datetime(2026, 7, 6, 13, 30, tzinfo=TZ),
        status="confirmed", contact=contact,
    )


def _cfg():
    return load_config(ROOT / "data" / "config.yaml")


def test_format_slot():
    assert format_slot(datetime(2026, 7, 14, 14, 0, tzinfo=TZ)) == "Tue Jul 14 at 2:00 PM"
    assert format_slot(datetime(2026, 7, 6, 9, 30, tzinfo=TZ)) == "Mon Jul 6 at 9:30 AM"


def test_rebook_sms():
    draft = render_rebook_draft(_booking({"phone": "(555) 010-1003"}), _cfg(), "sms")
    assert draft.channel == "sms"
    assert draft.to == "(555) 010-1003"
    assert draft.subject is None
    assert "Alan" in draft.body
    assert "Haircut" in draft.body
    assert "Sharp Cuts Barbershop" in draft.body
    assert "Mon Jul 6" in draft.body


def test_rebook_email_has_subject():
    draft = render_rebook_draft(_booking({"email": "alan@example.com"}), _cfg(), "email")
    assert draft.channel == "email"
    assert draft.to == "alan@example.com"
    assert draft.subject == "Let's get you rescheduled at Sharp Cuts Barbershop"


def test_missing_contact_raises():
    with pytest.raises(ValueError, match="no email on file"):
        render_rebook_draft(_booking({"phone": "(555) 010-1003"}), _cfg(), "email")


def test_reschedule_confirmation():
    new_start = datetime(2026, 7, 14, 10, 0, tzinfo=TZ)
    draft = render_reschedule_confirmation(_booking({"phone": "(555) 010-1003"}), new_start, _cfg(), "sms")
    assert "Tue Jul 14 at 10:00 AM" in draft.body
    assert "confirmed" in draft.body.lower()
```

Run: `.venv/bin/pytest tests/test_drafting.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'barber_ops.drafting'`

- [ ] **Step 2: Implement `barber_ops/drafting.py`**

```python
"""Channel-neutral draft rendering. This module has NO send capability by design."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .config import ShopConfig
from .models import Booking

CHANNELS = ("sms", "email")


@dataclass
class Draft:
    channel: str
    to: str
    subject: str | None
    body: str

    def to_dict(self) -> dict:
        return {"channel": self.channel, "to": self.to, "subject": self.subject, "body": self.body}


def format_slot(dt: datetime) -> str:
    clock = dt.strftime("%I:%M %p").lstrip("0")
    return f"{dt.strftime('%a %b')} {dt.day} at {clock}"


def _to_for(booking: Booking, channel: str) -> str:
    if channel not in CHANNELS:
        raise ValueError(f"unknown channel {channel!r}")
    key = "phone" if channel == "sms" else "email"
    to = booking.contact.get(key)
    if not to:
        raise ValueError(f"no {key} on file for {booking.customer}")
    return to


def render_rebook_draft(booking: Booking, cfg: ShopConfig, channel: str) -> Draft:
    to = _to_for(booking, channel)
    first = booking.customer.split()[0]
    when = format_slot(booking.start)
    if channel == "sms":
        body = (
            f"Hi {first}, this is {cfg.shop_name}. We missed you for your "
            f"{booking.service} on {when}. Want to get back on the books? "
            f"Reply here or call {cfg.booking_contact}."
        )
        return Draft("sms", to, None, body)
    body = (
        f"Hi {first},\n\n"
        f"We missed you for your {booking.service} on {when}. No worries - it happens! "
        f"Reply to this email or call {cfg.booking_contact} and we'll find you a new time.\n\n"
        f"{cfg.shop_name}"
    )
    return Draft("email", to, f"Let's get you rescheduled at {cfg.shop_name}", body)


def render_reschedule_confirmation(
    booking: Booking, new_start: datetime, cfg: ShopConfig, channel: str
) -> Draft:
    to = _to_for(booking, channel)
    first = booking.customer.split()[0]
    when = format_slot(new_start)
    body = (
        f"Hi {first}, you're confirmed for your {booking.service} on {when} "
        f"at {cfg.shop_name}. See you then!"
    )
    if channel == "sms":
        return Draft("sms", to, None, body)
    return Draft("email", to, f"Confirmed: {booking.service} on {when}", body)
```

- [ ] **Step 3: Run tests**

Run: `.venv/bin/pytest tests/test_drafting.py -v`
Expected: 5 passed

- [ ] **Step 4: Commit**

```bash
git add barber_ops/drafting.py tests/test_drafting.py
git commit -m "feat: add channel-neutral draft rendering"
```

---

### Task 7: `detect_no_shows.py` script

**Files:**
- Create: `skills/appointment-management/scripts/detect_no_shows.py`
- Test: `tests/test_detect_no_shows.py`

**Interfaces:**
- Consumes: `normalize_events` (Task 3), `load_config` (Task 2), fixture truth (Task 4).
- Produces: CLI `detect_no_shows.py [events.json] --as-of ISO [--config PATH]` (events from file arg or stdin; input shape `{"timeZone": ..., "events": [...]}` or a bare event list). Stdout JSON: `{"as_of": str, "confirmed": [booking dicts], "candidates": [booking dicts], "rejected": [{"event_id","reason"}]}`. Exit 2 with stderr message on invalid/naive `--as-of`. Task 9 consumes the booking dicts verbatim.

- [ ] **Step 1: Write the failing test**

`tests/test_detect_no_shows.py`:
```python
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "appointment-management" / "scripts" / "detect_no_shows.py"
FIXTURE = ROOT / "data" / "demo" / "week_fixture.json"
AS_OF = "2026-07-12T09:00:00-04:00"


def run(*argv, stdin=None):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *argv], capture_output=True, text=True, input=stdin
    )


def test_classifies_fixture_week():
    r = run(str(FIXTURE), "--as-of", AS_OF)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert [b["customer"] for b in out["confirmed"]] == ["Alan R", "Chris O", "Ethan Q"]
    assert [b["customer"] for b in out["candidates"]] == ["Nick D", "Jordan F", "Rob T"]
    assert out["rejected"] == []


def test_reads_stdin():
    r = run("--as-of", AS_OF, stdin=FIXTURE.read_text())
    assert r.returncode == 0, r.stderr
    assert len(json.loads(r.stdout)["confirmed"]) == 3


def test_malformed_event_reported_not_dropped():
    payload = {
        "timeZone": "America/New_York",
        "events": [{"id": "evt-bad", "summary": "Staff meeting", "start": {"dateTime": "2026-07-06T09:00:00-04:00"}, "end": {"dateTime": "2026-07-06T10:00:00-04:00"}, "status": "confirmed"}],
    }
    r = run("--as-of", AS_OF, stdin=json.dumps(payload))
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["rejected"][0]["event_id"] == "evt-bad"


def test_naive_as_of_rejected():
    r = run(str(FIXTURE), "--as-of", "2026-07-12T09:00:00")
    assert r.returncode == 2
    assert "UTC offset" in r.stderr
```

Run: `.venv/bin/pytest tests/test_detect_no_shows.py -v`
Expected: FAIL — script file does not exist (`FileNotFoundError` from subprocess or non-zero returncode)

- [ ] **Step 2: Implement `skills/appointment-management/scripts/detect_no_shows.py`**

```python
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
```

- [ ] **Step 3: Run tests**

Run: `.venv/bin/pytest tests/test_detect_no_shows.py -v`
Expected: 4 passed

- [ ] **Step 4: Commit**

```bash
git add skills/appointment-management/scripts/detect_no_shows.py tests/test_detect_no_shows.py
git commit -m "feat: add detect_no_shows skill script"
```

---

### Task 8: `propose_slots.py` script

**Files:**
- Create: `skills/appointment-management/scripts/propose_slots.py`
- Test: `tests/test_propose_slots.py`

**Interfaces:**
- Consumes: `normalize_events` (Task 3), `load_config` (Task 2), `load_services`/`get_service` (Task 1), `windows_for_range` (Task 5).
- Produces: CLI `propose_slots.py [events.json] --service NAME --from YYYY-MM-DD --to YYYY-MM-DD [--config PATH] [--services PATH]`. Stdout JSON: `{"service": str, "duration_min": int, "windows": [{"start": iso, "end": iso}], "rejected": [...]}`. Exit 2 on unknown service (stderr lists menu) or invalid date range.

- [ ] **Step 1: Write the failing test**

`tests/test_propose_slots.py`:
```python
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "appointment-management" / "scripts" / "propose_slots.py"
FIXTURE = ROOT / "data" / "demo" / "week_fixture.json"


def run(*argv):
    return subprocess.run([sys.executable, str(SCRIPT), *argv], capture_output=True, text=True)


def test_fade_windows_next_two_days():
    r = run(str(FIXTURE), "--service", "Fade", "--from", "2026-07-13", "--to", "2026-07-14")
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["service"] == "Fade"
    assert out["duration_min"] == 45
    assert len(out["windows"]) == 4
    assert out["windows"][0] == {"start": "2026-07-13T09:00:00-04:00", "end": "2026-07-13T10:00:00-04:00"}
    assert out["windows"][3]["start"] == "2026-07-14T09:20:00-04:00"


def test_unknown_service_exits_2_with_menu():
    r = run(str(FIXTURE), "--service", "Perm", "--from", "2026-07-13", "--to", "2026-07-13")
    assert r.returncode == 2
    assert "known services" in r.stderr


def test_inverted_range_exits_2():
    r = run(str(FIXTURE), "--service", "Fade", "--from", "2026-07-14", "--to", "2026-07-13")
    assert r.returncode == 2
    assert "range" in r.stderr
```

Run: `.venv/bin/pytest tests/test_propose_slots.py -v`
Expected: FAIL — script file does not exist

- [ ] **Step 2: Implement `skills/appointment-management/scripts/propose_slots.py`**

```python
#!/usr/bin/env python3
"""Propose free booking windows for a service over a date range.

Input (file arg or stdin): {"timeZone": str, "events": [...]} in Google
events.list shape, or a bare event list.
Output (stdout): {"service", "duration_min", "windows": [{"start","end"}], "rejected"}.

Windows fall inside business hours (data/config.yaml), exclude non-cancelled
bookings, and are at least the service's duration long. This script never
contacts any external service.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from barber_ops.config import load_config  # noqa: E402
from barber_ops.models import normalize_events  # noqa: E402
from barber_ops.services import get_service, load_services  # noqa: E402
from barber_ops.slots import windows_for_range  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("events_file", nargs="?", help="events JSON file (default: stdin)")
    parser.add_argument("--service", required=True)
    parser.add_argument("--from", dest="from_day", required=True, help="YYYY-MM-DD")
    parser.add_argument("--to", dest="to_day", required=True, help="YYYY-MM-DD")
    parser.add_argument("--config", default=str(REPO_ROOT / "data" / "config.yaml"))
    parser.add_argument("--services", default=str(REPO_ROOT / "data" / "services.yaml"))
    args = parser.parse_args()

    cfg = load_config(args.config)
    try:
        service = get_service(load_services(args.services), args.service)
    except KeyError as exc:
        print(f"error: {exc.args[0]}", file=sys.stderr)
        return 2

    try:
        first, last = date.fromisoformat(args.from_day), date.fromisoformat(args.to_day)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if last < first:
        print(f"error: invalid range {args.from_day}..{args.to_day}", file=sys.stderr)
        return 2

    raw = json.loads(Path(args.events_file).read_text()) if args.events_file else json.load(sys.stdin)
    events = raw["events"] if isinstance(raw, dict) else raw
    default_tz = (raw.get("timeZone") if isinstance(raw, dict) else None) or cfg.timezone

    bookings, rejected = normalize_events(events, default_tz)
    windows = windows_for_range(bookings, cfg, first, last, service.duration_min)

    json.dump(
        {
            "service": service.name,
            "duration_min": service.duration_min,
            "windows": [{"start": s.isoformat(), "end": e.isoformat()} for s, e in windows],
            "rejected": rejected,
        },
        sys.stdout, indent=2,
    )
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Run tests**

Run: `.venv/bin/pytest tests/test_propose_slots.py -v`
Expected: 3 passed

- [ ] **Step 4: Commit**

```bash
git add skills/appointment-management/scripts/propose_slots.py tests/test_propose_slots.py
git commit -m "feat: add propose_slots skill script"
```

---

### Task 9: `draft_followup.py` script

**Files:**
- Create: `skills/appointment-management/scripts/draft_followup.py`
- Test: `tests/test_draft_followup.py`

**Interfaces:**
- Consumes: `Booking.from_dict` (Task 3), `load_config` (Task 2), `render_rebook_draft`/`render_reschedule_confirmation` (Task 6). Booking dicts come verbatim from Task 7's output.
- Produces: CLI `draft_followup.py [payload.json] [--config PATH]`. Payload: `{"mode": "rebook", "channel_preference": "sms"|"email", "bookings": [...]}` or `{"mode": "reschedule", "channel_preference": ..., "booking": {...}, "new_start": iso}`. Stdout JSON: `{"drafts": [draft dicts], "skipped": [{"event_id","reason"}]}`. Channel fallback: preferred channel first, then the other; if neither has contact info the booking is skipped with a reason. Exit 2 on bad mode/channel.

- [ ] **Step 1: Write the failing test**

`tests/test_draft_followup.py`:
```python
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "appointment-management" / "scripts" / "draft_followup.py"

ALAN = {
    "event_id": "evt-003", "service": "Haircut", "customer": "Alan R", "marker": "no-show",
    "start": "2026-07-06T13:00:00-04:00", "end": "2026-07-06T13:30:00-04:00",
    "status": "confirmed", "contact": {"phone": "(555) 010-1003"},
}
NO_CONTACT = dict(ALAN, event_id="evt-x", customer="Ghost B", contact={})


def run(payload):
    return subprocess.run(
        [sys.executable, str(SCRIPT)], capture_output=True, text=True, input=json.dumps(payload)
    )


def test_rebook_drafts_sms():
    r = run({"mode": "rebook", "channel_preference": "sms", "bookings": [ALAN]})
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["skipped"] == []
    assert out["drafts"][0]["channel"] == "sms"
    assert out["drafts"][0]["to"] == "(555) 010-1003"
    assert "Alan" in out["drafts"][0]["body"]


def test_falls_back_to_other_channel():
    r = run({"mode": "rebook", "channel_preference": "email", "bookings": [ALAN]})
    out = json.loads(r.stdout)
    assert out["drafts"][0]["channel"] == "sms"  # no email on file, falls back


def test_no_contact_is_skipped_with_reason():
    r = run({"mode": "rebook", "channel_preference": "sms", "bookings": [ALAN, NO_CONTACT]})
    out = json.loads(r.stdout)
    assert len(out["drafts"]) == 1
    assert out["skipped"] == [{"event_id": "evt-x", "reason": "no contact info for Ghost B"}]


def test_reschedule_confirmation():
    r = run({
        "mode": "reschedule", "channel_preference": "sms",
        "booking": ALAN, "new_start": "2026-07-14T10:00:00-04:00",
    })
    out = json.loads(r.stdout)
    assert "Tue Jul 14 at 10:00 AM" in out["drafts"][0]["body"]


def test_bad_mode_exits_2():
    r = run({"mode": "send-everything", "bookings": []})
    assert r.returncode == 2
    assert "mode" in r.stderr
```

Run: `.venv/bin/pytest tests/test_draft_followup.py -v`
Expected: FAIL — script file does not exist

- [ ] **Step 2: Implement `skills/appointment-management/scripts/draft_followup.py`**

```python
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
from barber_ops.drafting import render_rebook_draft, render_reschedule_confirmation  # noqa: E402
from barber_ops.models import Booking  # noqa: E402


def _try_channels(render, preferred: str):
    for channel in (preferred, "email" if preferred == "sms" else "sms"):
        try:
            return render(channel)
        except ValueError:
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
        b = Booking.from_dict(payload["booking"])
        new_start = datetime.fromisoformat(payload["new_start"])
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
```

- [ ] **Step 3: Run tests**

Run: `.venv/bin/pytest tests/test_draft_followup.py -v`
Expected: 5 passed

- [ ] **Step 4: Commit**

```bash
git add skills/appointment-management/scripts/draft_followup.py tests/test_draft_followup.py
git commit -m "feat: add draft_followup skill script"
```

---

### Task 10: SKILL.md, README runbook, manual verification

**Files:**
- Create: `skills/appointment-management/SKILL.md`
- Modify: `README.md` (replace the one-line stub)

**Interfaces:**
- Consumes: the three script CLIs exactly as specified in Tasks 7–9.
- Produces: the complete phase-1 deliverable, ready for owner review.

- [ ] **Step 1: Write `skills/appointment-management/SKILL.md`**

```markdown
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
```

- [ ] **Step 2: Write `README.md`**

```markdown
# Barber Ops

Starter-tier demo package for a fractional AI ops service: Claude Cowork
skills for a barber shop, built on the Gmail and Google Calendar connectors.

- `skills/appointment-management/` — no-show detection, reschedules, and
  draft-only follow-up messages. See its `SKILL.md`.
- `skills/weekly-summary/` — (phase 2) weekly owner report.
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

In Cowork, the `appointment-management` skill drives these same scripts with
events fetched live from the Google Calendar connector; email follow-ups are
created as Gmail drafts and are never sent.

## Live demo (optional, phase 2)

`tools/seed_calendar.py` (phase 2) pushes the fixture into a real Google
Calendar so the same workflows run against live connector data.
```

- [ ] **Step 3: Run the full test suite**

Run: `.venv/bin/pytest -v`
Expected: all tests pass (34 across 9 files)

- [ ] **Step 4: Manual verification — run the runbook**

Run the three runbook commands above from the repo root with the system
`python3` (NOT the venv — proves the scripts work uninstalled, as in Cowork):
```bash
python3 skills/appointment-management/scripts/detect_no_shows.py data/demo/week_fixture.json --as-of 2026-07-12T09:00:00-04:00
python3 skills/appointment-management/scripts/propose_slots.py data/demo/week_fixture.json --service Fade --from 2026-07-13 --to 2026-07-14
python3 skills/appointment-management/scripts/detect_no_shows.py data/demo/week_fixture.json --as-of 2026-07-12T09:00:00-04:00 | python3 -c "import json,sys; d=json.load(sys.stdin); print(json.dumps({'mode':'rebook','channel_preference':'sms','bookings':d['confirmed']}))" | python3 skills/appointment-management/scripts/draft_followup.py
```
Expected: no tracebacks; outputs match the runbook's stated expectations
(3 confirmed / 3 candidates; 4 windows; 3 sms drafts, 0 skipped). Note:
`pyyaml` must be importable by system `python3` — if it is not, install it
(`python3 -m pip install --user pyyaml`) and note this as a skill
requirement in SKILL.md.

- [ ] **Step 5: Commit**

```bash
git add skills/appointment-management/SKILL.md README.md
git commit -m "feat: add appointment-management SKILL.md and demo runbook"
```

**Phase 1 ends here — owner review checkpoint before starting weekly-summary.**
