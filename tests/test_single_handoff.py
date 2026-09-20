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


def test_session_start_points_to_root_navigation_without_injecting_map(tmp_path: Path, monkeypatch) -> None:
    root = repo(tmp_path)
    (root / ".agent-memory" / "promoted").mkdir(parents=True, exist_ok=True)
    for index in range(100):
        (root / ".agent-memory" / "promoted" / f"doc-{index}.md").write_bytes(
            core._entry(f"Doc {index}", f"PRIVATE_BODY_{index}", evidence="NONE")
        )
    target = root / ".agent-memory" / "model-tree" / "deep" / "target.md"
    target.parent.mkdir(parents=True)
    target.write_bytes(core._entry("Target", "DECISION_CHANGING_BODY", evidence="NONE"))
    (root / ".agent-memory" / "INDEX.md").write_bytes(core._entry(
        "Global map",
        "Implementation target: [Target](model-tree/deep/target.md)",
        evidence="NONE",
        kind="MEMORY",
    ))

    def no_recursive_scan(*args, **kwargs):
        raise AssertionError("SessionStart catalog must not recursively scan durable documents")

    monkeypatch.setattr(Path, "rglob", no_recursive_scan)
    output = json.loads(handle_hook(root, "SessionStart", hook_payload(source="resume")))
    context = output["hookSpecificOutput"]["additionalContext"]
    assert len(context.encode("utf-8")) < 1024
    assert ".agent-memory/INDEX.md" in context
    assert ".milestones/INDEX.md" in context
    assert "explicitly read the root navigation" in context
    assert "model-tree/deep/target.md" not in context
    assert "PRIVATE_BODY" not in context
    assert "DECISION_CHANGING_BODY" not in context

    # The global map supplies the exact path, so one explicit retrieval call
    # returns the selected document without intermediate catalog traversal.
    fetched = core.document_get(root, [".agent-memory/model-tree/deep/target.md"])
    assert len(fetched["documents"]) == 1
    assert "DECISION_CHANGING_BODY" in fetched["documents"][0]["body"]

    child_output = handle_hook(root, "SubagentStart", hook_payload(
        source="resume", agent_id="unmanaged-child", agent_type="worker",
    ))
    assert child_output == ""


def test_checked_in_managed_instructions_equal_generated_source() -> None:
    repository = Path(__file__).resolve().parents[1]
    text = (repository / "AGENTS.md").read_text(encoding="utf-8")
    start = text.index(codex_adapter.MANAGED_START)
    end = text.index(codex_adapter.MANAGED_END, start) + len(codex_adapter.MANAGED_END)
    checked_in = text[start:end] + "\n"
    assert checked_in == codex_adapter.MANAGED


def test_blocking_wait_is_normalized_only_with_a_managed_dependency(tmp_path: Path, monkeypatch) -> None:
    root = repo(tmp_path)
    core.task_start(root, "wait mechanics", None, None)
    monkeypatch.setattr(codex_adapter, "selected_continuation_mode", lambda _root: "BLOCKING_WAIT")
    monkeypatch.setattr(codex_adapter, "host_explicit_blocking_wait", lambda: {
        "status": "PASS",
        "effective_max_wait_timeout_ms": 120_000,
    })
    wait = hook_payload(tool_name="wait_agent", tool_input={"timeout_ms": 30_000})

    assert codex_adapter.audit_hook(root, "PreToolUse", wait) == ""

    spawn = hook_payload(
        tool_name="spawn_agent",
        tool_input={"fork_turns": "none", "agent_type": "worker", "message": "explicit task"},
    )
    assert handle_hook(root, "PreToolUse", spawn) == ""
    rewritten = json.loads(codex_adapter.audit_hook(root, "PreToolUse", wait))
    assert rewritten["hookSpecificOutput"]["updatedInput"]["timeout_ms"] == 120_000


def test_unavailable_effective_wait_maximum_preserves_legal_timeout(tmp_path: Path, monkeypatch) -> None:
    root = repo(tmp_path)
    core.task_start(root, "wait mechanics", None, None)
    monkeypatch.setattr(codex_adapter, "selected_continuation_mode", lambda _root: "BLOCKING_WAIT")
    monkeypatch.setattr(codex_adapter, "host_explicit_blocking_wait", lambda: {
        "status": "PASS", "release_hard_max_wait_timeout_ms": 3_600_000,
        "effective_max_wait_timeout_ms": "UNAVAILABLE",
    })
    spawn = hook_payload(tool_name="spawn_agent", tool_input={"fork_turns": "none", "agent_type": "worker", "message": "explicit task"})
    assert handle_hook(root, "PreToolUse", spawn) == ""
    wait = hook_payload(tool_name="wait_agent", tool_input={"timeout_ms": 30_000})
    assert codex_adapter.audit_hook(root, "PreToolUse", wait) == ""


