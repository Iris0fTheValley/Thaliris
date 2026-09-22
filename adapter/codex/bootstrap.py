"""Project-external zero-state bootstrap for a Codex Git workspace.

This file intentionally has no Thaliris import.  It is usable before a
workspace has a project definition or an installed editable package.  The
host supplies either the canonical ``thaliris`` command or an executable path
and matching SHA-256 pin through environment variables.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def _repo_root(path: Path) -> Path:
    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, check=False,
    )
    if result.returncode:
        raise RuntimeError("not a Git workspace")
    return Path(result.stdout.strip()).resolve()


def _trusted_executable() -> list[str] | None:
    configured = os.environ.get("THALIRIS_EXECUTABLE") or os.environ.get("THALIRIS_CONTEXT_EXECUTABLE")
    expected = (os.environ.get("THALIRIS_EXECUTABLE_SHA256") or os.environ.get("THALIRIS_CONTEXT_EXECUTABLE_SHA256", "")).lower()
    if configured and expected:
        path = Path(configured).expanduser()
        if path.is_file() and len(expected) == 64:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest == expected:
                return [str(path.resolve())]
        return None
    # A bare canonical command is the only unpinned route; wrappers and
    # arbitrary PATH aliases are intentionally outside this entrypoint.
    if shutil.which("thaliris"):
        return ["thaliris"]
    return None


def _invoke(executable: list[str], root: Path, command: str) -> dict[str, object]:
    result = subprocess.run(
        [*executable, "--root", str(root), command],
        capture_output=True, text=True, check=False,
    )
    try:
        payload = json.loads(result.stdout)
    except (TypeError, json.JSONDecodeError):
        payload = {"ok": False, "error": "trusted executable returned non-JSON output", "stderr": result.stderr[-2000:]}
    if not isinstance(payload, dict):
        payload = {"ok": False, "error": "trusted executable returned a non-object JSON value"}
    payload["process_returncode"] = result.returncode
    return payload


def bootstrap(root: Path) -> dict[str, object]:
    workspace = _repo_root(root)
    executable = _trusted_executable()
    if executable is None:
        return {"ok": False, "status": "BOOTSTRAP_UNAVAILABLE", "manual_action_required": ["canonical_executable_unavailable"]}

    facts = _invoke(executable, workspace, "bootstrap-check")
    if facts.get("ok") is not True:
        return {"ok": False, "status": "BOOTSTRAP_UNAVAILABLE", "probe": facts}
    if facts.get("project_definition_present") == "YES":
        return {"ok": True, "status": "READY", "project_definition_present": "YES", "init_invoked": False}

    # Exactly one init attempt for this entrypoint invocation.  No durable
    # fence or retry state is created here; manual action is terminal.
    initialized = _invoke(executable, workspace, "init")
    manual = initialized.get("manual_action_required") or []
    if not isinstance(manual, list):
        manual = [manual]
    if initialized.get("project_definition_present") != "YES" or manual:
        return {
            "ok": False, "status": "MANUAL_ACTION_REQUIRED",
            "init_invoked": True, "manual_action_required": manual,
            "project_definition_present": initialized.get("project_definition_present", "UNKNOWN"),
        }
    if initialized.get("session_restart_required") is True:
        return {
            "ok": False, "status": "SESSION_RESTART_REQUIRED", "init_invoked": True,
            "session_restart_required": True,
            "message": "Stop this Controller session and start a fresh Codex session; do not task-start here.",
        }
    return {"ok": True, "status": "READY", "init_invoked": True}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Thaliris zero-state Codex bootstrap")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    try:
        result = bootstrap(args.root)
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        result = {"ok": False, "status": "BOOTSTRAP_UNAVAILABLE", "error": str(exc)}
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 3


if __name__ == "__main__":
    raise SystemExit(main())
