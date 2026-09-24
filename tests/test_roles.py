from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import tomllib

import pytest

from thaliris import cli, codex_adapter, core, lifecycle, roles


def _sentinel_definition() -> roles.RoleDefinition:
    return roles.RoleDefinition(
        id="sentinel",
        default_model="gpt-5.6-luna",
        reasoning_effort="high",
        native_profile="thaliris-sentinel",
        instructions="sentinel instructions",
        repo_write_allowed=True,
        allowed_delegation_targets=frozenset(),
        controller_control_state_modification_allowed=False,
        generated_profile=True,
        profile_filename="thaliris-sentinel.toml",
    )


def _formal_sentinel_registration() -> tuple[roles.RoleSpec, roles.CodexExecutionBinding]:
    return (
        roles.RoleSpec(
            id="formal-sentinel",
            purpose="A seventh role used to prove registry propagation.",
            instructions="formal sentinel instructions",
        ),
        roles.CodexExecutionBinding(
            model="gpt-5.6-luna",
            reasoning_effort="high",
            native_profile="thaliris-formal-sentinel",
            native_aliases=("formal-sentinel-alias",),
            generated_profile=True,
            profile_filename="thaliris-formal-sentinel.toml",
            repo_write_allowed=False,
            allowed_delegation_targets=frozenset(),
            controller_control_state_modification_allowed=False,
            telemetry_notice=True,
            write_denial_code="THALIRIS_FORMAL_SENTINEL_WRITE_BLOCKED",
            write_denial_reason="Formal sentinel must remain read-only.",
        ),
    )


def test_registry_is_authoritative_for_native_profiles_and_mechanical_facts() -> None:
    native = roles.native_role_definitions()
    assert [definition.id for definition in native] == [
        "investigator", "curator", "reasoning-specialist", "implementer", "focused-implementer", "verifier", "reviewer",
    ]
    for definition in native:
        assert definition.native_profile == f"thaliris-{definition.id}"
        assert definition.profile_filename == f"thaliris-{definition.id}.toml"
        assert definition.instructions
        assert definition.reasoning_effort
        assert definition.legacy_profile_hashes or definition.id == "focused-implementer"
    assert roles.native_agent_roles() == {
        profile: definition.id for definition in native
        for profile in (definition.native_profile, definition.astra_medium_native_profile, definition.exceptional_native_profile) if profile
    }
    expected_profiles = {
        definition.profile_filename: (
            definition.default_model, definition.reasoning_effort, definition.id
        )
        for definition in native
    }
    for definition in native:
        if definition.astra_medium_native_profile:
            expected_profiles[definition.astra_medium_native_profile + ".toml"] = ("gpt-6-astra", "medium", definition.id)
        if definition.exceptional_native_profile:
            expected_profiles[definition.exceptional_native_profile + ".toml"] = ("gpt-6-astra", "xhigh", definition.id)
    assert roles.agent_profiles() == expected_profiles
    assert roles.notice_roles() == {"curator", "reasoning-specialist", "verifier", "reviewer"}


def test_profile_defaults_and_static_astra_selection_are_fixed() -> None:
    assert codex_adapter._ROLE_MODEL_DEFAULTS == {
        "controller": (None, None),
        "investigator": ("gpt-6-luna", "xhigh"),
        "curator": ("gpt-6-luna", "xhigh"),
        "reasoning-specialist": ("gpt-6-sol", "high"),
        "implementer": ("gpt-6-luna", "xhigh"),
        "focused-implementer": ("gpt-6-sol", "high"),
        "verifier": ("gpt-6-luna", "xhigh"),
        "reviewer": ("gpt-6-sol", "high"),
    }
    assert len(roles.native_codex_role_map()) == len(set(roles.native_codex_role_map()))
    for name, (model, effort, role) in roles.agent_profiles().items():
        value = tomllib.loads(codex_adapter._agent_profile(name.removesuffix(".toml"), role, model, effort).decode())
        assert (value["name"], value["model"], value["model_reasoning_effort"]) == (name.removesuffix(".toml"), model, effort)
        assert roles.resolve_native_profile(value["name"]).id == role
        assert "Never select your own model or reasoning effort" in value["developer_instructions"]
        if role in {"implementer", "focused-implementer"}:
            assert "Work only within the assigned semantic slice" in value["developer_instructions"]
            assert "return a decision-changing unknown instead of changing them" in value["developer_instructions"]
            assert "its commit reference, and verification evidence" in value["developer_instructions"]
    for role in ("focused-implementer", "reasoning-specialist"):
        for effort, suffix in (("medium", "astra-medium"), ("xhigh", "xhigh")):
            name = f"thaliris-{role}-{suffix}.toml"
            assert roles.agent_profiles()[name] == ("gpt-6-astra", effort, role)
            assert codex_adapter._KNOWN_GENERATED_AGENT_PROFILE_HASHES.get(name, frozenset()) == frozenset()


def test_exact_phase_two_profile_bytes_are_recognized_only_for_own_role() -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    for role in ("investigator", "curator", "reasoning-specialist", "implementer", "verifier", "reviewer"):
        name = f"thaliris-{role}.toml"
        value = (fixture_dir / f"phase2-{role}.toml").read_bytes()
        assert hashlib.sha256(value).hexdigest() in roles.get_codex_binding(role).legacy_profile_hashes
        assert codex_adapter._agent_profile_state(value, name) == "legacy"
        assert codex_adapter._agent_profile_state(value + b"\nuser edit\n", name) == "user"
        other_name = "thaliris-curator.toml" if role != "curator" else "thaliris-investigator.toml"
        assert codex_adapter._agent_profile_state(value, other_name) == "user"