def test_codex_01551_wait_capability_is_version_pinned(monkeypatch) -> None:
    class Version:
        returncode = 0
        stdout = "codex-cli 0.155.1\n"
        stderr = ""

    codex_adapter._host_wait_mode_cached.cache_clear()
    monkeypatch.setattr(codex_adapter.subprocess, "run", lambda *args, **kwargs: Version())
    capability = codex_adapter.host_explicit_blocking_wait("codex-0.155-test")
    assert capability == {
        "status": "PASS", "version": "0.155.1", "min_wait_timeout_ms": 10_000,
        "default_wait_timeout_ms": 30_000, "release_hard_max_wait_timeout_ms": 3_600_000,
        "effective_max_wait_timeout_ms": "UNAVAILABLE", "explicit_timeout_supported": True,
    }
    assert codex_adapter.native_child_completion_reenters_root("codex-0.155-test") == "UNSUPPORTED"
    codex_adapter._host_wait_mode_cached.cache_clear()


@pytest.mark.parametrize("version", ["0.153.4", "0.154.0"])
def test_historical_codex_wait_capabilities_remain_exactly_pinned(monkeypatch, version: str) -> None:
    class Version:
        returncode = 0
        stdout = f"codex-cli {version}\n"
        stderr = ""

    codex_adapter._host_wait_mode_cached.cache_clear()
    monkeypatch.setattr(codex_adapter.subprocess, "run", lambda *args, **kwargs: Version())
    capability = codex_adapter.host_explicit_blocking_wait("codex-pinned-test")
    assert capability["version"] == version
    assert capability["release_hard_max_wait_timeout_ms"] == 3_600_000
    assert capability["effective_max_wait_timeout_ms"] == "UNAVAILABLE"
    codex_adapter._host_wait_mode_cached.cache_clear()


def test_future_codex_wait_capability_is_conservative(monkeypatch) -> None:
    class Version:
        returncode = 0
        stdout = "codex-cli 0.155.2\n"
        stderr = ""

    codex_adapter._host_wait_mode_cached.cache_clear()
    monkeypatch.setattr(codex_adapter.subprocess, "run", lambda *args, **kwargs: Version())
    capability = codex_adapter.host_explicit_blocking_wait("codex-future-test")
    assert capability["status"] == "UNKNOWN"
    assert codex_adapter.selected_continuation_mode(Path("."), "codex-future-test") == "UNAVAILABLE"
    codex_adapter._host_wait_mode_cached.cache_clear()


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


