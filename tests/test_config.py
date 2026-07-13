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
