from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from thaliris.core import init, uninstall
import thaliris.intent_audit as audit_module
from thaliris.intent_audit import handle_hook, hooks_health


def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    return tmp_path


def payload(session: str = "session-1", turn: str = "turn-1", **values: object) -> dict[str, object]:
    return {"session_id": session, "turn_id": turn, **values}


def captures(root: Path) -> dict[str, object]:
    paths = list((root / ".context" / "audit").glob("*/*/capture.json"))
    assert len(paths) == 1
    return json.loads(paths[0].read_text(encoding="utf-8"))


def fake_runner(monkeypatch, result: dict[str, object]) -> None:
    monkeypatch.setattr(
        audit_module,
        "_invoke_fresh_auditor",
        lambda request, mode: (json.dumps(result), False),
    )


def test_root_prompt_and_child_prompt_are_not_mixed(tmp_path):
    root = repo(tmp_path)
    raw = "  用户原文\n保持空白  "
    assert handle_hook(root, "UserPromptSubmit", payload(prompt=raw)) == ""
    assert handle_hook(root, "UserPromptSubmit", payload(agent_id="child-1", prompt="child secret")) == ""
    state = captures(root)
    assert [item["text"] for item in state["prompts"]] == [raw]
    assert state["prompts"][0]["sha256"] == hashlib.sha256(raw.encode()).hexdigest()
    assert state["prompts"][0]["text_status"] == "AVAILABLE_UNVERIFIED"


def test_cli_hook_decodes_utf8_bytes_verbatim_and_ignores_child(tmp_path):
    root = repo(tmp_path)
    raw = "  中文输入\n保留空白  "
    command = [sys.executable, "-m", "thaliris.cli", "--root", str(root), "audit-hook", "UserPromptSubmit"]
    submitted = subprocess.run(
        command,
        input=json.dumps(payload(prompt=raw), ensure_ascii=False).encode("utf-8"),
        cwd=root,
        capture_output=True,
        check=False,
    )
    assert submitted.returncode == 0 and submitted.stdout == b"" and submitted.stderr == b""
    child = subprocess.run(
        command,
        input=json.dumps(payload(agent_id="child-1", prompt="child text"), ensure_ascii=False).encode("utf-8"),
        cwd=root,
        capture_output=True,
        check=False,
    )
    assert child.returncode == 0 and child.stdout == b"" and child.stderr == b""
    state = captures(root)
    assert [item["text"] for item in state["prompts"]] == [raw]
    assert state["prompts"][0]["sha256"] == hashlib.sha256(raw.encode("utf-8")).hexdigest()

    invalid = subprocess.run(command, input=b"\xff", cwd=root, capture_output=True, check=False)
    assert invalid.returncode == 0 and invalid.stdout == b"" and invalid.stderr == b""


def test_spawn_and_followup_instructions_are_captured_verbatim(tmp_path):
    root = repo(tmp_path)
    first = "  实现中文\n不要删除  "
    second = "follow up\n\nexact"
    handle_hook(root, "PostToolUse", payload(tool_name="spawn_agent", tool_input={"message": first, "task_name": "worker"}))
    handle_hook(root, "PostToolUse", payload(tool_name="followup_task", tool_input={"message": second, "target": "worker"}))
    state = captures(root)
    assert [item["text"] for item in state["delegations"]] == [first, second]
    assert state["delegations"][0]["sha256"] == hashlib.sha256(first.encode()).hexdigest()
    assert all(item["dispatch_status"] == "UNKNOWN" for item in state["delegations"])
    assert all("target" not in item and "task_name" not in item for item in state["delegations"])


def test_fifth_delegation_runs_checkpoint_and_pass_is_invisible(tmp_path, monkeypatch):
    root = repo(tmp_path)
    fake_runner(monkeypatch, {"status": "PASS", "findings": []})
    for index in range(4):
        assert handle_hook(root, "PostToolUse", payload(tool_name="spawn_agent", tool_input={"message": f"work {index}"}, tool_response={"isError": False})) == ""
    assert captures(root)["audit_runs"] == 0
    assert handle_hook(root, "PostToolUse", payload(tool_name="spawn_agent", tool_input={"message": "work 4"}, tool_response={"isError": False})) == ""
    state = captures(root)
    assert state["audit_runs"] == 1
    assert state["audit_attempts"] == 1
    assert state["audit"]["checkpoint_through"] == 5
    assert state["audit_results"] == [{"mode": "checkpoint", "attempt": 1, "status": "PASS", "findings": [], "fresh_verified": False}]


