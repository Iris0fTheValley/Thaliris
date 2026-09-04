"""No-op hard gate for managed benchmark arms.

The probe uses a temporary git repository and the real Thaliris hook adapter.
It never touches a benchmark fixture and fails closed when any required native
protocol observation is absent.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path

from thaliris.core import init as context_init, task_start
from thaliris.intent_audit import handle_hook


def _payload(tool_name: str, tool_input: dict, *, agent_id: str | None = None) -> dict:
    value = {"session_id": "preflight-session", "turn_id": "preflight-turn", "tool_name": tool_name, "tool_input": tool_input}
    if agent_id is not None:
        value["agent_id"] = agent_id
    return value


def _decision(value: str) -> str:
    if not value:
        return "ALLOW"
    return str(json.loads(value)["hookSpecificOutput"]["permissionDecision"]).upper()


def run_preflight() -> dict:
    previous_audit_env = os.environ.pop("THALIRIS_INTENT_AUDIT_ACTIVE", None)
    with tempfile.TemporaryDirectory(prefix="thaliris-managed-preflight-") as name:
        root = Path(name)
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.email", "preflight@example.invalid"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.name", "Preflight"], cwd=root, check=True)
        context_init(root)
        task_start(root, "managed protocol preflight", None, None)
        root_investigation = _decision(handle_hook(root, "PreToolUse", _payload("functions.exec_command", {"cmd": "Get-Content README.md"})))
        root_mutation = _decision(handle_hook(root, "PreToolUse", _payload("file_change", {"changes": [{"path": "probe.txt", "kind": "update"}]})))
        child_investigation = _decision(handle_hook(root, "PreToolUse", _payload("functions.exec_command", {"cmd": "Get-Content README.md"}, agent_id="child")))
        child_mutation = _decision(handle_hook(root, "PreToolUse", _payload("file_change", {"changes": [{"path": "probe.txt", "kind": "update"}]}, agent_id="child")))
        rewrite = json.loads(handle_hook(root, "PreToolUse", _payload("collaborationspawn_agent", {"fork_turns": "all", "message": "preflight"})))
        post = handle_hook(root, "PostToolUse", _payload("collaborationspawn_agent", {"fork_turns": "none", "message": "preflight"}))
        checks = {
            "active_task": "PASS",
            "managed_agents_loaded": "PASS" if (root / "AGENTS.md").is_file() else "FAIL",
            "pretooluse_root_event": "PASS" if root_investigation == "DENY" else "FAIL",
            "root_harmless_investigation": "PASS" if root_investigation == "DENY" else "FAIL",
            "root_harmless_mutation": "PASS" if root_mutation == "DENY" else "FAIL",
            "fresh_child_dispatch": "PASS" if post == "" else "FAIL",
            "fork_turns_none": "PASS" if rewrite["hookSpecificOutput"].get("updatedInput", {}).get("fork_turns") == "none" else "FAIL",
            "child_investigation": "PASS" if child_investigation == "ALLOW" else "FAIL",
            "child_mutation": "PASS" if child_mutation == "ALLOW" else "FAIL",
            "posttooluse_dispatch_evidence": "PASS" if post == "" else "FAIL",
        }
        result = {"status": "PASS" if all(v == "PASS" for v in checks.values()) else "INFRA_INVALID", "checks": checks}
    if previous_audit_env is not None:
        os.environ["THALIRIS_INTENT_AUDIT_ACTIVE"] = previous_audit_env
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = run_preflight()
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
