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
