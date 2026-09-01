"""Read-only adapter and Codex configuration diagnostics."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tomllib

from .models import ContextConfig
from .core import LEGACY_MANAGED_END, LEGACY_MANAGED_START, MANAGED_END, MANAGED_START, entries, milestone_check, _load_state, _managed_span
from .intent_audit import hooks_health, is_managed_handler

UNKNOWN = "UNKNOWN"


def _runtime_hook_evidence(root: Path) -> tuple[bool, bool, bool]:
    """Read only private runtime markers emitted by the hook adapter."""
    pre = post = spawn = False
    for path in (root / ".context" / "audit").glob("*/runtime.json"):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(value, dict):
            continue
        events = value.get("events_observed")
        if isinstance(events, dict):
            pre = pre or events.get("PreToolUse") is True
            post = post or events.get("PostToolUse") is True
        tools = value.get("tools_observed")
        if isinstance(tools, list):
            spawn = spawn or "spawn_agent" in tools
    return pre, post, spawn


def _context_isolation(root: Path) -> dict[str, object]:
    """Report policy wiring separately from native runtime attestation.

    A repository hook proves that the policy is installed, not that the
    currently running Codex build honors PreToolUse or updatedInput.  Those
    runtime capabilities therefore remain UNKNOWN until a live native probe
    records them.  Configuration is reported only under ``configured``;
    ``observed`` never becomes YES merely because a hook file exists.
    """
    path = root / ".codex" / "hooks.json"
    policy = pre = post = "NO"
    try:
        value = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        hooks = value.get("hooks") if isinstance(value, dict) else None
        if isinstance(hooks, dict):
            for event, target in (("PreToolUse", "pre"), ("PostToolUse", "post")):
                entries = hooks.get(event)
                if not isinstance(entries, list):
                    continue
                managed = any(
                    isinstance(entry, dict)
                    and isinstance(entry.get("hooks"), list)
                    and any(is_managed_handler(item, event) for item in entry["hooks"])
                    for entry in entries
                )
                if managed:
                    if target == "pre":
                        pre = "YES"
                        policy = "YES"
                    else:
                        post = "YES"
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        policy = pre = post = UNKNOWN
    pre_observed, post_observed, spawn_observed = _runtime_hook_evidence(root)
    return {
        "configured": {
            "policy_present": policy,
            "pre_dispatch_hook": pre,
            "post_dispatch_hook": post,
        },
        "observed": {
            "pre_dispatch_hook_supported": "YES" if pre_observed else UNKNOWN,
            "spawn_payload_supported": "YES" if spawn_observed else UNKNOWN,
            "input_rewrite_supported": UNKNOWN,
            "pre_dispatch_enforcement": UNKNOWN,
            "post_dispatch_observation": "YES" if post_observed else UNKNOWN,
        },
    }


def _codex_config() -> tuple[dict[str, object], bool]:
    base = Path(os.environ["CODEX_HOME"]) if os.environ.get("CODEX_HOME") else Path.home() / ".codex"
    path = base / "config.toml"
    if not path.is_file(): return {}, False
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        return (data if isinstance(data, dict) else {}), True
    except (OSError, tomllib.TOMLDecodeError): return {}, False


def _states(configured: str = UNKNOWN, enabled: str = UNKNOWN) -> dict[str, str]:
    return {"configured": configured, "enabled": enabled}


def _version(command: str) -> str:
    executable = shutil.which(command)
    if not executable: return UNKNOWN
    try:
        output = subprocess.run([executable, "--version"], capture_output=True, text=True, timeout=2, check=False).stdout.strip()
        return output or UNKNOWN
    except (OSError, subprocess.SubprocessError): return UNKNOWN


def _adapter(name: str, expected: str, entry: object | None, project_enabled: bool | None, probe: bool) -> dict[str, str]:
    result = _states("YES" if entry is not None else "NO", "UNKNOWN" if project_enabled is None else ("YES" if project_enabled else "NO"))
    result["installed"] = "YES" if shutil.which(name) else "NO"
    result["version"] = _version(name) if probe else UNKNOWN
    result["expected_version"] = expected
    matches_expected = re.search(rf"(?<![0-9.]){re.escape(expected)}(?![0-9.])", result["version"]) is not None
    result["version_validated"] = "UNKNOWN" if result["version"] == UNKNOWN else ("YES" if matches_expected else "NO")
    return result


def report(root: Path) -> dict[str, object]:
    raw, codex_configured = _codex_config(); servers = raw.get("mcp_servers") if isinstance(raw, dict) else None
    lookup = lambda name: servers.get(name) if isinstance(servers, dict) else None
    try:
        project_config = ContextConfig.load(root); context_config = "YES"
        enabled = lambda name: project_config.adapters.get(name, False)
        probes = project_config.adapter_probes
    except ValueError:
        project_config = None; context_config = "NO"
        enabled = lambda name: None
        probes = False
    serena = _adapter("serena", "1.7.0", lookup("serena"), enabled("serena"), probes)
    cachebro = _adapter("cachebro", "0.2.2", lookup("cachebro"), enabled("cachebro"), probes)
    agentmemory = _adapter("agentmemory", "0.9.29", lookup("agentmemory"), enabled("agentmemory"), probes)
    serena["activation"] = "YES" if any((root / ".serena" / n).is_file() for n in ("project.yml", "project.yaml")) else "NO"
    cache_entry = lookup("cachebro")
    cachebro["cache"] = "YES" if isinstance(cache_entry, dict) and (cache_entry.get("cache") is True or isinstance(cache_entry.get("cache_path"), str)) else UNKNOWN
    agentmemory["automatic_injection"] = "UNKNOWN" if project_config is None else ("YES" if project_config.automatic_injection else "NO")
    agentmemory["automatic_compression"] = "UNKNOWN" if project_config is None else ("YES" if project_config.automatic_compression else "NO")
    model = raw.get("model", UNKNOWN) if isinstance(raw.get("model", UNKNOWN), str) else UNKNOWN
    reasoning = raw.get("model_reasoning_effort", UNKNOWN) if isinstance(raw.get("model_reasoning_effort", UNKNOWN), str) else UNKNOWN
    memory, milestones = (root / ".agent-memory").is_dir(), (root / ".milestones").is_dir()
    memory_state = _states("YES" if memory else "NO", "YES" if memory else "NO")
    milestone_state = _states("YES" if milestones else "NO", "YES" if milestones else "NO")
    if memory:
        try:
            entries(root)
            memory_state["structure"] = "YES"
        except (OSError, ValueError):
            memory_state["structure"] = "NO"
    else:
        memory_state["structure"] = "NO"
    if milestones:
        milestone_state["structure"] = "YES" if milestone_check(root)["ok"] else "NO"
    else:
        milestone_state["structure"] = "NO"
    agents = root / "AGENTS.md"
    if agents.is_file():
        try:
            agents_text = agents.read_text(encoding="utf-8")
            span = _managed_span(agents_text, MANAGED_START, MANAGED_END, LEGACY_MANAGED_START, LEGACY_MANAGED_END, "AGENTS.md")
            agents_state = "YES" if span is not None else "NO"
        except ValueError:
            agents_state = "NO"
        except OSError:
            agents_state = UNKNOWN
    else:
        agents_state = "NO"
    task = {"present": "NO", "valid": UNKNOWN, "status": UNKNOWN, "revision": UNKNOWN}
    if (root / ".context" / "state.json").is_file():
        task["present"] = "YES"
        try:
            current = _load_state(root)
            task.update({"valid": "YES", "status": current["status"], "revision": current["revision"]})
        except ValueError:
            task["valid"] = "NO"
        except OSError:
            pass
    task_state_valid = task["valid"] if task["present"] == "YES" else "YES"
    routing_ready = "YES" if all(value == "YES" for value in (context_config, agents_state, task_state_valid)) else "NO"
    routing = {
        "command_executed": "YES",
        "configuration_valid": context_config,
        "managed_agents_present": agents_state,
        "task_state_valid": task_state_valid,
        "role_routing_ready": routing_ready,
    }
    return {"ok": True, "codex": {"version": _version("codex"), "model_configured": model, "reasoning_configured": reasoning, "configured": "YES" if codex_configured else "NO"}, "subagents": {"status": UNKNOWN}, "adapters": {"serena": serena, "cachebro": cachebro, "agentmemory": agentmemory}, "intent_audit": hooks_health(root), "context_isolation": _context_isolation(root), "context": {"config": context_config, "agents": agents_state, "memory": memory_state, "milestones": milestone_state, "task_state": task, "ready_for_routing": routing_ready, "routing": routing}, "fallbacks": {"rg": "YES" if shutil.which("rg") else "NO", "git": "YES" if shutil.which("git") else "NO"}}
