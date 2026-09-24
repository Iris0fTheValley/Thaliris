from __future__ import annotations

import hashlib
from pathlib import Path

import pytest


@pytest.fixture
def pinned_test_thaliris(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Supply a fake exact executable identity for Host installer unit tests."""
    from thaliris import codex_adapter

    executable = tmp_path / "test-host-executable.exe"
    executable.write_bytes(b"test-only direct Thaliris executable identity")
    digest = hashlib.sha256(executable.read_bytes()).hexdigest()
    monkeypatch.setattr(
        codex_adapter,
        "_host_install_executable",
        lambda _home, _path, _sha: (executable, digest, None),
    )
    return executable, digest
