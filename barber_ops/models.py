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
    dt = datetime.fromisoformat(when["dateTime"].replace("Z", "+00:00"))
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