def test_drift_is_short_and_checkpoint_rejects_omission(tmp_path, monkeypatch):
    root = repo(tmp_path)
    omission = {"status": "DRIFT", "findings": [{"kind": "requirement_omission", "summary": "遗漏不得删除约束"}]}
    fake_runner(monkeypatch, omission)
    handle_hook(root, "UserPromptSubmit", payload(prompt="实现功能；不得删除用户文件"))
    outputs = []
    for _ in range(5):
        outputs.append(handle_hook(root, "PostToolUse", payload(tool_name="spawn_agent", tool_input={"message": "实现功能"})))
    assert outputs[-1] == ""  # incomplete checkpoints cannot claim omission

    # A fresh session final audit may make the complete omission judgment.
    final_root = repo(tmp_path / "final")
    handle_hook(final_root, "UserPromptSubmit", payload(session="s2", prompt="实现功能；不得删除用户文件"))
    handle_hook(final_root, "PostToolUse", payload(session="s2", tool_name="spawn_agent", tool_input={"message": "实现功能"}))
    output = handle_hook(final_root, "Stop", payload(session="s2", stop_hook_active=False))
    decoded = json.loads(output)
    assert decoded["decision"] == "block"
    assert "requirement_omission" in decoded["reason"]
    assert "不得删除用户文件" not in output
    assert captures(final_root)["audit_results"][0]["status"] == "DRIFT"


def test_stop_tail_is_one_shot_and_active_continuation_is_noop(tmp_path, monkeypatch):
    root = repo(tmp_path)
    drift = {"status": "DRIFT", "findings": [{"kind": "constraint_weakening", "summary": "worker instruction weakens a constraint"}]}
    fake_runner(monkeypatch, drift)
    handle_hook(root, "PostToolUse", payload(tool_name="spawn_agent", tool_input={"message": "work"}))
    assert handle_hook(root, "Stop", payload(stop_hook_active=True)) == ""
    first = handle_hook(root, "Stop", payload(stop_hook_active=False))
    assert json.loads(first)["decision"] == "block"
    assert handle_hook(root, "Stop", payload(stop_hook_active=False)) == ""
    assert handle_hook(root, "Stop", payload(stop_hook_active=True)) == ""
    assert captures(root)["audit_runs"] == 1


def test_two_turns_in_one_session_have_independent_final_audits(tmp_path, monkeypatch):
    root = repo(tmp_path)
    fake_runner(monkeypatch, {"status": "PASS", "findings": []})
    for turn in ("turn-a", "turn-b"):
        handle_hook(root, "UserPromptSubmit", payload(turn=turn, prompt=f"prompt {turn}"))
        handle_hook(root, "PostToolUse", payload(turn=turn, tool_name="spawn_agent", tool_input={"message": f"delegate {turn}"}))
        assert handle_hook(root, "Stop", payload(turn=turn, stop_hook_active=False)) == ""
        assert handle_hook(root, "Stop", payload(turn=turn, stop_hook_active=False)) == ""
    paths = sorted((root / ".context" / "audit").glob("*/*/capture.json"))
    assert len(paths) == 2
    states = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    assert sorted(state["prompts"][0]["text"] for state in states) == ["prompt turn-a", "prompt turn-b"]
    assert sorted(state["delegations"][0]["text"] for state in states) == ["delegate turn-a", "delegate turn-b"]
    assert all(state["audit_runs"] == 1 and state["audit_attempts"] == 1 for state in states)


def test_stop_continuation_is_ignored_once_then_real_prompt_is_captured(tmp_path, monkeypatch):
    root = repo(tmp_path)
    drift = {"status": "DRIFT", "findings": [{"kind": "scope_expansion", "summary": "delegation expands scope"}]}
    fake_runner(monkeypatch, drift)
    handle_hook(root, "UserPromptSubmit", payload(turn="turn-a", prompt="user request"))
    handle_hook(root, "PostToolUse", payload(turn="turn-a", tool_name="spawn_agent", tool_input={"message": "expanded work"}, tool_response={"success": True}))
    stopped = json.loads(handle_hook(root, "Stop", payload(turn="turn-a", stop_hook_active=False)))
    reason = stopped["reason"]
    assert handle_hook(root, "UserPromptSubmit", payload(turn="turn-real", prompt="real next request")) == ""
    assert handle_hook(root, "UserPromptSubmit", payload(turn="turn-continuation", prompt=reason)) == ""
    assert not list((root / ".context" / "audit").glob("*/" + hashlib.sha256(b"turn-continuation").hexdigest()[:24] + "/capture.json"))
    assert handle_hook(root, "UserPromptSubmit", payload(turn="turn-after-guard", prompt=reason)) == ""
    states = [json.loads(path.read_text(encoding="utf-8")) for path in (root / ".context" / "audit").glob("*/*/capture.json")]
    assert sorted(item["text"] for state in states for item in state["prompts"]) == sorted(["user request", "real next request", reason])


