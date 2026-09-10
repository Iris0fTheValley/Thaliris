"""Small event/deadline bridge for resuming a suspended Controller.

This is intentionally not an agent runtime.  Codex still owns child execution;
the adapter only persists one task-local activation event and this supervisor
delivers that event once to the existing Codex resume primitive.  There is no
model-driven status polling here.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import time
from typing import Any, Callable

from . import intent_audit


def record_native_completion(
    root: Path,
    *,
    session_id: str,
    agent_id: str,
    turn_id: str,
    agent_type: str,
    failed: bool = False,
) -> bool:
    """Forward one runtime-observed completion through the exact hook contract."""
    return intent_audit.record_supervisor_completion(
        root,
        session_id=session_id,
        agent_id=agent_id,
        turn_id=turn_id,
        agent_type=agent_type,
        failed=failed,
    )


def poll(root: Path, *, now_ns: int | None = None) -> dict[str, Any] | None:
    """Return a ready completion/timeout event, converting expired work once."""
    intent_audit.activation_timeout(root, now_ns=now_ns)
    event = intent_audit.activation_status(root)
    if not isinstance(event, dict) or event.get("state") != "READY":
        return None
    return event


def resume_once(
    root: Path,
    session_id: str,
    prompt: str,
    *,
    executable: str | None = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> dict[str, Any]:
    """Resume one root activation after an observed event, exactly once."""
    event = poll(root)
    if event is None:
        return {"status": "PENDING"}
    activation_id = event.get("activation_id")
    event_id = event.get("event_id")
    if not isinstance(activation_id, str) or not isinstance(event_id, str):
        return {"status": "INVALID_EVENT"}
    command = executable or os.environ.get("THALIRIS_CODEX_EXECUTABLE") or "codex"
    argv = [command, "exec", "resume", session_id, prompt]
    invoke = runner or subprocess.run
    result = invoke(argv, cwd=root, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return {"status": "RESUME_FAILED", "event_id": event_id, "returncode": result.returncode}
    claimed = intent_audit.claim_activation(root, activation_id, event_id)
    return {"status": "RESUMED" if claimed else "ALREADY_CLAIMED", "event_id": event_id}


def run(
    root: Path,
    session_id: str,
    prompt: str,
    *,
    timeout_seconds: float = 1800.0,
    poll_interval_seconds: float = 0.25,
    executable: str | None = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Wait outside the model turn for one event, then resume the root once.

    The timeout is a supervisor deadline, not a model wake-up.  A native hook
    event normally makes ``poll`` return immediately; the short filesystem
    check only bridges Codex builds that do not expose a mailbox callback.
    """
    deadline = clock() + timeout_seconds
    while clock() < deadline:
        result = resume_once(root, session_id, prompt, executable=executable, runner=runner)
        if result.get("status") != "PENDING":
            return result
        sleeper(min(poll_interval_seconds, max(0.0, deadline - clock())))
    event = intent_audit.activation_timeout(root)
    if isinstance(event, dict) and event.get("state") == "READY":
        return resume_once(root, session_id, prompt, executable=executable, runner=runner)
    return {"status": "SUPERVISOR_TIMEOUT"}
