from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
import pytest

from thaliris import cli, codex_adapter, core
from thaliris.lifecycle import handle_hook, hook_spec
import thaliris.lifecycle as lifecycle_module


def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    codex_adapter.init(tmp_path)
    return tmp_path


def hook_payload(**values: object) -> dict[str, object]:
    return {"session_id": "controller-session", "turn_id": "controller-turn", **values}


def lifecycle(root: Path) -> dict[str, object]:
    path = next((root / ".context" / "audit" / "lifecycle").glob("*.json"))
    return json.loads(path.read_text(encoding="utf-8"))


def spawn_start(root: Path, agent_id: str, agent_type: str = "worker") -> None:
    assert handle_hook(root, "PreToolUse", hook_payload(
        tool_name="spawn_agent",
        tool_input={"fork_turns": "none", "agent_type": agent_type, "message": f"task for {agent_id}"},
    )) == ""
    assert handle_hook(root, "SubagentStart", hook_payload(agent_id=agent_id, agent_type=agent_type)) == ""


def stop(root: Path, agent_id: str, agent_type: str = "worker") -> None:
    assert handle_hook(root, "SubagentStop", hook_payload(agent_id=agent_id, agent_type=agent_type)) == ""


def reconcile(root: Path, agent_id: str, status: object) -> None:
    assert handle_hook(root, "PostToolUse", hook_payload(
        tool_name="list_agents",
        tool_response={"agents": [{"agent_name": agent_id, "agent_status": status}]},
    )) == ""


def test_subagent_start_binds_explicit_handoff_without_injecting_projection(tmp_path: Path) -> None:
    root = repo(tmp_path)
    start_input = root.parent / "task-input.json"
    start_input.write_text(json.dumps({
        "records": [
            {"id": "old-unknown", "kind": "unknown", "text": "OLD_UNKNOWN"},
            {"id": "old-decision", "kind": "decision", "text": "OLD_DECISION"},
        ],
    }), encoding="utf-8")
    started = core.task_start(root, "single handoff", None, str(start_input))
    artifact = root / "private.md"
    artifact.write_text("ARTIFACT_PRIVATE_SENTINEL", encoding="utf-8")
    registered = core.task_artifact(
        root,
        started["revision"],
        "private-notes",
        "private.md",
        "private investigation notes",
        producer_role="implementer",
    )

    handoff = "SELECTED_FACT HANDOFF_SENTINEL; artifact pointer: private-notes"
    spawn = hook_payload(
        tool_name="spawn_agent",
        tool_input={"fork_turns": "none", "agent_type": "worker", "message": handoff},
    )
    assert handle_hook(root, "PreToolUse", spawn) == ""
    start_output = handle_hook(
        root,
        "SubagentStart",
        hook_payload(agent_id="child-one", agent_type="worker"),
    )

    # The native spawn message is already delivered by Codex. The adapter
    # must not return a second task-specific context payload.
    assert start_output == ""
    record = lifecycle(root)["children"][0]
    assert record["handoff_bound"] is True
    assert record["task_revision"] == registered["revision"]
    assert record["payload_hash"] == hashlib.sha256(handoff.encode("utf-8")).hexdigest()
    serialized = json.dumps(record)
    for unselected in ("OLD_UNKNOWN", "OLD_DECISION", "ARTIFACT_PRIVATE_SENTINEL"):
        assert unselected not in serialized
    start_handlers = hook_spec()["hooks"]["SubagentStart"][0]["hooks"]
    assert all("additionalContextLimit" not in handler for handler in start_handlers)


def test_blocking_wait_is_normalized_only_with_a_managed_dependency(tmp_path: Path, monkeypatch) -> None:
    root = repo(tmp_path)
    core.task_start(root, "wait mechanics", None, None)
    monkeypatch.setattr(codex_adapter, "selected_continuation_mode", lambda _root: "BLOCKING_WAIT")
    monkeypatch.setattr(codex_adapter, "host_explicit_blocking_wait", lambda: {
        "status": "PASS",
        "max_wait_timeout_ms": 3_600_000,
    })
    wait = hook_payload(tool_name="wait_agent", tool_input={"timeout_ms": 30_000})

    assert codex_adapter.audit_hook(root, "PreToolUse", wait) == ""

    spawn = hook_payload(
        tool_name="spawn_agent",
        tool_input={"fork_turns": "none", "agent_type": "worker", "message": "explicit task"},
    )
    assert handle_hook(root, "PreToolUse", spawn) == ""
    rewritten = json.loads(codex_adapter.audit_hook(root, "PreToolUse", wait))
    assert rewritten["hookSpecificOutput"]["updatedInput"]["timeout_ms"] == 3_600_000


