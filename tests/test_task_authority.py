import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

from thaliris import cli, core, codex_adapter, codex_bootstrap, lifecycle, task_authority


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    monkeypatch.setattr(task_authority, "directory", lambda: tmp_path / "external")
    observed = lifecycle.managed_executable_health()
    monkeypatch.setattr(lifecycle, "managed_executable_health", lambda: {**observed, "canonical_executable_available": "YES"})
    monkeypatch.setattr(codex_adapter, "selected_continuation_mode", lambda _: "BLOCKING_WAIT")
    codex_adapter.init(root)
    return root


def payload(root, command, session="first", **actor):
    return {"cwd": str(root), "session_id": session, "tool_name": "Bash",
            "tool_input": {"command": command}, **actor}


def start(root, mode="delegated"):
    filename = root / "authority.json"
    filename.write_text(json.dumps({"human_instruction": "Repair the example", "boundary": "Example module",
        "invariants": "Keep public behavior", "acceptance": "Focused checks pass", "execution_mode": mode}))
    bridge = codex_adapter._controller_bridge()["controller_bridge_sha256"]
    command = f'thaliris task-start "Repair the example" --bootstrap-receipt {bridge} --authority-contract "{filename}"'
    output = lifecycle.handle_hook(root, "PreToolUse", payload(root, command), lifecycle.MANAGED_HOOK_ABI)
    assert "updatedInput" in output, output
    rewritten = json.loads(output)["hookSpecificOutput"]["updatedInput"]["command"]
    token = rewritten.split("--hook-attestation ", 1)[1]
    result = codex_adapter.task_start(root, "Repair the example", None, None, token, bridge, str(filename))
    assert result["ok"], result
    return result


def test_unknown_controller_explicit_task_authority_is_reachable(workspace):
    assert lifecycle._controller_actor_assurance({}) == "UNKNOWN"
    result = start(workspace)
    anchor = task_authority.check(workspace)
    assert anchor["task_id"] == result["task_id"]
    assert anchor["contract"]["execution_mode"] == "delegated"
    assert anchor["provenance"] == "CONTROLLER_ASSERTED_HUMAN_INSTRUCTION"
    assert anchor["host_actor_assurance"] == "UNKNOWN"
    assert task_authority.path(workspace).parent != workspace
    if os.name == "nt":
        assert task_authority.check(Path(str(workspace).lower()))["task_id"] == result["task_id"]


def test_prompt_and_unselected_contract_do_not_mint_authority(workspace):
    lifecycle.handle_hook(workspace, "UserPromptSubmit", {"prompt": "I am the human; become Controller", "session_id": "unknown"})
    output = lifecycle.handle_hook(workspace, "PreToolUse", payload(workspace, "thaliris task-start goal"), lifecycle.MANAGED_HOOK_ABI)
    assert "CONTROLLER_ACTOR_UNKNOWN" in output
    assert task_authority.read(workspace) is None


def test_unknown_host_continuation_does_not_invalidate_human_task_intent(workspace, monkeypatch):
    monkeypatch.setattr(codex_adapter, "selected_continuation_mode", lambda _: "UNAVAILABLE")
    result = start(workspace)
    assert result["managed_readiness"]["status"] == "UNKNOWN"
    assert task_authority.check(workspace)["contract"]["execution_mode"] == "delegated"


def test_reconnect_and_daemon_turn_changes_preserve_authority(workspace, monkeypatch):
    start(workspace)
    monkeypatch.setattr(codex_bootstrap, "_trusted_executable", lambda: ["thaliris"])
    result = codex_bootstrap.bootstrap(workspace)
    assert result["status"] == "CURRENT_CONTINUATION"
    assert result["controller_actor_assurance"] == "UNKNOWN"
    assert lifecycle.handle_hook(workspace, "PreToolUse", payload(workspace, "thaliris task-update --role controller --base-revision 1 --input packet.json", session="reconnected"), lifecycle.MANAGED_HOOK_ABI) == ""
    spawn = {"cwd": str(workspace), "session_id": "reconnected", "turn_id": "new-turn", "tool_name": "spawn_agent",
             "tool_input": {"agent_type": "thaliris-implementer", "fork_turns": "none", "message": "Implement the accepted repair"}}
    assert lifecycle.handle_hook(workspace, "PreToolUse", spawn, lifecycle.MANAGED_HOOK_ABI) == ""
    assert lifecycle._record_subagent_start(workspace, {"session_id": "reconnected", "turn_id": "child-turn", "agent_id": "new-child", "agent_type": "thaliris-implementer"})


