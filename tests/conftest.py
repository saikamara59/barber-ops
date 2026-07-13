import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def week_data():
    return json.loads((ROOT / "data" / "demo" / "week_fixture.json").read_text())