def test_session_start_clears_guard_only_for_startup_or_clear(tmp_path):
    from thaliris.intent_audit import _mark_expected_continuation

    root = repo(tmp_path)
    reason = "synthetic continuation"
    _mark_expected_continuation(root, payload(), reason)
    handle_hook(root, "SessionStart", payload(source="compact"))
    assert handle_hook(root, "UserPromptSubmit", payload(turn="compact-turn", prompt=reason)) == ""
    assert not list((root / ".context" / "audit").glob("*/" + hashlib.sha256(b"compact-turn").hexdigest()[:24] + "/capture.json"))

    _mark_expected_continuation(root, payload(), reason)
    handle_hook(root, "SessionStart", payload(source="startup"))
    handle_hook(root, "UserPromptSubmit", payload(turn="startup-turn", prompt=reason))
    assert any(path.name == "capture.json" for path in (root / ".context" / "audit").glob("*/*/capture.json"))


def test_dispatch_status_controls_capture_and_pass(tmp_path, monkeypatch):
    root = repo(tmp_path)
    requests = []
    def inspect_request(request, mode):
        requests.append(json.loads(request))
        return json.dumps({"status": "PASS", "findings": []}), False
    monkeypatch.setattr(audit_module, "_invoke_fresh_auditor", inspect_request)
    rejected = payload(tool_name="spawn_agent", tool_input={"message": "rejected body"}, tool_response={"isError": True, "error": "large private response"})
    assert handle_hook(root, "PostToolUse", rejected) == ""
    assert not list((root / ".context" / "audit").glob("*/*/capture.json"))
    for index in range(5):
        handle_hook(root, "PostToolUse", payload(tool_name="spawn_agent", tool_input={"message": f"accepted {index}", "target": "must-not-persist", "task_name": "also-private"}, tool_response={"status": "ok", "body": "must not persist"}))
    state = captures(root)
    assert all(item["dispatch_status"] == "ACCEPTED" for item in state["delegations"])
    assert "must not persist" not in json.dumps(state) and "must-not-persist" not in json.dumps(state) and "also-private" not in json.dumps(state)
    assert "target" not in json.dumps(requests) and "task_name" not in json.dumps(requests)
    assert state["audit_results"][-1]["status"] == "PASS"

    unknown_root = repo(tmp_path / "unknown-dispatch")
    for index in range(5):
        handle_hook(unknown_root, "PostToolUse", payload(tool_name="spawn_agent", tool_input={"message": f"unknown {index}"}))
    unknown = captures(unknown_root)
    assert unknown["audit_results"][-1]["status"] == "UNKNOWN"
    assert unknown["audit_results"][-1]["reason"] == "dispatch_unverified"


def test_capture_and_runner_failures_do_not_affect_core(tmp_path, monkeypatch):
    root = repo(tmp_path)
    init_result = init(root)
    assert init_result["ok"]
    audit = root / ".context" / "audit"
    if audit.exists():
        for child in audit.glob("**/*"):
            pass
    def crash(request, mode):
        raise OSError("runner failed")
    monkeypatch.setattr(audit_module, "_invoke_fresh_auditor", crash)
    for _ in range(5):
        assert handle_hook(root, "PostToolUse", payload(tool_name="spawn_agent", tool_input={"message": "work"})) == ""
    failed = captures(root)
    assert failed["audit"]["checkpoint_through"] == 5
    assert failed["audit_attempts"] == 1 and failed["audit_runs"] == 0
    assert failed["audit_results"][-1]["status"] == "UNKNOWN"
    assert failed["audit_results"][-1]["reason"] == "runner_unavailable_or_invalid"
    assert handle_hook(root, "PostToolUse", payload(tool_name="spawn_agent", tool_input={"message": "sixth"})) == ""
    assert captures(root)["audit_attempts"] == 1
    assert handle_hook(root, "Stop", payload()) == ""

    invalid_root = repo(tmp_path / "invalid")
    monkeypatch.setattr(audit_module, "_invoke_fresh_auditor", lambda request, mode: ("invalid", False))
    for _ in range(5):
        assert handle_hook(invalid_root, "PostToolUse", payload(tool_name="spawn_agent", tool_input={"message": "work"})) == ""
    assert captures(invalid_root)["audit"]["checkpoint_through"] == 5
    assert captures(invalid_root)["audit_attempts"] == 1

    missing_root = repo(tmp_path / "missing")
    monkeypatch.setattr(audit_module, "_invoke_fresh_auditor", lambda request, mode: None)
    for _ in range(5):
        assert handle_hook(missing_root, "PostToolUse", payload(tool_name="spawn_agent", tool_input={"message": "work"})) == ""
    assert captures(missing_root)["audit"]["checkpoint_through"] == 5
    assert captures(missing_root)["audit_attempts"] == 1
    # The normal deterministic workflow remains usable without audit files.
    import shutil
    shutil.rmtree(audit, ignore_errors=True)
    assert init(root)["ok"]


