"""Explicit recovery of an incomplete managed task."""

import hashlib
import json
import re
import subprocess

import pytest

from thaliris import cli, codex_adapter, core, lifecycle


def _fixture(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    codex_adapter.init(tmp_path)
    started = core.task_start(tmp_path, "old incomplete task", None, None)
    lifecycle.record_task_start_owner(tmp_path, started["task_id"], hashlib.sha256(b"old-controller-session").hexdigest())
    spawn = {
        "session_id": "old-controller-session",
        "turn_id": "turn",
        "tool_name": "spawn_agent",
        "tool_input": {"fork_turns": "none", "agent_type": "thaliris-implementer", "message": "old handoff"},
    }
    assert lifecycle.handle_hook(tmp_path, "PreToolUse", spawn) == ""
    # Emulate the older ledger format whose depth-one pending reservation was
    # the only ownership evidence.
    initial_path = lifecycle._lifecycle_path(tmp_path, started["task_id"])
    initial = json.loads(initial_path.read_text(encoding="utf-8"))
    initial.pop("owner_session_id_hash")
    initial_path.write_text(json.dumps(initial), encoding="utf-8")
    state_path = tmp_path / ".context" / "state.json"
    lifecycle_path = lifecycle._lifecycle_path(tmp_path, started["task_id"])
    state_raw, lifecycle_raw = state_path.read_bytes(), lifecycle_path.read_bytes()
    expected = {
        "task_id": started["task_id"],
        "revision": started["revision"],
        "state_sha256": hashlib.sha256(state_raw).hexdigest(),
        "lifecycle_sha256": hashlib.sha256(lifecycle_raw).hexdigest(),
    }
    return expected, state_raw, lifecycle_raw


def _proof(root, session="new-controller-session"):
    payload = {
        "session_id": session,
        "turn_id": "recovery-turn",
        "tool_name": "Bash",
        "tool_input": {"command": "thaliris task-abandon --task-id x --revision 1 --state-sha256 x --lifecycle-sha256 x --reason takeover"},
    }
    result = json.loads(lifecycle.handle_hook(root, "PreToolUse", payload, lifecycle.MANAGED_HOOK_ABI))
    assert result["hookSpecificOutput"]["permissionDecision"] == "allow"
    return re.search(r"--hook-attestation ([A-Za-z0-9._-]+)$", result["hookSpecificOutput"]["updatedInput"]["command"]).group(1)


def _abandon(root, expected, token):
    return codex_adapter.task_abandon(
        root, expected["task_id"], expected["revision"], expected["state_sha256"],
        expected["lifecycle_sha256"], "Controller chose takeover after incomplete handoff", token,
    )


def test_requires_proof_and_rejects_same_session(tmp_path):
    expected, state_raw, lifecycle_raw = _fixture(tmp_path)
    with pytest.raises(ValueError, match="MANAGED_CURRENT_SESSION_NOT_ATTESTED"):
        _abandon(tmp_path, expected, None)
    with pytest.raises(ValueError, match="owning session"):
        _abandon(tmp_path, expected, _proof(tmp_path, "old-controller-session"))
    assert (tmp_path / ".context" / "state.json").read_bytes() == state_raw
    assert lifecycle._lifecycle_path(tmp_path, expected["task_id"]).read_bytes() == lifecycle_raw


@pytest.mark.parametrize("changed", ["task_id", "revision", "state_sha256", "lifecycle_sha256"])
def test_exact_cas_rejects_changed_identity_or_bytes(tmp_path, changed):
    expected, state_raw, lifecycle_raw = _fixture(tmp_path)
    wrong = dict(expected)
    wrong[changed] = ("0" * 64 if changed.endswith("sha256") else (2 if changed == "revision" else "00000000-0000-0000-0000-000000000000"))
    with pytest.raises(ValueError, match="changed"):
        _abandon(tmp_path, wrong, _proof(tmp_path))
    assert (tmp_path / ".context" / "state.json").read_bytes() == state_raw
    assert lifecycle._lifecycle_path(tmp_path, expected["task_id"]).read_bytes() == lifecycle_raw


def test_archives_raw_evidence_and_allows_fresh_task(tmp_path, capsys):
    expected, state_raw, lifecycle_raw = _fixture(tmp_path)
    token = _proof(tmp_path)
    assert cli.main([
        "--root", str(tmp_path), "task-abandon",
        "--task-id", expected["task_id"], "--revision", str(expected["revision"]),
        "--state-sha256", expected["state_sha256"],
        "--lifecycle-sha256", expected["lifecycle_sha256"],
        "--reason", "Controller chose takeover after incomplete handoff",
        "--hook-attestation", token,
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    archive = tmp_path / result["archive"]
    manifest = json.loads((archive / "manifest.json").read_text(encoding="utf-8"))
    assert result["status"] == manifest["status"] == "ABANDONED"
    assert manifest["lifecycle_status"] == "RECOVERED_INCOMPLETE"
    assert (archive / "state.json").read_bytes() == state_raw
    assert (archive / "lifecycle.json").read_bytes() == lifecycle_raw
    assert manifest["old_controller_owner_provenance"] == "DEPTH_ONE_PENDING_RESERVATION"
    assert manifest["fenced_old_session_provenance"]
    assert not (tmp_path / ".context" / "state.json").exists()
    assert lifecycle._lifecycle_path(tmp_path, expected["task_id"]).read_bytes() == lifecycle_raw
    old_call = {"session_id": "old-controller-session", "tool_name": "Bash", "tool_input": {"command": "echo late"}}
    assert json.loads(lifecycle.handle_hook(tmp_path, "PreToolUse", old_call))["hookSpecificOutput"]["permissionDecision"] == "deny"
    fresh = core.task_start(tmp_path, "fresh task", None, None)
    assert fresh["task_id"] != expected["task_id"]
    assert json.loads(lifecycle.handle_hook(tmp_path, "PreToolUse", old_call))["hookSpecificOutput"]["permissionDecision"] == "deny"
    new_call = {"session_id": "new-controller-session", "tool_name": "Bash", "tool_input": {"command": "thaliris task-status"}}
    assert lifecycle.handle_hook(tmp_path, "PreToolUse", new_call) == ""


def test_unknown_controller_owner_can_be_explicitly_abandoned(tmp_path):
    expected, state_raw, _ = _fixture(tmp_path)
    lifecycle_path = lifecycle._lifecycle_path(tmp_path, expected["task_id"])
    record = json.loads(lifecycle_path.read_text(encoding="utf-8"))
    record["pending_authorized_spawn"] = None
    lifecycle_path.write_text(json.dumps(record), encoding="utf-8")
    expected["lifecycle_sha256"] = hashlib.sha256(lifecycle_path.read_bytes()).hexdigest()
    result = _abandon(tmp_path, expected, _proof(tmp_path))
    manifest = json.loads((tmp_path / result["archive"] / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["old_controller_session_id_hash"] == "UNKNOWN"
    assert manifest["old_controller_owner_provenance"] == "UNKNOWN"
    assert (tmp_path / result["archive"] / "state.json").read_bytes() == state_raw


def test_new_task_owner_survives_pending_clear_and_fences_child(tmp_path):
    expected, _, _ = _fixture(tmp_path)
    path = lifecycle._lifecycle_path(tmp_path, expected["task_id"])
    lifecycle.record_task_start_owner(tmp_path, expected["task_id"], hashlib.sha256(b"old-controller-session").hexdigest())
    record = json.loads(path.read_text(encoding="utf-8"))
    record["children"].append({"session_id_hash": hashlib.sha256(b"old-child-session").hexdigest()})
    record["pending_authorized_spawn"] = None
    record["session_id_hash"] = hashlib.sha256(b"old-child-session").hexdigest()
    path.write_text(json.dumps(record), encoding="utf-8")
    expected["lifecycle_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    result = _abandon(tmp_path, expected, _proof(tmp_path))
    manifest = json.loads((tmp_path / result["archive"] / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["old_controller_owner_provenance"] == "TASK_START"
    assert manifest["old_controller_session_id_hash"] == hashlib.sha256(b"old-controller-session").hexdigest()
    for session in ("old-controller-session", "old-child-session"):
        call = {"session_id": session, "tool_name": "Bash", "tool_input": {"command": "echo late"}}
        assert json.loads(lifecycle.handle_hook(tmp_path, "PreToolUse", call))["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_before_first_spawn_and_absent_lifecycle_are_recoverable(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    codex_adapter.init(tmp_path)
    started = core.task_start(tmp_path, "unspawned", None, None)
    path = lifecycle._lifecycle_path(tmp_path, started["task_id"])
    expected = {"task_id": started["task_id"], "revision": started["revision"], "state_sha256": hashlib.sha256((tmp_path / ".context" / "state.json").read_bytes()).hexdigest(), "lifecycle_sha256": "ABSENT"}
    result = _abandon(tmp_path, expected, _proof(tmp_path))
    archive = tmp_path / result["archive"]
    manifest = json.loads((archive / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["lifecycle_presence"] == "ABSENT"
    assert manifest["old_controller_session_id_hash"] == "UNKNOWN"
    assert not (archive / "lifecycle.json").exists()
    assert not path.exists()


def test_attested_managed_start_records_owner_before_first_spawn(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    codex_adapter.init(tmp_path)
    monkeypatch.setattr(lifecycle, "managed_executable_health", lambda: {"canonical_executable_available": "YES"})
    monkeypatch.setattr(codex_adapter, "selected_continuation_mode", lambda _root: "EVENT_DRIVEN")
    digest = codex_adapter._controller_bridge()["controller_bridge_sha256"]
    payload = {"session_id": "old-controller-session", "turn_id": "start-turn", "tool_name": "Bash", "tool_input": {"command": f"thaliris task-start goal --controller-bridge-sha256 {digest}"}}
    rewritten = json.loads(lifecycle.handle_hook(tmp_path, "PreToolUse", payload, lifecycle.MANAGED_HOOK_ABI))
    token = re.search(r"--hook-attestation ([A-Za-z0-9._-]+)$", rewritten["hookSpecificOutput"]["updatedInput"]["command"]).group(1)
    started = codex_adapter.task_start(tmp_path, "goal", None, None, token, digest)
    path = lifecycle._lifecycle_path(tmp_path, started["task_id"])
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["owner_session_id_hash"] == hashlib.sha256(b"old-controller-session").hexdigest()
    assert record["pending_authorized_spawn"] is None
    expected = {"task_id": started["task_id"], "revision": started["revision"], "state_sha256": hashlib.sha256((tmp_path / ".context" / "state.json").read_bytes()).hexdigest(), "lifecycle_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    with pytest.raises(ValueError, match="owning session"):
        _abandon(tmp_path, expected, _proof(tmp_path, "old-controller-session"))
    result = _abandon(tmp_path, expected, _proof(tmp_path))
    manifest = json.loads((tmp_path / result["archive"] / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["old_controller_owner_provenance"] == "TASK_START"


def test_late_old_callbacks_cannot_change_fresh_task_lifecycle(tmp_path):
    expected, _, _ = _fixture(tmp_path)
    _abandon(tmp_path, expected, _proof(tmp_path))
    fresh = core.task_start(tmp_path, "fresh task", None, None)
    lifecycle.record_task_start_owner(tmp_path, fresh["task_id"], hashlib.sha256(b"new-controller-session").hexdigest())
    spawn = {
        "session_id": "new-controller-session", "turn_id": "new-turn", "tool_name": "spawn_agent",
        "tool_input": {"fork_turns": "none", "agent_type": "thaliris-implementer", "message": "fresh handoff"},
    }
    assert lifecycle.handle_hook(tmp_path, "PreToolUse", spawn) == ""
    child = {"session_id": "new-controller-session", "turn_id": "child-turn", "agent_id": "same-child", "agent_type": "thaliris-implementer"}
    assert lifecycle.handle_hook(tmp_path, "SubagentStart", child) == ""
    lifecycle.handle_hook(tmp_path, "PostToolUse", {**spawn, "tool_response": {"task_name": "/root/same-child"}})
    path = lifecycle._lifecycle_path(tmp_path, fresh["task_id"])
    before = path.read_bytes()
    lifecycle.handle_hook(tmp_path, "SubagentStart", {**child, "session_id": "old-controller-session"})
    lifecycle.handle_hook(tmp_path, "SubagentStop", {**child, "session_id": "old-controller-session"})
    lifecycle.handle_hook(tmp_path, "PostToolUse", {
        "session_id": "old-controller-session", "turn_id": "old-turn", "tool_name": "list_agents",
        "tool_response": {"agents": [{"agent_name": "/root/same-child", "agent_status": {"completed": "old result"}}]},
    })
    assert path.read_bytes() == before
