"""Channel-neutral draft rendering. This module has NO send capability by design."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .config import ShopConfig
from .models import Booking

CHANNELS = ("sms", "email")


class MissingContact(ValueError):
    """Raised when a booking has no contact info for the requested channel."""


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
        raise MissingContact(f"no {key} on file for {booking.customer}")
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