def test_user_prompt_does_not_clear_pending_spawn_reservation(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.task_start(root, "causal reservation", None, None)
    spawn = hook_payload(tool_name="spawn_agent", tool_input={
        "fork_turns": "none", "agent_type": "worker", "message": "handoff",
    })
    assert handle_hook(root, "PreToolUse", spawn) == ""
    pending = lifecycle(root)["pending_authorized_spawn"]
    assert handle_hook(root, "UserPromptSubmit", hook_payload(prompt="new user input")) == ""
    assert lifecycle(root)["pending_authorized_spawn"] == pending


def test_active_controller_uses_only_the_mechanical_tool_allowlist(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.task_start(root, "mechanical guard", None, None)
    assert hook_spec()["hooks"]["PreToolUse"][0]["matcher"] == "*"

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
    denied = json.loads(handle_hook(root, "PreToolUse", hook_payload(
        tool_name="Bash", tool_input={"command": "context task-show"},
    )))
    assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert handle_hook(root, "PreToolUse", hook_payload(
        tool_name="Bash", tool_input={"command": "context task-get R1"},
    )) == ""
    denied = json.loads(handle_hook(root, "PreToolUse", hook_payload(
        tool_name="Bash", tool_input={"command": r"C:\untrusted\context.exe task-status"},
    )))
    assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"
    for command in (
        "context init",
        "context uninstall",
        "context rollback backup-id",
        "context task-start another-task",
        "context stale",
    ):
        denied = json.loads(handle_hook(root, "PreToolUse", hook_payload(
            tool_name="Bash", tool_input={"command": command},
        )))
        assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"
    for name in ("wait_agent", "list_agents", "interrupt_agent"):
        assert handle_hook(root, "PreToolUse", hook_payload(tool_name=name, tool_input={})) == ""
    for name in ("followup_task", "send_message", "send_input"):
        denied = json.loads(handle_hook(root, "PreToolUse", hook_payload(tool_name=name, tool_input={"target": "old-child"})))
        assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"

    assert handle_hook(root, "PreToolUse", hook_payload(
        tool_name="spawn_agent",
        tool_input={"fork_turns": "none", "agent_type": "worker", "message": "fresh handoff"},
    )) == ""


def test_session_start_does_not_inject_large_root_map_or_document_body(tmp_path: Path) -> None:
    root = repo(tmp_path)
    target = root / ".agent-memory" / "selected.md"
    target.write_bytes(core._entry("Selected", "PRIVATE_DOCUMENT_BODY", evidence="NONE"))
    route = "[Selected](selected.md)\n\n" + ("model-authored-routing-hint " * 160)
    index = root / ".agent-memory" / "INDEX.md"
    index.write_bytes(core._entry("Global map", route, evidence="NONE", kind="MEMORY"))
    assert core.DURABLE_INDEX_RECOMMENDED_BYTES < index.stat().st_size < core.DURABLE_INDEX_HARD_MAX_BYTES

    output = json.loads(handle_hook(root, "SessionStart", hook_payload(source="startup")))
    context = output["hookSpecificOutput"]["additionalContext"]
    assert ".agent-memory/INDEX.md" in context
    assert "model-authored-routing-hint" not in context
    assert "selected.md" not in context
    assert "PRIVATE_DOCUMENT_BODY" not in context


def test_task_start_recreates_missing_root_navigation_before_active(tmp_path: Path) -> None:
    root = repo(tmp_path)
    (root / ".agent-memory" / "INDEX.md").unlink()
    (root / ".milestones" / "INDEX.md").unlink()
    started = core.task_start(root, "establish navigation", None, None)
    assert started["status"] == "ACTIVE"
    assert (root / ".agent-memory" / "INDEX.md").is_file()
    assert (root / ".milestones" / "INDEX.md").is_file()


def test_task_status_does_not_reread_navigation_automatically(tmp_path: Path, monkeypatch) -> None:
    root = repo(tmp_path)
    calls: list[object] = []

    def fail_catalog(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("task status must not read durable navigation")

    monkeypatch.setattr(core, "catalog", fail_catalog)
    core.task_start(root, "no automatic navigation reread", None, None)
    core.task_status(root)
    assert calls == []


def test_no_task_is_transparent_to_ordinary_spawn(tmp_path: Path) -> None:
    root = repo(tmp_path)
    assert handle_hook(root, "PreToolUse", hook_payload(
        tool_name="spawn_agent",
        tool_input={"agent_type": "worker", "message": "ordinary Codex child"},
    )) == ""
    assert not (root / ".context" / "audit" / "lifecycle").exists()


@pytest.mark.parametrize("agent_type", ("thaliris-investigator", "worker"))
def test_execution_role_extra_context_reads_are_telemetry_only(tmp_path: Path, agent_type: str) -> None:
    root = repo(tmp_path)
    core.task_start(root, "deviation telemetry", None, None)
    spawn_start(root, "reader-3", agent_type)
    child_read = hook_payload(
        agent_id="reader-3",
        agent_type=agent_type,
        tool_name="Bash",
        tool_input={"command": "context task-show"},
    )
    assert handle_hook(root, "PreToolUse", child_read) == ""
    deviation = lifecycle(root)["protocol_deviations"][0]
    assert deviation["agent_id"] == "reader-3"
    assert deviation["agent_type"] == agent_type
    assert deviation["operation"] == "task-show"
    assert deviation["blocked"] is False

    assert "Protocol deviation" not in core.task_status(root)

    child_status = {**child_read, "tool_input": {"command": "context task-status"}}
    rewrite = json.loads(handle_hook(root, "PreToolUse", child_status))
    assert rewrite["hookSpecificOutput"]["permissionDecision"] == "allow"
    assert rewrite["hookSpecificOutput"]["updatedInput"]["command"].endswith("--suppress-protocol-notice")
    assert "Protocol deviation" not in cli._task_status(root, suppress_protocol_notice=True)
    assert "Protocol deviation" not in core.task_status(root)


def test_task_status_keeps_core_ledger_only_and_cli_consumes_one_shot_notice(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.task_start(root, "cli notice", None, None)
    spawn_start(root, "reader", "thaliris-reviewer")
    assert handle_hook(root, "PreToolUse", hook_payload(
        agent_id="reader", agent_type="thaliris-reviewer", tool_name="Bash",
        tool_input={"command": "context task-show"},
    )) == ""
    assert "Protocol deviation" not in core.task_status(root)
    assert "lifecycle" not in Path(core.__file__).read_text(encoding="utf-8")
    assert "Protocol deviation" not in cli._task_status(root, suppress_protocol_notice=True)
    assert "Protocol deviation" in cli._task_status(root, suppress_protocol_notice=False)
    assert "Protocol deviation" not in cli._task_status(root, suppress_protocol_notice=False)

@pytest.mark.parametrize(("agent_type", "expected_role"), (
    ("thaliris-reviewer", "reviewer"),
    ("thaliris-reasoning-specialist", "reasoning-specialist"),
    ("thaliris-curator", "curator"),
))
def test_selected_roles_receive_one_bounded_aggregate_deviation_notice(
    tmp_path: Path, agent_type: str, expected_role: str,
) -> None:
    root = repo(tmp_path)
    core.task_start(root, "role-aware telemetry", None, None)
    spawn_start(root, "reader-1", agent_type)
    for operation in ("catalog", "document-get", "artifact-get"):
        assert handle_hook(root, "PreToolUse", hook_payload(
            agent_id="reader-1",
            agent_type=agent_type,
            tool_name="Bash",
            tool_input={"command": f"context {operation} .agent-memory/INDEX.md"},
        )) == ""
    notice = cli._task_status(root, suppress_protocol_notice=False)["Protocol deviation"]
    assert "Protocol deviations (batched)" in notice
    assert f"{expected_role}=3" in notice
    assert ".agent-memory/INDEX.md" in notice
    assert len(notice.encode("utf-8")) < 1024
    assert "Protocol deviation" not in cli._task_status(root, suppress_protocol_notice=False)


def test_selected_role_records_actual_context_and_obvious_shell_durable_targets(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.task_start(root, "actual durable targets", None, None)
    spawn_start(root, "reviewer-reader", "thaliris-reviewer")
    assert handle_hook(root, "PreToolUse", hook_payload(
        agent_id="reviewer-reader",
        agent_type="thaliris-reviewer",
        tool_name="Bash",
        tool_input={"command": "context document-get .agent-memory/a.md .milestones/b.md"},
    )) == ""
    assert handle_hook(root, "PreToolUse", hook_payload(
        agent_id="reviewer-reader",
        agent_type="thaliris-reviewer",
        tool_name="Bash",
        tool_input={"command": "cat .agent-memory/reviews/old-review.md"},
    )) == ""
    state = lifecycle(root)
    targets = [item["target"] for item in state["protocol_deviations"]]
    assert targets == [
        ".agent-memory/a.md",
        ".milestones/b.md",
        ".agent-memory/reviews/old-review.md",
    ]
    notice = cli._task_status(root, suppress_protocol_notice=False)["Protocol deviation"]
    assert "reviewer=3" in notice
    assert ".agent-memory/a.md" in notice
    assert ".milestones/b.md" in notice
    assert ".agent-memory/reviews/old-review.md" in notice
    assert len(notice.encode("utf-8")) < 1024
    assert "Protocol deviation" not in cli._task_status(root, suppress_protocol_notice=False)


def test_investigator_obvious_shell_durable_read_is_telemetry_only(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.task_start(root, "investigator durable read", None, None)
    spawn_start(root, "investigator-reader", "thaliris-investigator")
    assert handle_hook(root, "PreToolUse", hook_payload(
        agent_id="investigator-reader",
        agent_type="thaliris-investigator",
        tool_name="Bash",
        tool_input={"command": "rg needle .milestones/current/INDEX.md"},
    )) == ""
    state = lifecycle(root)
    assert state["protocol_deviations"][-1]["target"] == ".milestones/current/INDEX.md"
    assert state["protocol_deviations"][-1]["notice_delivered"] is True
    assert "Protocol deviation" not in core.task_status(root)


def test_reviewer_non_bash_durable_path_read_is_aggregated(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.task_start(root, "reviewer durable read", None, None)
    spawn_start(root, "reviewer-reader", "thaliris-reviewer")
    assert handle_hook(root, "PreToolUse", hook_payload(
        agent_id="reviewer-reader",
        agent_type="thaliris-reviewer",
        tool_name="mcp__files__read",
        tool_input={"path": ".agent-memory/x.md"},
    )) == ""
    state = lifecycle(root)
    assert state["protocol_deviations"][-1]["target"] == ".agent-memory/x.md"
    assert state["protocol_deviations"][-1]["notice_delivered"] is False
    notice = cli._task_status(root, suppress_protocol_notice=False)["Protocol deviation"]
    assert "reviewer=1" in notice
    assert ".agent-memory/x.md" in notice


def test_investigator_non_bash_durable_path_read_is_telemetry_only(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.task_start(root, "investigator durable read", None, None)
    spawn_start(root, "investigator-reader", "thaliris-investigator")
    assert handle_hook(root, "PreToolUse", hook_payload(
        agent_id="investigator-reader",
        agent_type="thaliris-investigator",
        tool_name="mcp__files__read",
        tool_input={"path": ".milestones/x.md"},
    )) == ""
    state = lifecycle(root)
    assert state["protocol_deviations"][-1]["target"] == ".milestones/x.md"
    assert state["protocol_deviations"][-1]["notice_delivered"] is True
    assert "Protocol deviation" not in cli._task_status(root, suppress_protocol_notice=False)


def test_one_generic_read_call_deduplicates_durable_targets(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.task_start(root, "deduplicate durable read", None, None)
    spawn_start(root, "reviewer-reader", "thaliris-reviewer")
    assert handle_hook(root, "PreToolUse", hook_payload(
        agent_id="reviewer-reader",
        agent_type="thaliris-reviewer",
        tool_name="mcp__files__read",
        tool_input={"paths": [".agent-memory/x.md", ".agent-memory/x.md"]},
    )) == ""
    targets = [item["target"] for item in lifecycle(root)["protocol_deviations"]]
    assert targets == [".agent-memory/x.md"]


def test_protocol_deviation_ring_keeps_late_events_in_one_aggregate(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.task_start(root, "deviation overflow", None, None)
    spawn_start(root, "reader", "thaliris-reviewer")
    for index in range(40):
        assert handle_hook(root, "PreToolUse", hook_payload(
            agent_id="reader",
            agent_type="thaliris-reviewer",
            tool_name="Bash",
            tool_input={"command": f"context task-show --marker {index}"},
        )) == ""
    state = lifecycle(root)
    assert len(state["protocol_deviations"]) == 32
    assert state["protocol_deviation_overflow_count"] == 8
    assert state["protocol_deviation_counts"]["reviewer:allowed_read"] == 40
    notice = cli._task_status(root, suppress_protocol_notice=False)["Protocol deviation"]
    assert "reviewer=40" in notice
    assert "diagnostic ring overflow=8" in notice
    assert "Protocol deviation" not in cli._task_status(root, suppress_protocol_notice=False)


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


def test_non_bash_control_state_mutation_tools_are_blocked_but_reads_and_repo_writes_are_allowed(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.task_start(root, "non bash child guard", None, None)
    spawn_start(root, "worker-1")
    denied = json.loads(handle_hook(root, "PreToolUse", hook_payload(
        agent_id="worker-1",
        agent_type="worker",
        tool_name="mcp__files__write",
        tool_input={"path": ".context/state.json", "content": "changed"},
    )))
    assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert lifecycle(root)["protocol_deviations"][-1]["operation"] == "control-state-write"

    assert handle_hook(root, "PreToolUse", hook_payload(
        agent_id="worker-1",
        agent_type="worker",
        tool_name="mcp__files__read",
        tool_input={"path": ".context/state.json"},
    )) == ""
    assert lifecycle(root)["protocol_deviations"][-1]["blocked"] is False

    assert handle_hook(root, "PreToolUse", hook_payload(
        agent_id="worker-1",
        agent_type="worker",
        tool_name="mcp__files__write",
        tool_input={"path": "src/example.py", "content": "changed"},
    )) == ""


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


def test_native_spawn_failure_without_posttool_keeps_pending_reservation(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.task_start(root, "spawn failure recovery", None, None)
    failed_spawn = hook_payload(tool_name="spawn_agent", tool_input={
        "fork_turns": "none", "agent_type": "worker", "message": "failed handoff",
    })
    assert handle_hook(root, "PreToolUse", failed_spawn) == ""
    pending = lifecycle(root)["pending_authorized_spawn"]
    assert pending is not None

    # Codex 0.154 returns the native error without PostToolUse. The reservation
    # therefore remains until the Controller explicitly invokes recovery.
    assert lifecycle(root)["pending_authorized_spawn"] == pending


def test_pending_spawn_recovery_requires_exact_handoff_id(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.task_start(root, "wrong recovery id", None, None)
    spawn = hook_payload(tool_name="spawn_agent", tool_input={
        "fork_turns": "none", "agent_type": "worker", "message": "handoff",
    })
    assert handle_hook(root, "PreToolUse", spawn) == ""
    with pytest.raises(ValueError, match="does not match"):
        lifecycle_module.recover_pending_spawn(root, "handoff-" + "0" * 32)
    assert lifecycle(root)["pending_authorized_spawn"] is not None


def test_exact_pending_spawn_recovery_clears_reservation_and_allows_next_spawn(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.task_start(root, "exact recovery id", None, None)
    spawn = hook_payload(tool_name="spawn_agent", tool_input={
        "fork_turns": "none", "agent_type": "worker", "message": "handoff",
    })
    assert handle_hook(root, "PreToolUse", spawn) == ""
    handoff_id = lifecycle(root)["pending_authorized_spawn"]["handoff_id"]
    recovered = lifecycle_module.recover_pending_spawn(root, handoff_id)
    assert recovered["recovered"] is True
    state = lifecycle(root)
    assert state["pending_authorized_spawn"] is None
    assert state["spawn_recoveries"][-1]["handoff_id"] == handoff_id

    next_spawn = hook_payload(tool_name="spawn_agent", tool_input={
        "fork_turns": "none", "agent_type": "worker", "message": "next handoff",
    })
    assert handle_hook(root, "PreToolUse", next_spawn) == ""
    assert lifecycle(root)["pending_authorized_spawn"] is not None


def test_pending_spawn_recovery_rejects_handoff_already_bound_to_child(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.task_start(root, "bound recovery", None, None)
    spawn = hook_payload(tool_name="spawn_agent", tool_input={
        "fork_turns": "none", "agent_type": "worker", "message": "bound handoff",
    })
    assert handle_hook(root, "PreToolUse", spawn) == ""
    handoff_id = lifecycle(root)["pending_authorized_spawn"]["handoff_id"]
    assert handle_hook(root, "SubagentStart", hook_payload(agent_id="bound-child", agent_type="worker")) == ""
    with pytest.raises(ValueError, match="already bound"):
        lifecycle_module.recover_pending_spawn(root, handoff_id)
    assert lifecycle(root)["children"][-1]["managed"] is True


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
    assert stopped["native_terminal_status"] is None
    assert isinstance(stopped["started"], int) and isinstance(stopped["stopped"], int)


def test_stop_requires_explicit_native_completed_for_close(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.task_start(root, "native completion", None, None)
    spawn_start(root, "worker-1")
    stop(root, "worker-1")
    state = core.task_show(root)["state"]
    with pytest.raises(ValueError, match="matching native SubagentStart/Stop"):
        codex_adapter.task_close(root, state["revision"])

    reconcile(root, "worker-1", {"completed": "result"})
    assert codex_adapter.task_close(root, state["revision"])["status"] == "DONE"


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
        ({"completed": "result"}, False, False),
        ("interrupted", True, False),
        ({"errored": "boom"}, True, False),
        ("shutdown", True, False),
        ({"completed": "result"}, True, True),
    )
    for index, (latest_status, attest_stop, should_close) in enumerate(terminal_cases):
        root = tmp_path / str(index)
        root.mkdir()
        root = repo(root)
        core.task_start(root, "latest child", None, None)
        spawn_start(root, "child-a")
        stop(root, "child-a")
        reconcile(root, "child-a", {"completed": "result"})
        spawn_start(root, "child-b")
        if attest_stop:
            stop(root, "child-b")
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
