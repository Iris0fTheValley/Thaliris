"""Bounded delegation scenarios plus scoped live nested Scanner evidence.

Direct-child wire provenance: isolated codex-cli 0.155.0-alpha.9.2 probe,
2026-09-25. Start/PreToolUse/Stop carry the child's agent_id and turn_id;
all share the root session_id. Child PreToolUse also has agent_type. Start
has neither parent_id nor spawn tool_use_id. The 2026-09-25 live managed CLI
probe verified exact reservation/Start/bound PreToolUse acceptance and parent
continuation for one CLI build. Grandchild events below remain contract-shaped
fixtures for other cases; raw Host wire-byte equality and other Host/Desktop
behavior remain UNKNOWN.
"""
from __future__ import annotations

import json
import hashlib
from pathlib import Path
import subprocess

import pytest

from thaliris import codex_adapter, core, lifecycle, roles


@pytest.fixture
def active(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    codex_adapter.init(tmp_path)
    core.task_start(tmp_path, "bounded scanner", None, None)
    return tmp_path


def event(**values):
    return {"session_id": "root-session", "turn_id": "root-turn", **values}


def identity(role="implementer", agent="executor"):
    return event(agent_id=agent, agent_type=f"thaliris-{role}", turn_id=f"{agent}-turn")


def spawn(actor=None, role="investigator", **overrides):
    return {**(actor or event()), "tool_name": "spawn_agent", "tool_input": {
        "agent_type": f"thaliris-{role}", "fork_turns": "none", "message": "Selected facts only", **overrides,
    }}


def state(root):
    task = core.task_show(root)["state"]["task_id"]
    return lifecycle._load_lifecycle(lifecycle._lifecycle_path(root, task), task)


def start(root, role="implementer", agent="executor", actor=None):
    request = spawn(actor, role)
    assert lifecycle.handle_hook(root, "PreToolUse", request) == ""
    child = identity(role, agent)
    assert lifecycle._record_subagent_start(root, child)
    lifecycle.handle_hook(root, "PostToolUse", {**request, "tool_response": {"task_name": f"/root/{agent}"}})
    return child


def finish(root, child, observer=None, status="completed"):
    lifecycle.handle_hook(root, "SubagentStop", child)
    lifecycle.handle_hook(root, "PostToolUse", {**(observer or event()), "tool_name": "list_agents", "tool_response": {
        "agents": [{"agent_name": f'/root/{child["agent_id"]}', "agent_status": {status: "result"}}],
    }})


@pytest.mark.parametrize("role", ["implementer", "focused-implementer", "reviewer"])
def test_executor_scanner_parent_binding_and_completion(active, role):
    parent = start(active, role)
    assert not lifecycle.managed_dependency_pending(active, parent)
    scanner = start(active, "investigator", "scanner", parent)
    assert lifecycle.managed_dependency_pending(active, parent)
    assert not lifecycle.managed_dependency_pending(active, scanner)
    children = state(active)["children"]
    assert [child["depth"] for child in children] == [1, 2]
    assert children[1]["parent_agent_id_hash"] == children[0]["agent_id_hash"]
    assert children[1]["parent_turn_id_hash"] == children[0]["turn_id_hash"]
    assert children[1]["root_handoff_id"] == children[0]["handoff_id"]
    assert children[1]["parent_role"] == role
    assert lifecycle.handle_hook(active, "PreToolUse", {**scanner, "tool_name": "read_file", "tool_input": {}}) == ""
    assert "DELEGATION" in lifecycle.handle_hook(active, "PreToolUse", spawn(scanner))
    assert "SERIAL" in lifecycle.handle_hook(active, "PreToolUse", spawn(parent))
    finish(active, scanner, parent)
    assert not lifecycle.qualifying_child_completed(active)
    finish(active, parent)
    assert lifecycle.qualifying_child_completed(active)
    assert codex_adapter.task_close(active, core.task_show(active)["state"]["revision"])["status"] == "DONE"


def message(actor, target=None, tool_name="send_message"):
    tool_input = {"message": "decision-changing fact"}
    if target is not None:
        tool_input["target"] = target
    return {**actor, "tool_name": tool_name, "tool_input": tool_input}


def test_bound_child_messages_only_root(active):
    child = start(active)
    assert lifecycle.handle_hook(active, "PreToolUse", message(child, "/root")) == ""
    for target in (None, "", "root", "/root/peer", "executor"):
        assert "deny" in lifecycle.handle_hook(active, "PreToolUse", message(child, target))
    for target in (0, ["/root"]):
        assert "deny" in lifecycle.handle_hook(active, "PreToolUse", {**child, "tool_name": "send_message", "tool_input": {"target": target, "message": "fact"}})
    for tool_name in ("followup_task", "send_input"):
        assert "deny" in lifecycle.handle_hook(active, "PreToolUse", message(child, "/root", tool_name))
    assert "deny" in lifecycle.handle_hook(active, "PreToolUse", message({**child, "turn_id": "spoof"}, "/root"))
    assert "deny" in lifecycle.handle_hook(active, "PreToolUse", message(event(), "/root"))


def test_nested_child_messages_only_exact_parent(active):
    parent = start(active)
    scanner = start(active, "investigator", "scanner", parent)
    for target in ("executor", "/root/executor"):
        assert lifecycle.handle_hook(active, "PreToolUse", message(scanner, target)) == ""
    for target in (None, "", "/root", "scanner", "/root/scanner", "/root/peer"):
        assert "deny" in lifecycle.handle_hook(active, "PreToolUse", message(scanner, target))
    for tool_name in ("followup_task", "send_input"):
        assert "deny" in lifecycle.handle_hook(active, "PreToolUse", message(scanner, "executor", tool_name))
    assert "deny" in lifecycle.handle_hook(active, "PreToolUse", message({**scanner, "agent_id": "spoof"}, "executor"))


def test_nested_message_with_missing_parent_task_name_and_ambiguous_target(active):
    request = spawn(role="implementer")
    assert lifecycle.handle_hook(active, "PreToolUse", request) == ""
    parent = identity()
    assert lifecycle._record_subagent_start(active, parent)
    assert state(active)["children"][0]["task_name_hash"] is None
    scanner = start(active, "investigator", "scanner", parent)
    assert lifecycle.handle_hook(active, "PreToolUse", message(scanner, "executor")) == ""
    assert "deny" in lifecycle.handle_hook(active, "PreToolUse", message(scanner, "/root/executor"))
    task = core.task_show(active)["state"]["task_id"]
    path = lifecycle._lifecycle_path(active, task)
    capture = state(active)
    capture["children"][1]["task_name_hash"] = capture["children"][0]["agent_id_hash"]
    lifecycle._write_capture(path, capture)
    assert "deny" in lifecycle.handle_hook(active, "PreToolUse", message(scanner, "executor"))


def test_nested_child_cannot_message_bound_peer(active):
    parent = start(active)
    first = start(active, "investigator", "first", parent)
    finish(active, first, parent)
    second = start(active, "investigator", "second", parent)
    for target in ("first", "/root/first"):
        assert "deny" in lifecycle.handle_hook(active, "PreToolUse", message(second, target))
    assert lifecycle.handle_hook(active, "PreToolUse", message(second, "/root/executor")) == ""


@pytest.mark.parametrize("role", ["investigator", "curator", "reasoning-specialist", "verifier"])
def test_non_executor_delegation_denied(active, role):
    parent = start(active, role)
    assert "DELEGATION" in lifecycle.handle_hook(active, "PreToolUse", spawn(parent))
    assert state(active)["pending_authorized_spawn"] is None


@pytest.mark.parametrize("target", ["implementer", "focused-implementer", "reviewer", "curator", "reasoning-specialist", "verifier"])
def test_executor_only_delegates_scanner(active, target):
    parent = start(active)
    assert "DELEGATION" in lifecycle.handle_hook(active, "PreToolUse", spawn(parent, target))


@pytest.mark.parametrize("field", ["agent_id", "agent_type", "turn_id", "session_id"])
@pytest.mark.parametrize("missing", [True, False])
def test_nested_exact_parent_identity_fails_closed(active, field, missing):
    parent = start(active)
    request = spawn(parent)
    if missing:
        request.pop(field)
    else:
        request[field] = "wrong"
    assert "deny" in lifecycle.handle_hook(active, "PreToolUse", request)
    assert state(active)["pending_authorized_spawn"] is None


def test_start_consumes_only_exact_reservation_and_requires_own_identity(active):
    parent = start(active)
    assert lifecycle.handle_hook(active, "PreToolUse", spawn(parent)) == ""
    for changes in ({"session_id": "wrong"}, {"turn_id": None}, {"agent_id": "executor"}, {"agent_type": "thaliris-curator"}):
        assert not lifecycle._record_subagent_start(active, {**identity("investigator", "scanner"), **changes})
        assert state(active)["pending_authorized_spawn"] is not None
    # A previously rejected identity is never rebound; use a fresh native ID.
    scanner = identity("investigator", "fresh-scanner")
    assert lifecycle._record_subagent_start(active, scanner)
    for key in ("agent_id", "agent_type", "turn_id", "session_id"):
        assert "deny" in lifecycle.handle_hook(active, "PreToolUse", {**scanner, key: "wrong", "tool_name": "read_file", "tool_input": {}})


def test_parent_stop_before_scanner_start_does_not_bind(active):
    parent = start(active)
    assert lifecycle.handle_hook(active, "PreToolUse", spawn(parent)) == ""
    lifecycle.handle_hook(active, "SubagentStop", parent)
    assert not lifecycle._record_subagent_start(active, identity("investigator", "scanner"))
    assert state(active)["pending_authorized_spawn"] is not None
    finish(active, parent)
    assert not lifecycle.qualifying_child_completed(active)


def test_spawn_return_is_correlated_to_authorized_parent(active):
    parent = start(active)
    request = spawn(parent)
    request["tool_use_id"] = "nested-spawn-call"
    assert lifecycle.handle_hook(active, "PreToolUse", request) == ""
    scanner = identity("investigator", "scanner")
    assert lifecycle._record_subagent_start(active, scanner)
    for wrong in ({**event()}, {**parent, "turn_id": "wrong"}, parent):
        lifecycle.handle_hook(active, "PostToolUse", {**wrong, "tool_name": "spawn_agent", "tool_response": {"task_name": "/wrong"}})
        assert state(active)["children"][-1]["task_name_hash"] is None
    lifecycle.handle_hook(active, "PostToolUse", {**request, "tool_response": {"task_name": "/root/scanner"}})
    assert state(active)["children"][-1]["task_name_hash"] == lifecycle._identity_hash("/root/scanner")


@pytest.mark.parametrize("role", ["implementer", "focused-implementer", "reviewer"])
def test_parent_wait_normalizes_only_its_pending_scanner(active, monkeypatch, role):
    monkeypatch.setattr(codex_adapter, "selected_continuation_mode", lambda root: "BLOCKING_WAIT")
    monkeypatch.setattr(codex_adapter, "host_explicit_blocking_wait", lambda: {"status": "PASS", "effective_max_wait_timeout_ms": 60000})
    parent = start(active, role)
    wait_input = {"timeout_ms": 1, "future_argument": {"keep": True}}
    wait = {**parent, "tool_name": "wait_agent", "tool_input": wait_input}
    assert codex_adapter.audit_hook(active, "PreToolUse", wait) == ""
    assert wait["tool_input"] == wait_input
    scanner = start(active, "investigator", "scanner", parent)
    result = json.loads(codex_adapter.audit_hook(active, "PreToolUse", wait))
    assert result["hookSpecificOutput"]["updatedInput"] == {
        **wait_input, "timeout_ms": 60000,
    }
    finish(active, scanner, parent)
    assert codex_adapter.audit_hook(active, "PreToolUse", wait) == ""


def test_active_or_pending_descendant_prevents_close(active):
    parent = start(active)
    scanner = start(active, "investigator", "scanner", parent)
    finish(active, parent)
    assert not lifecycle.qualifying_child_completed(active)
    # A bound Scanner keeps its own identity after the parent terminates.
    assert lifecycle.handle_hook(active, "PreToolUse", {**scanner, "tool_name": "read_file", "tool_input": {}}) == ""
    finish(active, scanner)
    assert lifecycle.qualifying_child_completed(active)


def test_latest_scanner_failure_does_not_replace_successful_parent(active):
    parent = start(active)
    scanner = start(active, "investigator", "scanner", parent)
    finish(active, scanner, parent, "errored")
    finish(active, parent)
    assert lifecycle.qualifying_child_completed(active)


def test_successful_scanner_does_not_hide_parent_failure(active):
    parent = start(active)
    scanner = start(active, "investigator", "scanner", parent)
    finish(active, scanner, parent)
    finish(active, parent, status="errored")
    assert not lifecycle.qualifying_child_completed(active)


def test_nested_pending_recovery_is_exact_and_controller_owned(active):
    parent = start(active)
    assert lifecycle.handle_hook(active, "PreToolUse", spawn(parent)) == ""
    handoff = state(active)["pending_authorized_spawn"]["handoff_id"]
    with pytest.raises(ValueError, match="does not match"):
        lifecycle.recover_pending_spawn(active, "handoff-" + "0" * 32)
    denied = lifecycle.handle_hook(active, "PreToolUse", {**parent, "tool_name": "Bash", "tool_input": {"command": f"thaliris recover-pending-spawn {handoff}"}})
    assert "CONTROL_STATE_MUTATION" in denied
    assert lifecycle.recover_pending_spawn(active, handoff)["recovered"]
    assert lifecycle.handle_hook(active, "PreToolUse", spawn(parent)) == ""


def test_model_override_is_controller_only_and_exact(active):
    for overrides in ({"model": "gpt-6-luna"}, {"reasoning_effort": "xhigh"}, {"thinking": "xhigh"}, {"model_reasoning_effort": "xhigh"}, {"model": "gpt-6-astra", "reasoning_effort": "high"}):
        assert "MODEL_OVERRIDE" in lifecycle.handle_hook(active, "PreToolUse", spawn(role="implementer", **overrides))
    request = spawn(role="implementer", model="gpt-6-astra", reasoning_effort="xhigh")
    assert "MODEL_OVERRIDE" in lifecycle.handle_hook(active, "PreToolUse", request)
    parent = start(active)
    assert "MODEL_OVERRIDE" in lifecycle.handle_hook(active, "PreToolUse", spawn(parent, model="gpt-6-astra", reasoning_effort="xhigh"))


@pytest.mark.parametrize("field", ["model", "reasoning_effort", "thinking", "model_reasoning_effort"])
def test_top_level_fallback_model_override_is_denied(active, field):
    request = event(
        tool_name="spawn_agent",
        agentType="thaliris-implementer",
        fork_turns="none",
        message="Selected facts only",
        **{field: "gpt-6-astra" if field == "model" else "xhigh"},
    )
    assert "MODEL_OVERRIDE" in lifecycle.handle_hook(active, "PreToolUse", request)


def test_top_level_fallback_spawn_without_override_remains_authorized(active):
    request = event(
        tool_name="spawn_agent",
        agentType="thaliris-implementer",
        fork_turns="none",
        message="Selected facts only",
    )
    assert lifecycle.handle_hook(active, "PreToolUse", request) == ""
    assert state(active)["pending_authorized_spawn"] is not None


@pytest.mark.parametrize("role", ["focused-implementer", "reasoning-specialist"])
def test_controller_selects_static_exceptional_profile(active, role):
    profile = f"thaliris-{role}-xhigh"
    assert roles.resolve_native_profile(profile).id == role
    assert roles.agent_profiles()[profile + ".toml"] == ("gpt-6-astra", "xhigh", role)
    request = spawn(role=role)
    request["tool_input"]["agent_type"] = profile
    assert lifecycle.handle_hook(active, "PreToolUse", request) == ""
    parent = {**identity(role), "agent_type": profile}
    assert lifecycle._record_subagent_start(active, parent)
    assert state(active)["children"][0]["role"] == role
    if role == "focused-implementer":
        assert lifecycle.handle_hook(active, "PreToolUse", spawn(parent)) == ""
    else:
        assert "DELEGATION" in lifecycle.handle_hook(active, "PreToolUse", spawn(parent))


@pytest.mark.parametrize("role", ["focused-implementer", "reasoning-specialist"])
def test_executor_cannot_select_exceptional_profile(active, role):
    parent = start(active)
    request = spawn(parent, role)
    request["tool_input"]["agent_type"] += "-xhigh"
    assert "DELEGATION" in lifecycle.handle_hook(active, "PreToolUse", request)
    default = (Path(__file__).parent / "fixtures" / f"phase2-{'reasoning-specialist' if role == 'focused-implementer' else role}.toml").read_bytes()
    assert codex_adapter._agent_profile_state(default, f"thaliris-{role}-xhigh.toml") == "user"


def test_previous_flat_lifecycle_state_is_not_nested_authority(active):
    start(active)
    task = core.task_show(active)["state"]["task_id"]
    path = lifecycle._lifecycle_path(active, task)
    previous = state(active)
    previous["version"] = 11
    path.write_text(json.dumps(previous), encoding="utf-8")
    assert not lifecycle.qualifying_child_completed(active)
    assert "deny" in lifecycle.handle_hook(active, "PreToolUse", spawn(identity()))


@pytest.mark.parametrize("kind", ["profile", "alias", "filename"])
def test_registry_identity_uniqueness(monkeypatch, kind):
    kwargs = {"native_profile": "new", "profile_filename": "new.toml"}
    kwargs[{"profile": "native_profile", "alias": "native_aliases", "filename": "profile_filename"}[kind]] = {
        "profile": "thaliris-investigator", "alias": ("luna",), "filename": "thaliris-investigator.toml",
    }[kind]
    monkeypatch.setitem(roles.ROLE_REGISTRY, "new", (roles.RoleSpec("new", "test"), roles.CodexExecutionBinding(**kwargs)))
    with pytest.raises(ValueError, match="duplicate"):
        roles.role_choices()


def test_independent_phase_two_profile_migration_and_user_edits(tmp_path, monkeypatch, pinned_test_thaliris):
    # Exact generator at immutable 5e6554196d27c4d6bc87c2a8008bd3c37ef01b31:
    # roles blob 481aba1ef66448238f1b00ff4b58eba3f28f9605;
    # adapter blob 880d5a9753220bcf09f27bc34890e411ccee17c4.
    # Fixtures are fixed UTF-8/LF bytes, never reconstructed from current HEAD.
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    codex_adapter.init(tmp_path)
    host_home = tmp_path / "codex-home"
    monkeypatch.setenv("CODEX_HOME", str(host_home))
    host_agents = host_home / "agents"
    host_agents.mkdir(parents=True)
    for role, digest in roles._PHASE_TWO_PROFILE_HASHES.items():
        value = (Path(__file__).parent / "fixtures" / f"phase2-{role}.toml").read_bytes()
        assert hashlib.sha256(value).hexdigest() == digest
        name = f"thaliris-{role}.toml"
        assert codex_adapter._agent_profile_state(value, name) == "legacy"
        assert codex_adapter._agent_profile_state(value + b"\n# user edit\n", name) == "user"
        (host_agents / name).write_bytes(value)
    packs = (Path(__file__).parent / "fixtures" / "phase2-role-packs.md").read_bytes()
    assert hashlib.sha256(packs).hexdigest() == "0a51833bf936b14053c08a6502a6a1d27ecd1518263e7eea5c4e43f53fa1c5f1"
    assert codex_adapter._role_pack_state(packs) == "legacy"
    (tmp_path / "docs" / "thaliris-role-packs.md").write_bytes(packs)
    install = codex_adapter.codex_install()
    assert install["host_profile_definition_present"] == "YES"
    assert install["host_role_catalog_status"] == "HOST_ROLE_CATALOG_UNKNOWN"
    migrated = {f"thaliris-{role}.toml" for role in roles._PHASE_TWO_PROFILE_HASHES}
    assert {f"agents/{name}" for name in migrated} <= set(install["files"])
    for name in host_agents.glob("thaliris-*.toml"):
        assert codex_adapter._agent_profile_state(name.read_bytes(), name.name) == "current"
    result = codex_adapter.init(tmp_path)
    assert result["agent_profile_changed"] is False
    assert not (tmp_path / ".codex" / "agents").exists()
    assert (tmp_path / "docs" / "thaliris-role-packs.md").read_text(encoding="utf-8") == codex_adapter.render_role_packs()


def test_profile_quotes_remain_valid_toml():
    import tomllib
    for name, (model, effort, role) in roles.agent_profiles().items():
        parsed = tomllib.loads(codex_adapter._agent_profile(name.removesuffix(".toml"), role, model, effort).decode())
        assert parsed["developer_instructions"] == roles.get_role(role).instructions