def test_production_hooks_record_hashes_without_model_audit_or_correction(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.task_start(root, "telemetry only", None, None)
    prompt = "ROOT_PRIVATE_PROMPT"
    handoff = "CHILD_PRIVATE_HANDOFF"

    assert handle_hook(root, "UserPromptSubmit", hook_payload(prompt=prompt)) == ""
    assert handle_hook(root, "PostToolUse", hook_payload(
        tool_name="spawn_agent",
        tool_input={"fork_turns": "none", "agent_type": "worker", "message": handoff},
        tool_response={"success": True},
    )) == ""
    assert handle_hook(root, "Stop", hook_payload()) == ""

    runtime_path = next((root / ".context" / "audit").glob("*/runtime.json"))
    runtime_text = runtime_path.read_text(encoding="utf-8")
    runtime = json.loads(runtime_text)
    assert prompt not in runtime_text and handoff not in runtime_text
    assert hashlib.sha256(prompt.encode("utf-8")).hexdigest() in runtime["root_prompt_hashes"]
    assert runtime["delegation_telemetry"][0]["payload_hash"] == hashlib.sha256(handoff.encode("utf-8")).hexdigest()

    source = Path(__import__("thaliris.lifecycle", fromlist=["x"]).__file__).read_text(encoding="utf-8")
    for removed in ("_invoke_fresh_auditor", "task_close_audit", "AUDITOR_INSTRUCTION"):
        assert removed not in source


def test_active_controller_uses_only_the_mechanical_tool_allowlist(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.task_start(root, "mechanical guard", None, None)

    for payload in (
        hook_payload(tool_name="Bash", tool_input={"command": "rg -n architecture src"}),
        hook_payload(tool_name="Bash", tool_input={"command": "pytest -q"}),
        hook_payload(tool_name="apply_patch", tool_input={}),
        hook_payload(tool_name="mcp__example__read", tool_input={}),
    ):
        denied = json.loads(handle_hook(root, "PreToolUse", payload))
        assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"

    assert handle_hook(root, "PreToolUse", hook_payload(
        tool_name="Bash", tool_input={"command": "context task-status"},
    )) == ""
    for name in ("wait_agent", "list_agents", "interrupt_agent"):
        assert handle_hook(root, "PreToolUse", hook_payload(tool_name=name, tool_input={})) == ""
    for name in ("followup_task", "send_message", "send_input"):
        denied = json.loads(handle_hook(root, "PreToolUse", hook_payload(tool_name=name, tool_input={"target": "old-child"})))
        assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"

    assert handle_hook(root, "PreToolUse", hook_payload(
        tool_name="spawn_agent",
        tool_input={"fork_turns": "none", "agent_type": "worker", "message": "fresh handoff"},
    )) == ""


def test_child_control_context_reads_are_allowed_recorded_and_notified_once(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.task_start(root, "deviation telemetry", None, None)
    spawn_start(root, "investigator-3", "thaliris-investigator")
    child_read = hook_payload(
        agent_id="investigator-3",
        agent_type="thaliris-investigator",
        tool_name="Bash",
        tool_input={"command": "context task-show"},
    )
    assert handle_hook(root, "PreToolUse", child_read) == ""
    deviation = lifecycle(root)["protocol_deviations"][0]
    assert deviation["agent_id"] == "investigator-3"
    assert deviation["agent_type"] == "thaliris-investigator"
    assert deviation["operation"] == "task-show"
    assert deviation["blocked"] is False

    first = core.task_status(root)
    assert "Child investigator-3 directly retrieved control context" in first["Protocol deviation"]
    assert "No control-state mutation occurred" in first["Protocol deviation"]
    assert "Protocol deviation" not in core.task_status(root)

    child_status = {**child_read, "tool_input": {"command": "context task-status"}}
    rewrite = json.loads(handle_hook(root, "PreToolUse", child_status))
    assert rewrite["hookSpecificOutput"]["permissionDecision"] == "allow"
    assert rewrite["hookSpecificOutput"]["updatedInput"]["command"].endswith("--suppress-protocol-notice")
    assert "Protocol deviation" not in core.task_status(root, include_protocol_notice=False)
    assert "context task-status" in core.task_status(root)["Protocol deviation"]


def test_child_control_state_mutation_is_blocked_and_recorded(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.task_start(root, "child guard", None, None)
    spawn_start(root, "worker-1")
    mutation = hook_payload(
        agent_id="worker-1",
        agent_type="worker",
        tool_name="Bash",
        tool_input={"command": "context task-update --role controller --base-revision 1 --input update.json"},
    )
    denied = json.loads(handle_hook(root, "PreToolUse", mutation))
    assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"
    deviation = lifecycle(root)["protocol_deviations"][0]
    assert deviation["operation"] == "task-update"
    assert deviation["target"] == "context task-update"
    assert deviation["blocked"] is True

    direct_write = hook_payload(
        agent_id="worker-1",
        agent_type="worker",
        tool_name="Bash",
        tool_input={"command": "Set-Content .context/state.json '{}'"},
    )
    denied = json.loads(handle_hook(root, "PreToolUse", direct_write))
    assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert lifecycle(root)["protocol_deviations"][-1]["operation"] == "control-state-write"


def test_reviewer_profile_makes_no_native_sandbox_claim_and_obvious_writes_are_blocked(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.task_start(root, "review guard", None, None)
    spawn_start(root, "reviewer-1", "thaliris-reviewer")
    denied = json.loads(handle_hook(root, "PreToolUse", hook_payload(
        agent_id="reviewer-1",
        agent_type="thaliris-reviewer",
        tool_name="apply_patch",
        tool_input={"patch": "*** Begin Patch\n*** Update File: src/a.py\n*** End Patch"},
    )))
    assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"
    profile = codex_adapter._agent_profile("thaliris-reviewer", "reviewer", "gpt-5.6-terra", "high").decode()
    assert "sandbox_mode" not in profile


def test_task_start_requires_current_one_shot_hook_attestation(tmp_path: Path, monkeypatch, capsys) -> None:
    root = repo(tmp_path)
    monkeypatch.setattr(codex_adapter, "selected_continuation_mode", lambda _root: "BLOCKING_WAIT")
    monkeypatch.setattr(codex_adapter, "native_child_completion_reenters_root", lambda: "UNSUPPORTED")
    monkeypatch.setattr(codex_adapter, "host_explicit_blocking_wait", lambda: {"status": "PASS"})

    with pytest.raises(ValueError, match="MANAGED_CURRENT_SESSION_NOT_ATTESTED"):
        codex_adapter.task_start(root, "missing attestation", None, None)

    pre = hook_payload(tool_name="Bash", tool_input={"command": "context task-start goal"})
    rewritten = json.loads(codex_adapter.audit_hook(root, "PreToolUse", pre))
    command = rewritten["hookSpecificOutput"]["updatedInput"]["command"]
    token = re.search(r"--hook-attestation ([A-Za-z0-9._-]+)$", command).group(1)
    assert cli.main(["--root", str(root), "task-start", "attested", "--hook-attestation", token]) == 0
    started = json.loads(capsys.readouterr().out)
    assert started["status"] == "ACTIVE"
    with pytest.raises(ValueError, match="MANAGED_CURRENT_SESSION_NOT_ATTESTED"):
        codex_adapter.task_start(root, "reused", None, None, token)


def test_invalid_task_state_fails_closed_for_managed_root_control(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.task_start(root, "invalid state", None, None)
    (root / ".context" / "state.json").write_text("{broken", encoding="utf-8")
    assert lifecycle_module.managed_task_state(root) == ("INVALID_STATE", None)
    diagnostic = codex_adapter.doctor(root)
    assert diagnostic["managed_task_state"] == "INVALID_STATE"
    assert diagnostic["host_capability"]["reviewer_native_readonly_observed"] != "PASS"

    for payload in (
        hook_payload(tool_name="spawn_agent", tool_input={"fork_turns": "none", "agent_type": "worker", "message": "work"}),
        hook_payload(tool_name="list_agents", tool_input={}),
        hook_payload(tool_name="Bash", tool_input={"command": "context task-close --base-revision 1"}),
    ):
        denied = json.loads(handle_hook(root, "PreToolUse", payload))
        assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "INVALID_STATE" in denied["hookSpecificOutput"]["permissionDecisionReason"]
    assert handle_hook(root, "PreToolUse", hook_payload(
        tool_name="Bash", tool_input={"command": "context doctor"},
    )) == ""


def test_role_profiles_define_distilled_results_without_semantic_workflow(tmp_path: Path) -> None:
    del tmp_path
    for name, (model, effort, role) in codex_adapter._AGENT_PROFILES.items():
        profile = codex_adapter._agent_profile(name.removesuffix(".toml"), role, model, effort).decode()
        assert "sole task-specific input" in profile
        assert "distilled result" in profile
        assert "sandbox_mode" not in profile
        for removed in ("context prepare --role", "REVALIDATION_REQUIRED", "MECHANICAL or LOCAL_SEMANTIC"):
            assert removed not in profile
    assert "sole task-specific semantic router" in codex_adapter.MANAGED
    assert "never calls Core" in codex_adapter.MANAGED


def test_authorized_spawn_requires_fresh_explicit_serial_handoff(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.task_start(root, "spawn contract", None, None)

    for tool_input in (
        {"fork_turns": "all", "agent_type": "worker", "message": "task"},
        {"fork_turns": "none", "agent_type": "worker", "message": ""},
        {"fork_turns": "none", "agent_type": "unknown-role", "message": "task"},
    ):
        denied = json.loads(handle_hook(root, "PreToolUse", hook_payload(tool_name="spawn_agent", tool_input=tool_input)))
        assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"

    valid = hook_payload(tool_name="spawn_agent", tool_input={
        "fork_turns": "none", "agent_type": "worker", "message": "first task",
    })
    assert handle_hook(root, "PreToolUse", valid) == ""
    duplicate = json.loads(handle_hook(root, "PreToolUse", hook_payload(tool_name="spawn_agent", tool_input={
        "fork_turns": "none", "agent_type": "worker", "message": "second task",
    })))
    assert duplicate["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_explicit_spawn_failure_atomically_releases_matching_reservation(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.task_start(root, "spawn failure", None, None)
    failed_spawn = hook_payload(tool_name="spawn_agent", tool_input={
        "fork_turns": "none", "agent_type": "worker", "message": "failed handoff",
    })
    assert handle_hook(root, "PreToolUse", failed_spawn) == ""
    assert lifecycle(root)["pending_authorized_spawn"] is not None

    assert handle_hook(root, "PostToolUse", {
        **failed_spawn,
        "tool_response": {"status": "rejected", "error": "native spawn rejected"},
    }) == ""
    failed_state = lifecycle(root)
    assert failed_state["pending_authorized_spawn"] is None
    assert failed_state["spawn_failures"][-1]["dispatch_status"] == "REJECTED"

    next_spawn = hook_payload(tool_name="spawn_agent", tool_input={
        "fork_turns": "none", "agent_type": "worker", "message": "next handoff",
    })
    assert handle_hook(root, "PreToolUse", next_spawn) == ""
    assert lifecycle(root)["pending_authorized_spawn"] is not None


def test_unknown_spawn_result_does_not_release_reservation(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.task_start(root, "unknown spawn", None, None)
    spawn = hook_payload(tool_name="spawn_agent", tool_input={
        "fork_turns": "none", "agent_type": "worker", "message": "handoff",
    })
    assert handle_hook(root, "PreToolUse", spawn) == ""
    assert handle_hook(root, "PostToolUse", {**spawn, "tool_response": {"detail": "no outcome"}}) == ""
    assert lifecycle(root)["pending_authorized_spawn"] is not None


def test_lifecycle_binds_matching_identity_and_stop(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.task_start(root, "lifecycle", None, None)
    spawn = hook_payload(tool_name="spawn_agent", tool_input={
        "fork_turns": "none", "agent_type": "thaliris-reviewer", "message": "review this",
    })
    assert handle_hook(root, "PreToolUse", spawn) == ""

    # Wrong native role cannot consume the reservation.
    assert handle_hook(root, "SubagentStart", hook_payload(agent_id="wrong", agent_type="worker")) == ""
    state = lifecycle(root)
    assert state["children"][0]["managed"] is False
    assert state["pending_authorized_spawn"] is not None

    assert handle_hook(root, "SubagentStart", hook_payload(agent_id="reviewer-1", agent_type="thaliris-reviewer")) == ""
    running = lifecycle(root)["children"][-1]
    assert running["managed"] is True and running["terminal_state"] == "RUNNING"
    assert handle_hook(root, "SubagentStop", hook_payload(agent_id="other", agent_type="thaliris-reviewer")) == ""
    assert lifecycle(root)["children"][-1]["terminal_state"] == "RUNNING"
    assert handle_hook(root, "SubagentStop", hook_payload(agent_id="reviewer-1", agent_type="thaliris-reviewer")) == ""
    stopped = lifecycle(root)["children"][-1]
    assert stopped["terminal_state"] == "STOP_ATTESTED"
    assert isinstance(stopped["started"], int) and isinstance(stopped["stopped"], int)


def test_missing_stop_native_terminal_reconciliation_is_not_success(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.task_start(root, "reconcile", None, None)
    spawn = hook_payload(tool_name="spawn_agent", tool_input={
        "fork_turns": "none", "agent_type": "worker", "message": "implement",
    })
    assert handle_hook(root, "PreToolUse", spawn) == ""
    assert handle_hook(root, "SubagentStart", hook_payload(agent_id="worker-1", agent_type="worker")) == ""
    assert handle_hook(root, "PostToolUse", hook_payload(
        tool_name="list_agents",
        tool_response={"agents": [{"agent_name": "worker-1", "agent_status": {"completed": "result"}}]},
    )) == ""
    child = lifecycle(root)["children"][-1]
    assert child["terminal_state"] == "NATIVE_TERMINAL_RECONCILED"
    assert child["native_terminal_status"] == "completed"

    shown = core.task_show(root)["state"]
    try:
        codex_adapter.task_close(root, shown["revision"])
    except ValueError as exc:
        assert "matching native SubagentStart/Stop" in str(exc)
    else:
        raise AssertionError("native reconciliation incorrectly counted as successful result")


def test_selected_handoff_sentinel_exists_once_across_native_and_adapter_payload(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.task_start(root, "once", None, None)
    handoff = "SELECTED_FACT HANDOFF_SENTINEL"
    spawn = hook_payload(tool_name="spawn_agent", tool_input={
        "fork_turns": "none", "agent_type": "worker", "message": handoff,
    })
    assert handle_hook(root, "PreToolUse", spawn) == ""
    adapter_payload = handle_hook(root, "SubagentStart", hook_payload(agent_id="child", agent_type="worker"))
    assert (handoff + adapter_payload).count("HANDOFF_SENTINEL") == 1


def test_latest_managed_child_alone_controls_close(tmp_path: Path) -> None:
    terminal_cases = (
        ({"completed": "result"}, False),
        ("interrupted", False),
        ({"errored": "boom"}, False),
        ("shutdown", False),
        ("STOP_ATTESTED", True),
    )
    for index, (latest_status, should_close) in enumerate(terminal_cases):
        root = tmp_path / str(index)
        root.mkdir()
        root = repo(root)
        core.task_start(root, "latest child", None, None)
        spawn_start(root, "child-a")
        stop(root, "child-a")
        spawn_start(root, "child-b")
        if latest_status == "STOP_ATTESTED":
            stop(root, "child-b")
        else:
            reconcile(root, "child-b", latest_status)
        state = core.task_show(root)["state"]
        if should_close:
            assert codex_adapter.task_close(root, state["revision"])["status"] == "DONE"
        else:
            try:
                codex_adapter.task_close(root, state["revision"])
            except ValueError as exc:
                assert "matching native SubagentStart/Stop" in str(exc)
            else:
                raise AssertionError(f"latest child status {latest_status!r} was hidden by historical success")


def test_subagent_start_identity_collision_preserves_reservation(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.task_start(root, "collision", None, None)
    spawn_start(root, "reused-id")
    stop(root, "reused-id")
    assert handle_hook(root, "PreToolUse", hook_payload(
        tool_name="spawn_agent",
        tool_input={"fork_turns": "none", "agent_type": "worker", "message": "second handoff"},
    )) == ""

    assert handle_hook(root, "SubagentStart", hook_payload(agent_id="reused-id", agent_type="worker")) == ""
    state = lifecycle(root)
    assert state["pending_authorized_spawn"] is not None
    assert len([child for child in state["children"] if child.get("managed") is True]) == 1
    assert state["identity_collisions"][-1]["pending_handoff_id"] == state["pending_authorized_spawn"]["handoff_id"]


def test_only_current_lifecycle_schema_is_accepted(tmp_path: Path) -> None:
    root = repo(tmp_path)
    started = core.task_start(root, "current lifecycle", None, None)
    path = root / ".context" / "audit" / "lifecycle" / f"{lifecycle_module._task_key(started['task_id'])}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "version": lifecycle_module.LIFECYCLE_STATE_VERSION - 1,
        "task_id_hash": lifecycle_module._task_key(started["task_id"]),
        "children": [],
        "pending_authorized_spawn": None,
        "sequence": 0,
    }), encoding="utf-8")
    try:
        lifecycle_module._load_lifecycle(path, started["task_id"])
    except ValueError as exc:
        assert "invalid lifecycle runtime state" in str(exc)
    else:
        raise AssertionError("old lifecycle schema was accepted")


def test_no_historical_profile_hash_registry_remains() -> None:
    source = Path(codex_adapter.__file__).read_text(encoding="utf-8")
    assert "KNOWN_GENERATED" not in source
    assert "LEGACY_MANAGED" not in source
    assert not hasattr(codex_adapter, "migrate")
