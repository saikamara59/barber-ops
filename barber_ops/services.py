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
