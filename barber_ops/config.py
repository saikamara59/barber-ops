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