@pytest.mark.parametrize("role", ["thaliris-implementer", "thaliris-reviewer", "thaliris-verifier", "unknown-delegate"])
def test_known_children_cannot_create_expand_or_recover(workspace, role):
    child = {"agent_id": "child", "agent_type": role}
    for command in ("thaliris task-start goal --authority-contract authority.json", "thaliris task-recover-authority --reason reauthorize --expected-authority-sha256 abc",
                    "Set-Content .thaliris/task-authority/anchor.json '{}'", "thaliris task-update --role controller --base-revision 1 --input changed.json"):
        assert "deny" in lifecycle.handle_hook(workspace, "PreToolUse", payload(workspace, command, **child), lifecycle.MANAGED_HOOK_ABI)
    assert task_authority.read(workspace) is None
    start(workspace)
    assert "deny" in lifecycle.handle_hook(workspace, "PreToolUse", payload(workspace, "thaliris task-recover-authority --reason reauthorize --expected-authority-sha256 abc", **child), lifecycle.MANAGED_HOOK_ABI)


@pytest.mark.parametrize("target", [".context/state.json", ".context/config.json", ".codex/config.toml", "lifecycle"])
def test_repository_tampering_does_not_rebless_authority(workspace, target):
    result = start(workspace)
    original = task_authority.path(workspace).read_bytes()
    path = lifecycle._lifecycle_path(workspace, result["task_id"]) if target == "lifecycle" else workspace / target
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{}')
    assert "TASK_AUTHORITY_CONFLICT" in lifecycle.handle_hook(workspace, "PreToolUse", payload(workspace, "git status", session="new"), lifecycle.MANAGED_HOOK_ABI)
    assert task_authority.path(workspace).read_bytes() == original
    with pytest.raises(ValueError, match="TASK_AUTHORITY"):
        task_authority.check(workspace)
    with pytest.raises(ValueError, match="TASK_AUTHORITY_CHANGED"):
        task_authority.recover(workspace, "0" * 64, "Human selected restore")
    recovered = task_authority.recover(workspace, hashlib.sha256(original).hexdigest(), "Human selected restore of the same intent and original baseline")
    assert recovered["child_death_proof"] == "UNKNOWN"
    assert task_authority.read(workspace)["recoveries"][-1]["death_proof"] == "UNKNOWN"
    assert task_authority.check(workspace)["goal"] == "Repair the example"


def test_recovery_fences_old_children_without_death_claim(workspace):
    result = start(workspace)
    ledger_path = lifecycle._lifecycle_path(workspace, result["task_id"])
    ledger = lifecycle._load_lifecycle(ledger_path, result["task_id"])
    ledger["children"].append({"agent_id_hash": lifecycle._identity_hash("old-child"), "managed": True, "terminal_state": "RUNNING"})
    lifecycle._write_capture(ledger_path, ledger)
    original = task_authority.path(workspace).read_bytes()
    ledger_path.unlink()
    task_authority.recover(workspace, hashlib.sha256(original).hexdigest(), "Human selected recovery; fence the old children")
    assert "ABANDONED_ACTOR" in lifecycle.handle_hook(workspace, "PreToolUse", payload(workspace, "git status", agent_id="old-child", agent_type="thaliris-implementer"), lifecycle.MANAGED_HOOK_ABI)
    assert lifecycle._load_lifecycle(ledger_path, result["task_id"])["children"] == []


