from __future__ import annotations

import hashlib
from pathlib import Path

import pytest


@pytest.fixture
def pinned_test_thaliris(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Supply a fake exact executable identity for Host installer unit tests."""
    from thaliris import codex_adapter, codex_app_server, lifecycle

    executable = tmp_path / "test-host-executable.exe"
    executable.write_bytes(b"test-only direct Thaliris executable identity")
    digest = hashlib.sha256(executable.read_bytes()).hexdigest()
    monkeypatch.setattr(
        codex_adapter,
        "_host_install_executable",
        lambda _home, _path, _sha: (executable, digest, None),
    )

    trusted_homes: set[Path] = set()

    def trust_host_hooks(home: Path, _exe: Path, _sha: str):
        resolved_home = home.resolve()
        changed = resolved_home not in trusted_homes
        trusted_homes.add(resolved_home)
        expected = len(lifecycle.HOOK_EVENTS)
        return {
            "status": "TRUSTED",
            "trusted_count": expected,
            "enabled_count": expected,
            "expected_count": expected,
            "changed": changed,
            "config_path": str(home / "config.toml") if changed else None,
            "keys": [f"host-key:{event}" for event in lifecycle.HOOK_EVENTS],
        }

    monkeypatch.setattr(codex_adapter, "_install_host_hook_trust", trust_host_hooks)
    monkeypatch.setattr(
        codex_app_server,
        "owned_hook_keys_from_host",
        lambda _home, commands: [
            f"host-key:{event}:{index}"
            for event, handlers in commands.items()
            for index, _command in enumerate(sorted(handlers))
        ],
    )
    monkeypatch.setattr(codex_app_server, "remove_owned_hook_trust", lambda _home, keys: len(keys))
    return executable, digest