def test_phase_two_profiles_migrate_while_edited_profile_is_preserved(tmp_path: Path) -> None:
    root = _initialized_repo(tmp_path)
    agents = root / ".codex" / "agents"
    fixture_dir = Path(__file__).parent / "fixtures"
    roles_to_migrate = ("investigator", "curator", "reasoning-specialist", "implementer", "verifier", "reviewer")
    for role in roles_to_migrate:
        (agents / f"thaliris-{role}.toml").write_bytes((fixture_dir / f"phase2-{role}.toml").read_bytes())
    edited_name = "thaliris-reviewer.toml"
    edited = (agents / edited_name).read_bytes() + b"\nuser edit\n"
    (agents / edited_name).write_bytes(edited)

    result = codex_adapter.init(root)

    assert (agents / edited_name).read_bytes() == edited
    assert f".codex/agents/{edited_name}" in result["manual_action_required"]
    for role in roles_to_migrate[:-1]:
        name = f"thaliris-{role}.toml"
        assert codex_adapter._agent_profile_state((agents / name).read_bytes(), name) == "current"
        assert f".codex/agents/{name}" in result["files"]


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


def test_doctor_reports_missing_registry_document(tmp_path: Path) -> None:
    root = _initialized_repo(tmp_path)
    registry_document = root / "docs" / "thaliris-role-registry.md"
    registry_document.unlink()

    result = codex_adapter.doctor(root)

    assert result["role_registry"]["generated_role_document"] == "MISSING"


def test_formal_seventh_role_requires_only_spec_and_binding(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setitem(roles.ROLE_REGISTRY, "formal-sentinel", _formal_sentinel_registration())
    root = _initialized_repo(tmp_path)

    profile = root / ".codex" / "agents" / "thaliris-formal-sentinel.toml"
    assert profile.is_file()
    assert 'model_reasoning_effort = "high"' in profile.read_text(encoding="utf-8")
    assert codex_adapter.bootstrap_check(root)["project_definition_present"] == "YES"
    assert lifecycle._native_agent_roles()["thaliris-formal-sentinel"] == "formal-sentinel"
    role_action = next(
        action
        for action in cli._parser()._subparsers._group_actions[0].choices["task-update"]._actions
        if action.dest == "role"
    )
    assert "formal-sentinel" in role_action.choices
    assert "formal-sentinel" in codex_adapter.doctor(root)["role_registry"]["roles"]
    assert "Formal Sentinel" in codex_adapter.render_managed()
    assert "Formal Sentinel" in codex_adapter.render_role_packs()
    assert "| `formal-sentinel` |" in roles.render_registry_document().decode()
    assert roles.get_codex_binding("formal-sentinel").legacy_profile_hashes == frozenset()

    delegation = lifecycle._child_pre_tool_output(root, {
        "agent_type": "thaliris-formal-sentinel",
        "tool_name": "spawn_agent",
        "tool_input": {},
    })
    write = lifecycle._child_pre_tool_output(root, {
        "agent_type": "thaliris-formal-sentinel",
        "tool_name": "Bash",
        "tool_input": {"command": "echo output > generated.txt"},
    })
    control = lifecycle._child_pre_tool_output(root, {
        "agent_type": "thaliris-formal-sentinel",
        "tool_name": "Bash",
        "tool_input": {"command": "thaliris task-update --role formal-sentinel"},
    })
    assert "THALIRIS_ROLE_SESSION_DELEGATION" in delegation
    assert "THALIRIS_FORMAL_SENTINEL_WRITE_BLOCKED" in write
    assert "THALIRIS_ROLE_SESSION_CONTROL_STATE_MUTATION" in control


def test_registry_rejects_key_that_differs_from_spec_identity(monkeypatch) -> None:
    monkeypatch.setitem(
        roles.ROLE_REGISTRY,
        "formal-key",
        (
            roles.RoleSpec(id="formal-spec", instructions="formal instructions"),
            roles.CodexExecutionBinding(native_profile="thaliris-formal-key"),
        ),
    )

    with pytest.raises(
        ValueError,
        match=r"ROLE_REGISTRY key 'formal-key' must match RoleSpec\.id 'formal-spec'",
    ):
        roles.role_choices()


def test_managed_renderer_matches_working_artifact_and_derives_added_role(monkeypatch) -> None:
    # Current output consistency is not historical ownership evidence.
    baseline = Path("AGENTS.md").read_bytes()
    marker_start = codex_adapter.MANAGED_START.encode("utf-8")
    marker_end = codex_adapter.MANAGED_END.encode("utf-8")
    start = baseline.index(marker_start)
    end = baseline.index(marker_end, start) + len(marker_end)
    checked_in = (baseline[start:end] + b"\n").decode("utf-8")
    if checked_in != codex_adapter.render_managed():
        assert codex_adapter._managed_agents_state(checked_in) == "user"

    monkeypatch.setitem(roles.ROLE_REGISTRY, "formal-sentinel", _formal_sentinel_registration())
    rendered = codex_adapter.render_managed()
    assert (
        "Fresh Investigator, Curator, Reasoning Specialist, Implementer, Focused Implementer, Verifier, "
        "Reviewer, and Formal Sentinel sessions"
    ) in rendered
    assert (
        "never enter an Investigator, Curator, Reasoning Specialist, Implementer, Focused Implementer, "
        "Verifier, Reviewer, or Formal Sentinel automatically."
    ) in rendered
