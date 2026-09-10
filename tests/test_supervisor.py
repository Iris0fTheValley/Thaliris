from __future__ import annotations

from pathlib import Path
import subprocess

from thaliris.codex_adapter import init, task_start
from thaliris.intent_audit import activation_status, claim_activation, handle_hook
from thaliris import supervisor


def _repo(path: Path) -> Path:
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    init(path)
    task_start(path, "event-driven child", None, None)
    return path


def _payload(session: str = "root-session", turn: str = "root-turn", **values: object) -> dict[str, object]:
    return {"session_id": session, "turn_id": turn, **values}


def _reserve(root: Path) -> None:
    assert handle_hook(root, "PreToolUse", _payload(
        tool_name="spawn_agent",
        tool_input={"fork_turns": "none", "agent_type": "worker"},
    )) == ""


def test_completion_event_is_persisted_and_claimed_once(tmp_path: Path):
    root = _repo(tmp_path / "complete")
    _reserve(root)
    pending = activation_status(root)
    assert pending and pending["state"] == "PENDING_START"
    assert handle_hook(root, "SubagentStart", _payload(agent_id="child", agent_type="worker", turn_id="child-turn"))
    running = activation_status(root)
    assert running and running["state"] == "RUNNING"
    handle_hook(root, "SubagentStop", _payload(agent_id="child", agent_type="worker", turn_id="child-turn"))
    ready = activation_status(root)
    assert ready and ready["state"] == "READY" and ready["event_kind"] == "completed"
    assert claim_activation(root, ready["activation_id"], ready["event_id"]) is True
    assert claim_activation(root, ready["activation_id"], ready["event_id"]) is False


def test_deadline_event_is_idempotent_and_does_not_need_model_polling(tmp_path: Path):
    root = _repo(tmp_path / "timeout")
    _reserve(root)
    pending = activation_status(root)
    assert pending and isinstance(pending["deadline_ns"], int)
    expired = supervisor.poll(root, now_ns=pending["deadline_ns"] + 1)
    assert expired and expired["state"] == "READY" and expired["event_kind"] == "timeout"
    event_id = expired["event_id"]
    assert supervisor.poll(root, now_ns=pending["deadline_ns"] + 2)["event_id"] == event_id


def test_supervisor_resumes_ready_event_once(tmp_path: Path):
    root = _repo(tmp_path / "resume")
    _reserve(root)
    handle_hook(root, "SubagentStart", _payload(agent_id="child", agent_type="worker", turn_id="child-turn"))
    handle_hook(root, "SubagentStop", _payload(agent_id="child", agent_type="worker", turn_id="child-turn"))
    calls: list[list[str]] = []

    def runner(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, "", "")

    result = supervisor.resume_once(root, "root-session", "continue from child event", runner=runner)
    assert result["status"] == "RESUMED"
    assert calls == [["codex", "exec", "resume", "root-session", "continue from child event"]]
    assert supervisor.resume_once(root, "root-session", "continue from child event", runner=runner)["status"] == "PENDING"
    assert len(calls) == 1


def test_native_completion_bridge_requires_exact_start_identity(tmp_path: Path):
    root = _repo(tmp_path / "identity")
    _reserve(root)
    handle_hook(root, "SubagentStart", _payload(agent_id="child", agent_type="worker", turn_id="child-turn"))
    assert supervisor.record_native_completion(
        root,
        session_id="root-session",
        agent_id="child",
        turn_id="wrong-turn",
        agent_type="worker",
    ) is False
    assert activation_status(root)["state"] == "RUNNING"
    assert supervisor.record_native_completion(
        root,
        session_id="root-session",
        agent_id="child",
        turn_id="child-turn",
        agent_type="worker",
    ) is True
    assert activation_status(root)["event_kind"] == "completed"