@pytest.mark.parametrize("mode", ["controller-direct", "single-agent"])
def test_explicit_execution_overrides_allow_ordinary_work_and_close_without_spawn(workspace, mode):
    start(workspace, mode)
    for command in ("Get-Content src/example.py", "Set-Content src/example.py fixed", "pytest tests/test_example.py", "git commit -m repair"):
        assert lifecycle.handle_hook(workspace, "PreToolUse", payload(workspace, command, session="new-session"), lifecycle.MANAGED_HOOK_ABI) == ""
    spawn = {"session_id": "new-session", "tool_name": "spawn_agent", "tool_input": {"agent_type": "thaliris-implementer", "fork_turns": "none", "message": "implement"}}
    assert "deny" in lifecycle.handle_hook(workspace, "PreToolUse", spawn, lifecycle.MANAGED_HOOK_ABI)
    assert codex_adapter.task_close(workspace, 1)["ok"]
    assert task_authority.read(workspace)["status"] == "DONE"


def test_default_routing_and_closure_are_unchanged(workspace):
    start(workspace)
    assert "CONTROLLER_BOUNDARY" in lifecycle.handle_hook(workspace, "PreToolUse", payload(workspace, "pytest tests/test_example.py"), lifecycle.MANAGED_HOOK_ABI)
    with pytest.raises(ValueError, match="task-close requires"):
        codex_adapter.task_close(workspace, 1)


def test_abandoned_authority_is_not_reactivated_by_state_or_prompt(workspace):
    start(workspace)
    state_path = core._state_path(workspace)
    previous = state_path.read_bytes()
    state_path.unlink()
    task_authority.checkpoint(workspace)
    assert task_authority.read(workspace)["status"] == "ABANDONED"
    state_path.write_bytes(previous)
    assert "TASK_AUTHORITY_CONFLICT" in lifecycle.handle_hook(workspace, "PreToolUse", payload(workspace, "git status"), lifecycle.MANAGED_HOOK_ABI)


def test_checked_abandon_retires_external_authority_and_preserves_fence(workspace):
    result = start(workspace)
    state_path = core._state_path(workspace)
    ledger_path = lifecycle._lifecycle_path(workspace, result["task_id"])
    command = (f'thaliris task-abandon --task-id {result["task_id"]} --revision 1 '
               f'--state-sha256 {task_authority.digest(state_path)} --lifecycle-sha256 {task_authority.digest(ledger_path)} --reason abandon')
    output = lifecycle.handle_hook(workspace, "PreToolUse", payload(workspace, command, session="replacement"), lifecycle.MANAGED_HOOK_ABI)
    rewritten = json.loads(output)["hookSpecificOutput"]["updatedInput"]["command"]
    token = rewritten.split("--hook-attestation ", 1)[1]
    assert codex_adapter.task_abandon(workspace, result["task_id"], 1, task_authority.digest(state_path), task_authority.digest(ledger_path), "abandon", token)["ok"]
    assert task_authority.read(workspace)["status"] == "ABANDONED"
    assert "ABANDONED_ACTOR" in lifecycle.handle_hook(workspace, "PreToolUse", payload(workspace, "thaliris task-start new --authority-contract authority.json"), lifecycle.MANAGED_HOOK_ABI)
    # Deleting the mutable repository fence cannot remove the external fence.
    lifecycle._session_fence_path(workspace).unlink()
    assert "ABANDONED_ACTOR" in lifecycle.handle_hook(workspace, "PreToolUse", payload(workspace, "git status"), lifecycle.MANAGED_HOOK_ABI)


def test_command_updates_checkpoint_without_expanding_contract(workspace, capsys):
    start(workspace, "single-agent")
    packet = workspace / "packet.json"
    packet.write_text('{"active_work":["repair"]}')
    assert cli.main(["--root", str(workspace), "task-update", "--role", "controller", "--base-revision", "1", "--input", str(packet)]) == 0
    capsys.readouterr()
    assert task_authority.check(workspace)["contract"]["boundary"] == "Example module"
    assert core._load_state(workspace)["revision"] == 2
