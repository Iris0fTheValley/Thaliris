from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess

import pytest

from thaliris import codex_adapter, lifecycle


def test_direct_init_posttool_delivers_one_shot_proof_before_first_task_start(tmp_path: Path, monkeypatch) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    payload = {
        "session_id": "init-session",
        "turn_id": "init-turn",
        "cwd": str(tmp_path),
        "tool_name": "Bash",
        "tool_input": {"command": f'thaliris --root "{tmp_path}" init'},
    }
    codex_adapter.audit_hook(tmp_path, "SessionStart", {
        "session_id": "init-session", "source": "startup", "cwd": str(tmp_path),
    })
    assert codex_adapter.audit_hook(tmp_path, "PreToolUse", payload, lifecycle.MANAGED_HOOK_ABI) == ""
    result = codex_adapter.init(tmp_path)
    digest = result["controller_bridge_sha256"]
    post = {**payload, "tool_response": json.dumps(result)}
    output = json.loads(codex_adapter.audit_hook(tmp_path, "PostToolUse", post, lifecycle.MANAGED_HOOK_ABI))
    specific = output["hookSpecificOutput"]
    assert specific["hookEventName"] == "PostToolUse"
    assert "updatedInput" not in specific
    assert "permissionDecision" not in specific
    token = re.search(r"--hook-attestation (v2\.[0-9a-f]{64}\.[A-Za-z0-9_-]{16,128})", specific["additionalContext"]).group(1)

    monkeypatch.setattr(lifecycle, "managed_executable_health", lambda: {"canonical_executable_available": "YES"})
    monkeypatch.setattr(codex_adapter, "selected_continuation_mode", lambda _root: "BLOCKING_WAIT")
    monkeypatch.setattr(codex_adapter, "native_child_completion_reenters_root", lambda: "UNSUPPORTED")
    monkeypatch.setattr(codex_adapter, "host_explicit_blocking_wait", lambda: {"status": "PASS"})
    started = codex_adapter.task_start(tmp_path, "goal", None, None, token, digest)
    assert started["status"] == "ACTIVE"
    with pytest.raises(ValueError, match="MANAGED_CURRENT_SESSION_NOT_ATTESTED"):
        lifecycle.consume_task_start_attestation(tmp_path, token, digest)