def test_hooks_merge_idempotent_uninstall_preserves_users_and_malformed_is_fail_open(tmp_path):
    root = repo(tmp_path)
    hooks = root / ".codex" / "hooks.json"
    hooks.parent.mkdir()
    user = {"unknown": {"keep": True}, "hooks": {"Stop": [{"matcher": "user", "hooks": [{"type": "command", "command": "user-hook"}]}]}}
    hooks.write_text(json.dumps(user), encoding="utf-8")
    first = init(root)
    assert first["ok"] and ".codex/hooks.json" in first["files"]
    installed = hooks.read_bytes()
    assert all(handler["timeout"] == 60 and "statusMessage" not in handler for entries in json.loads(installed)["hooks"].values() for entry in entries for handler in entry["hooks"] if handler["command"].startswith("context audit-hook"))
    second = init(root)
    assert second["ok"] and hooks.read_bytes() == installed
    removed = uninstall(root)
    assert removed["ok"]
    restored = json.loads(hooks.read_text(encoding="utf-8"))
    assert restored == user

    empty = repo(tmp_path / "empty")
    empty_hooks = empty / ".codex" / "hooks.json"
    empty_hooks.parent.mkdir()
    empty_hooks.write_text("{}\n", encoding="utf-8")
    assert init(empty)["ok"] and uninstall(empty)["ok"]
    assert empty_hooks.is_file() and isinstance(json.loads(empty_hooks.read_text(encoding="utf-8")), dict)

    managed = repo(tmp_path / "managed")
    assert init(managed)["ok"]
    managed_hooks = managed / ".codex" / "hooks.json"
    assert json.loads(managed_hooks.read_text(encoding="utf-8"))["description"] == audit_module.MANAGED_HOOKS_DESCRIPTION
    assert uninstall(managed)["ok"] and not managed_hooks.exists()

    near = repo(tmp_path / "near-match")
    near_hooks = near / ".codex" / "hooks.json"
    near_hooks.parent.mkdir()
    extras = [
        {"type": "command", "command": "context audit-hook Stop --extra", "timeout": 60},
        {"type": "command", "command": "context audit-hook UserPromptSubmit", "timeout": 60},
        {"type": "command", "command": "context audit-hook Stop", "timeout": 30},
    ]
    near_hooks.write_text(json.dumps({"hooks": {"Stop": [{"hooks": extras}]}}), encoding="utf-8")
    assert init(near)["ok"]
    installed_near = json.loads(near_hooks.read_text(encoding="utf-8"))
    assert any(handler == {"type": "command", "command": "context audit-hook Stop", "timeout": 60} for entry in installed_near["hooks"]["Stop"] for handler in entry["hooks"])
    assert uninstall(near)["ok"]
    remaining = json.loads(near_hooks.read_text(encoding="utf-8"))["hooks"]["Stop"][0]["hooks"]
    assert remaining == extras

    malformed = repo(tmp_path / "malformed")
    bad = malformed / ".codex" / "hooks.json"
    bad.parent.mkdir()
    bad.write_text("{bad", encoding="utf-8")
    result = init(malformed)
    assert result["ok"] and result["manual_migration_required"] == [".codex/hooks.json"]
    assert bad.read_text(encoding="utf-8") == "{bad"


def test_audit_is_ignored_and_absent_from_state_and_role_packs(tmp_path, capsys, monkeypatch):
    from thaliris.cli import main

    root = repo(tmp_path)
    assert init(root)["ok"]
    fake_runner(monkeypatch, {"status": "PASS", "findings": []})
    handle_hook(root, "UserPromptSubmit", payload(prompt="private audit input"))
    for index in range(5):
        handle_hook(root, "PostToolUse", payload(tool_name="spawn_agent", tool_input={"message": f"private delegation {index}"}, tool_response={"success": True}))
    assert captures(root)["audit_results"][-1]["status"] == "PASS"
    assert ".context/audit/" in (root / ".gitignore").read_text(encoding="utf-8")
    assert main(["--root", str(root), "task-start", "ordinary goal"]) == 0
    capsys.readouterr()
    state = (root / ".context" / "state.json").read_text(encoding="utf-8")
    assert "private audit input" not in state and "private delegation" not in state and "audit_results" not in state
    assert main(["--root", str(root), "prepare", "--role", "controller"]) == 0
    pack = capsys.readouterr().out
    assert "private audit input" not in pack and "private delegation" not in pack and "audit_results" not in pack and "intent_audit" not in pack
    health = hooks_health(root)
    assert health["hooks_configured"] == "YES"
    assert health["root_classification"] == "UNKNOWN"
