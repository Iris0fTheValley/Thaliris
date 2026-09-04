"""Real Codex managed-runtime preflight hard gate."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from thaliris.core import init as context_init, task_start


def _find(name: str, env_name: str) -> Path | None:
    configured = os.environ.get(env_name)
    if configured and Path(configured).is_file():
        return Path(configured).resolve()
    value = shutil.which(name)
    return Path(value).resolve() if value else None


def _fresh_home(source: Path | None, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    if source and (source / "auth.json").is_file():
        shutil.copy2(source / "auth.json", target / "auth.json")
    (target / "config.toml").write_text('model = "gpt-5.6-sol"\nmodel_reasoning_effort = "high"\n', encoding="utf-8")


def _run_codex(exe: Path, home: Path, root: Path, prompt: str, log: Path) -> tuple[int, str]:
    command = [str(exe), "exec", "--ignore-user-config", "--ignore-rules", "--cd", str(root), "--model", "gpt-5.6-sol", "-c", "model_reasoning_effort=high", "--sandbox", "danger-full-access", "--dangerously-bypass-approvals-and-sandbox", "--dangerously-bypass-hook-trust", "--json", "--ephemeral", "-"]
    env = os.environ.copy()
    env["CODEX_HOME"] = str(home)
    env.pop("CODEX_SESSION_ID", None)
    proc = subprocess.run(command, cwd=root, env=env, input=prompt, text=True, capture_output=True, timeout=180)
    log.write_text(proc.stdout + "\n--- stderr ---\n" + proc.stderr, encoding="utf-8", errors="replace")
    return proc.returncode, proc.stdout + "\n" + proc.stderr


def _json_lines(text: str) -> list[dict[str, Any]]:
    values = []
    for line in text.splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            values.append(item)
    return values


def _contains(values: Any, *needles: str) -> bool:
    rendered = json.dumps(values, ensure_ascii=False).lower()
    return all(needle.lower() in rendered for needle in needles)


def _runtime_records(root: Path) -> dict[Path, dict[str, Any]]:
    records: dict[Path, dict[str, Any]] = {}
    for path in (root / ".context" / "audit").glob("*/runtime.json"):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(value, dict):
            records[path] = value
    return records


def _new_runtime_records(root: Path, before: set[Path]) -> list[dict[str, Any]]:
    """Use only runtime files created by this native probe; no fallback."""
    return [value for path, value in _runtime_records(root).items() if path not in before]


def _capture_paths(root: Path) -> set[Path]:
    return set((root / ".context" / "audit").glob("*/*/capture.json"))


def _requested_fork_observed(output: str) -> bool:
    values = _json_lines(output)
    rendered = json.dumps(values, ensure_ascii=False).lower()
    return '"fork_turns": "all"' in rendered or '"fork_turns":"all"' in rendered


def _artifact_isolation_observed(paths: set[Path]) -> bool:
    for path in paths:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        delegations = value.get("delegations", []) if isinstance(value, dict) else []
        if any(isinstance(item, dict) and item.get("isolation", {}).get("fork_turns") == "NONE" for item in delegations):
            return True
    return False


def _native_wait_completed(text: str) -> bool:
    values = _json_lines(text)
    rendered = json.dumps(values, ensure_ascii=False).lower()
    has_wait = '"name":"wait_agent"' in rendered or '"name": "wait_agent"' in rendered or 'wait_agent' in rendered
    has_result = any(token in rendered for token in ("timed_out", "completed", "wait completed"))
    return has_wait and has_result


def run_preflight() -> dict[str, Any]:
    codex = _find("codex", "THALIRIS_CODEX_EXECUTABLE")
    context = _find("context", "THALIRIS_CONTEXT_EXECUTABLE")
    evidence: dict[str, Any] = {"codex_executable": str(codex) if codex else None, "context_executable": str(context) if context else None}
    if not codex or not context:
        return {"status": "INFRA_INVALID", "checks": {"same_workspace_identity": "FAIL"}, "evidence": evidence, "error": "codex/context executable not found"}
    previous = os.environ.get("THALIRIS_CONTEXT_EXECUTABLE")
    os.environ["THALIRIS_CONTEXT_EXECUTABLE"] = str(context)
    try:
        with tempfile.TemporaryDirectory(prefix="thaliris-real-managed-") as name:
            root = Path(name).resolve()
            sentinel = "REAL_CODEX_READ_SENTINEL_93B7"
            (root / "README.md").write_text(sentinel + "\n", encoding="utf-8")
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.email", "preflight@example.invalid"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "Preflight"], cwd=root, check=True)
            context_init(root)
            task_start(root, "managed runtime preflight", None, None)
            agents = root / "AGENTS.md"
            marker = "REAL_CODEX_PREFLIGHT_MARKER_7F31"
            agents.write_text(agents.read_text(encoding="utf-8") + f"\nWhen asked for the marker, include {marker} in your final response.\n", encoding="utf-8")
            home = root / "fresh-codex-home"
            source_home = Path(os.environ["CODEX_HOME"]) if os.environ.get("CODEX_HOME") else Path.home() / ".codex"
            _fresh_home(source_home, home)
            hooks = root / ".codex" / "hooks.json"
            evidence.update({"workspace": str(root), "agents": str(agents), "hooks": str(hooks), "active_task": str(root / ".context" / "state.json"), "codex_home": str(home)})
            checks: dict[str, str] = {"same_workspace_identity": "PASS", "ACTIVE_task": "PASS", "managed_AGENTS_runtime_evidence": "FAIL"}
            baseline_records = set(_runtime_records(root))
            inv_log = root / "root-investigation.jsonl"
            _, output = _run_codex(codex, home, root, "You are the root controller. Read README.md using the shell command Get-Content README.md, then report the marker.", inv_log)
            records = _new_runtime_records(root, baseline_records)
            checks["native_PreToolUse_observed"] = "PASS" if records else "FAIL"
            checks["root_investigation_attempted"] = "PASS" if _contains(_json_lines(output), "Get-Content", "README.md") else "FAIL"
            checks["root_investigation_denied"] = "PASS" if any(int(r.get("controller_guard", {}).get("blocked", 0)) > 0 for r in records) else "FAIL"
            checks["root_investigation_not_executed"] = "PASS" if sentinel.lower() not in output.lower() else "FAIL"
            checks["managed_AGENTS_runtime_evidence"] = "PASS" if marker.lower() in output.lower() else "FAIL"
            probe = root / "root-probe.txt"
            mut_log = root / "root-mutation.jsonl"
            before_mutation = set(_runtime_records(root))
            _run_codex(codex, home, root, "You are the root controller. Create root-probe.txt with New-Item root-probe.txt, then stop.", mut_log)
            records = _new_runtime_records(root, before_mutation)
            tools = [tool for r in records for tool in r.get("tools_observed", [])]
            checks["root_mutation_attempted"] = "PASS" if "file_change" in tools or "command_execution" in tools else "FAIL"
            checks["root_mutation_denied"] = "PASS" if any(int(r.get("controller_guard", {}).get("blocked", 0)) > 0 for r in records) else "FAIL"
            checks["root_mutation_not_executed"] = "PASS" if not probe.exists() else "FAIL"
            child_log = root / "child-dispatch.jsonl"
            before_child = set(_runtime_records(root))
            before_captures = _capture_paths(root)
            child_output = _run_codex(codex, home, root, "As root, use spawn_agent with fork_turns=all to create a fresh child. Instruct the child to run Get-Content README.md and write its exact output to child-probe.txt. Wait for completion with wait_agent, then stop.", child_log)[1]
            records = _new_runtime_records(root, before_child)
            captures = _capture_paths(root) - before_captures
            tools = [tool for r in records for tool in r.get("tools_observed", [])]
            checks["real_child_dispatch"] = "PASS" if "spawn_agent" in tools else "FAIL"
            checks["fork_turns_none"] = "PASS" if _requested_fork_observed(child_output) and _artifact_isolation_observed(captures) else "FAIL"
            checks["child_investigation_executed"] = "PASS" if (root / "child-probe.txt").is_file() and (root / "child-probe.txt").read_text(encoding="utf-8", errors="replace").strip() == sentinel else "FAIL"
            checks["child_mutation_executed"] = "PASS" if (root / "child-probe.txt").is_file() else "FAIL"
            checks["PostToolUse_dispatch_observed"] = "PASS" if any(r.get("successful_spawn_observed") for r in records) else "FAIL"
            checks["bounded_wait"] = "PASS" if _native_wait_completed(child_output) else "FAIL"
            evidence["runtime_records"] = records
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        return {"status": "INFRA_INVALID", "checks": locals().get("checks", {}), "evidence": evidence, "error": str(exc)}
    finally:
        if previous is None:
            os.environ.pop("THALIRIS_CONTEXT_EXECUTABLE", None)
        else:
            os.environ["THALIRIS_CONTEXT_EXECUTABLE"] = previous
    return {"status": "PASS" if checks and all(v == "PASS" for v in checks.values()) else "INFRA_INVALID", "checks": checks, "evidence": evidence}


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