def test_posttool_init_proof_rejects_unbound_or_failed_callbacks(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    codex_adapter.init(tmp_path)
    base = {
        "session_id": "controller-session",
        "turn_id": "turn",
        "cwd": str(tmp_path),
        "tool_name": "Bash",
        "tool_input": {"command": f'thaliris --root "{tmp_path}" init'},
        "tool_response": '{"ok":true}',
    }
    wrong_cases = [
        {"session_id": ""},
        {"agent_id": "child", "agent_type": "thaliris-implementer"},
        {"tool_name": "functions.exec", "tool_input": {"code": "thaliris init"}},
        {"tool_input": {"command": "Get-Date"}, "tool_response": "thaliris init"},
        {"tool_input": {"command": "thaliris init; Get-Date"}},
        {"tool_input": {"command": f'thaliris --root "{tmp_path.parent}" init'}},
        {"tool_response": None},
        {"tool_response": {"exit_code": 1, "output": '{"ok":false}'}},
        {"tool_response": {"isError": True}},
    ]
    for changes in wrong_cases:
        assert codex_adapter.audit_hook(tmp_path, "PostToolUse", {**base, **changes}, lifecycle.MANAGED_HOOK_ABI) == ""
    assert codex_adapter.audit_hook(tmp_path, "PostToolUse", base, "thaliris-hook-abi-9") == ""
    assert codex_adapter.audit_hook(tmp_path, "UserPromptSubmit", base, lifecycle.MANAGED_HOOK_ABI) == ""
    assert lifecycle.handle_hook(tmp_path, "PostToolUse", base, lifecycle.MANAGED_HOOK_ABI, None) == ""


def test_same_session_activation_issues_command_independent_one_shot_proof(tmp_path: Path, monkeypatch) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    payload = {
        "session_id": "same-session",
        "turn_id": "turn",
        "cwd": str(tmp_path),
        "tool_name": "Bash",
        # The Host emits the inner Bash call; its text is unrelated to task-start.
        "tool_input": {"command": "Get-Date"},
    }
    codex_adapter.audit_hook(tmp_path, "SessionStart", {
        "session_id": "same-session", "source": "startup", "cwd": str(tmp_path),
    })
    assert codex_adapter.audit_hook(tmp_path, "PreToolUse", payload, lifecycle.MANAGED_HOOK_ABI) == ""

    result = codex_adapter.init(tmp_path)
    digest = result["controller_bridge_sha256"]
    assert codex_adapter.audit_hook(tmp_path, "PreToolUse", payload, "thaliris-hook-abi-9") == ""
    output = json.loads(codex_adapter.audit_hook(tmp_path, "PreToolUse", payload, lifecycle.MANAGED_HOOK_ABI))
    specific = output["hookSpecificOutput"]
    assert specific["hookEventName"] == "PreToolUse"
    assert "updatedInput" not in specific
    assert "permissionDecision" not in specific
    token = re.search(r"--hook-attestation (v2\.[0-9a-f]{64}\.[A-Za-z0-9_-]{16,128})", specific["additionalContext"]).group(1)
    wrong_session_hash = hashlib.sha256(b"wrong-session").hexdigest()
    wrong_session_token = f"v2.{wrong_session_hash}.{token.rsplit('.', 1)[1]}"
    with pytest.raises(ValueError, match="MANAGED_CURRENT_SESSION_NOT_ATTESTED"):
        lifecycle.consume_task_start_attestation(tmp_path, wrong_session_token, digest)
    repeated = json.loads(codex_adapter.audit_hook(tmp_path, "PreToolUse", payload, lifecycle.MANAGED_HOOK_ABI))
    assert token in repeated["hookSpecificOutput"]["additionalContext"]
    record_path = lifecycle._start_attestation_path(tmp_path, token.split(".")[1])
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["expires_at_ns"] = 0
    record_path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ValueError, match="MANAGED_CURRENT_SESSION_NOT_ATTESTED"):
        lifecycle.consume_task_start_attestation(tmp_path, token, digest)
    renewed = json.loads(codex_adapter.audit_hook(tmp_path, "PreToolUse", payload, lifecycle.MANAGED_HOOK_ABI))
    token = re.search(r"--hook-attestation (v2\.[0-9a-f]{64}\.[A-Za-z0-9_-]{16,128})", renewed["hookSpecificOutput"]["additionalContext"]).group(1)
    assert token != record["token"]

    monkeypatch.setattr(lifecycle, "managed_executable_health", lambda: {"canonical_executable_available": "YES"})
    monkeypatch.setattr(codex_adapter, "selected_continuation_mode", lambda _root: "BLOCKING_WAIT")
    monkeypatch.setattr(codex_adapter, "native_child_completion_reenters_root", lambda: "UNSUPPORTED")
    monkeypatch.setattr(codex_adapter, "host_explicit_blocking_wait", lambda: {"status": "PASS"})
    assert codex_adapter.task_start(tmp_path, "goal", None, None, token, "0" * 64)["status"] == "CONTROLLER_BRIDGE_REQUIRED"
    started = codex_adapter.task_start(tmp_path, "goal", None, None, token, digest)
    assert started["status"] == "ACTIVE"
    with pytest.raises(ValueError, match="MANAGED_CURRENT_SESSION_NOT_ATTESTED"):
        lifecycle.consume_task_start_attestation(tmp_path, token, digest)


@pytest.mark.parametrize(
    "changes",
    [
        {"agent_id": "child", "agent_type": "thaliris-implementer"},
        {"tool_name": "spawn_agent"},
        {"tool_name": "Bash", "tool_input": {"command": "Get-Date"}, "agent_type": "worker"},
    ],
)
def test_admission_proof_is_not_minted_for_child_or_non_controller_calls(
    tmp_path: Path, changes: dict[str, object],
) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    codex_adapter.init(tmp_path)
    payload: dict[str, object] = {
        "session_id": "controller-session",
        "turn_id": "turn",
        "cwd": str(tmp_path),
        "tool_name": "Bash",
        "tool_input": {"command": "Get-Date"},
    }
    payload.update(changes)
    codex_adapter.audit_hook(tmp_path, "SessionStart", {
        "session_id": "controller-session", "source": "startup", "cwd": str(tmp_path),
    })
    assert codex_adapter.audit_hook(tmp_path, "PreToolUse", payload, lifecycle.MANAGED_HOOK_ABI) == ""
