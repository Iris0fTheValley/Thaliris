"""Read-only diagnostics for the runtime-neutral Thaliris Core."""
from __future__ import annotations

from pathlib import Path

from .core import entries, milestone_check, _load_state
from .models import ContextConfig

UNKNOWN = "UNKNOWN"


def report(root: Path) -> dict[str, object]:
    try:
        ContextConfig.load(root)
        config_state = "YES"
    except (OSError, ValueError):
        config_state = "NO"
    memory = root / ".agent-memory"
    milestones = root / ".milestones"
    memory_state = {"configured": "YES" if memory.is_dir() else "NO", "enabled": "YES" if memory.is_dir() else "NO", "structure": UNKNOWN}
    if memory.is_dir():
        try:
            entries(root)
            memory_state["structure"] = "YES"
        except (OSError, ValueError):
            memory_state["structure"] = "NO"
    milestone_state = {"configured": "YES" if milestones.is_dir() else "NO", "enabled": "YES" if milestones.is_dir() else "NO", "structure": "YES" if milestones.is_dir() and milestone_check(root)["ok"] else "NO"}
    task = {"present": "NO", "valid": "YES", "status": UNKNOWN, "revision": UNKNOWN}
    if (root / ".context" / "state.json").is_file():
        task["present"] = "YES"
        try:
            state = _load_state(root)
            task.update({"valid": "YES", "status": state["status"], "revision": state["revision"]})
        except (OSError, ValueError):
            task["valid"] = "NO"
    agents_state = "YES" if (root / "AGENTS.md").is_file() else "NO"
    task_state_valid = task["valid"] if task["present"] == "YES" else "YES"
    routing_ready = "YES" if all(value == "YES" for value in (config_state, task_state_valid)) else "NO"
    routing = {"command_executed": "YES", "configuration_valid": config_state, "managed_agents_present": agents_state, "task_state_valid": task_state_valid, "role_routing_ready": routing_ready}
    return {"ok": True, "context": {"config": config_state, "agents": agents_state, "memory": memory_state, "milestones": milestone_state, "task_state": task, "ready_for_routing": routing_ready, "routing": routing}}
