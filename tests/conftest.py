"""Core and optional benchmark regression fixtures are local to their suites."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolated_thaliris_home(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test uses a private THALIRIS_HOME; no test reads or writes the real ~/.thaliris."""
    monkeypatch.setenv("THALIRIS_HOME", str(tmp_path_factory.mktemp("thaliris-home") / "home"))
