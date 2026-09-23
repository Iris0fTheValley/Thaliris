from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

from thaliris import cli, codex_adapter, core, lifecycle, roles


def _sentinel_definition() -> roles.RoleDefinition:
    return roles.RoleDefinition(
        id="sentinel",
        default_model="gpt-5.6-luna",
        reasoning_effort="high",
        native_profile="thaliris-sentinel",
        instructions="sentinel instructions",
        repo_write_allowed=True,
        delegation_allowed=False,
        controller_control_state_modification_allowed=False,
        generated_profile=True,
        profile_filename="thaliris-sentinel.toml",
    )


def test_registry_is_authoritative_for_native_profiles_and_mechanical_facts() -> None:
    native = roles.native_role_definitions()
    assert [definition.id for definition in native] == [
        "investigator", "curator", "reasoning-specialist", "implementer", "verifier", "reviewer",
    ]
    for definition in native:
        assert definition.native_profile == f"thaliris-{definition.id}"
        assert definition.profile_filename == f"thaliris-{definition.id}.toml"
        assert definition.instructions
        assert definition.reasoning_effort
        assert definition.legacy_profile_hashes
    assert roles.native_agent_roles() == {
        definition.native_profile: definition.id for definition in native
    }
    assert roles.agent_profiles() == {
        definition.profile_filename: (
            definition.default_model, definition.reasoning_effort, definition.id
        )
        for definition in native
    }
    assert roles.notice_roles() == {"curator", "reasoning-specialist", "verifier", "reviewer"}


def test_new_registry_role_flows_through_adapter_inventories_and_cli(monkeypatch) -> None:
    monkeypatch.setitem(roles.ROLE_REGISTRY, "sentinel", _sentinel_definition())

    assert "sentinel" in codex_adapter.role_choices()
    assert roles.agent_profiles()["thaliris-sentinel.toml"] == (
        "gpt-5.6-luna", "high", "sentinel"
    )
    assert lifecycle._native_agent_roles()["thaliris-sentinel"] == "sentinel"
    assert "thaliris-sentinel" in roles.native_profile_names()
    assert "| `sentinel` | `gpt-5.6-luna` | `high` | `thaliris-sentinel` |" in roles.render_registry_document().decode()

    parser = cli._parser()
    choices = parser._subparsers._group_actions[0].choices["task-update"]._actions
    role_action = next(action for action in choices if action.dest == "role")
    assert "sentinel" in role_action.choices


def test_new_registry_role_appears_in_active_spawn_isolation_diagnostic(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setitem(roles.ROLE_REGISTRY, "sentinel", _sentinel_definition())
    root = _initialized_repo(tmp_path)
    core.task_start(root, "registry diagnostic", None, None)

    denied = lifecycle._pre_tool_output(root=root, payload={
        "tool_name": "spawn_agent",
        "tool_input": {"fork_turns": "all"},
    })

    reason = json.loads(denied)["hookSpecificOutput"]["permissionDecisionReason"]
    assert reason.startswith("THALIRIS_ISOLATION_REQUIRED:")
    assert reason.endswith('and Sentinel session explicitly with fork_turns="none".')


def _initialized_repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    codex_adapter.init(tmp_path)
    return tmp_path


def _historical_registry_document() -> bytes:
    # Fixed LF/UTF-8 bytes captured from immutable commit b1d517f (blob
    # 9c410a4d2af5d3780f4b415429227150d08626bd), not regenerated at test time.
    value = (Path(__file__).parent / "fixtures" / "thaliris-role-registry-v1.md").read_bytes()
    assert hashlib.sha256(value).hexdigest() in codex_adapter._KNOWN_GENERATED_ROLE_REGISTRY_DOC_HASHES
    return value


def _simulate_registry_addition(monkeypatch) -> None:
    monkeypatch.setitem(roles.ROLE_REGISTRY, "sentinel", _sentinel_definition())
    # A new adapter process would capture the expanded current rendering at
    # import time; model that boundary so the historical six-role bytes cannot
    # be accepted merely because they match the old module constant.
    monkeypatch.setattr(codex_adapter, "ROLE_REGISTRY_DOC", roles.render_registry_document().decode())


def test_historical_registry_document_migrates_after_registry_addition(tmp_path: Path, monkeypatch) -> None:
    root = _initialized_repo(tmp_path)
    registry_document = root / "docs" / "thaliris-role-registry.md"
    registry_document.write_bytes(_historical_registry_document())
    _simulate_registry_addition(monkeypatch)

    assert codex_adapter._role_registry_state(registry_document.read_bytes()) == "legacy"
    result = codex_adapter.init(root)

    assert registry_document.read_bytes() == roles.render_registry_document()
    assert "docs/thaliris-role-registry.md" in result["files"]
    assert "docs/thaliris-role-registry.md" not in result["manual_action_required"]


def test_modified_registry_document_is_preserved_as_user_owned(tmp_path: Path, monkeypatch) -> None:
    root = _initialized_repo(tmp_path)
    registry_document = root / "docs" / "thaliris-role-registry.md"
    user_owned = _historical_registry_document() + b"\nuser edit\n"
    registry_document.write_bytes(user_owned)
    _simulate_registry_addition(monkeypatch)

    assert codex_adapter._role_registry_state(registry_document.read_bytes()) == "user"
    result = codex_adapter.init(root)

    assert registry_document.read_bytes() == user_owned
    assert "docs/thaliris-role-registry.md" not in result["files"]
    assert "docs/thaliris-role-registry.md" in result["manual_action_required"]


def test_current_registry_document_generation_remains_stable(tmp_path: Path) -> None:
    root = _initialized_repo(tmp_path)
    registry_document = root / "docs" / "thaliris-role-registry.md"

    assert codex_adapter._role_registry_state(registry_document.read_bytes()) == "current"
    result = codex_adapter.init(root)

    assert result["changed"] is False
    assert registry_document.read_bytes() == roles.render_registry_document()
    assert "docs/thaliris-role-registry.md" not in result["files"]
    assert "docs/thaliris-role-registry.md" not in result["manual_action_required"]


def test_generated_registry_document_matches_tracked_artifact() -> None:
    from pathlib import Path

    assert Path("docs/thaliris-role-registry.md").read_bytes() == roles.render_registry_document()
    assert codex_adapter.ROLE_REGISTRY_DOC.encode("utf-8") == roles.render_registry_document()
