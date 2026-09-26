from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "real-sessions"


def pytest_collection_modifyitems(config, items):  # noqa: ANN001, ARG001
    live = pytest.mark.live
    for item in items:
        if "live" in item.keywords:
            item.add_marker(live)


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    # grows in T5
    if not FIXTURES.exists():
        pytest.skip("fixture corpus missing - run `uv run python -m vctrl record` (A5)")
    return FIXTURES
