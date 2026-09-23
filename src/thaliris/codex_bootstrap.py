"""One-shot project-external bootstrap for a Codex Git workspace.

This module intentionally depends only on the Python standard library.  It is
installed with the canonical ``thaliris`` command, so it remains available
before a workspace has a project definition and is independent of workspace
instruction files.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


def _repo_root(path: Path) -> Path:
    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode or not result.stdout.strip():
        raise RuntimeError("not a Git workspace")
    return Path(result.stdout.strip()).resolve()


def _trusted_executable() -> list[str] | None:
    configured = os.environ.get("THALIRIS_EXECUTABLE") or os.environ.get(
        "THALIRIS_CONTEXT_EXECUTABLE"
    )
    expected = (
        os.environ.get("THALIRIS_EXECUTABLE_SHA256")
        or os.environ.get("THALIRIS_CONTEXT_EXECUTABLE_SHA256", "")
    ).lower()
    if configured is not None or expected:
        # A configured route is trusted only when it is an absolute regular
        # executable file with an exact SHA-256 pin.  In particular, do not
        # silently fall back to PATH when the configured route is malformed.
        if not configured or not expected:
            return None
        path = Path(configured).expanduser()
        if (
            not path.is_absolute()
            or not path.is_file()
            or path.is_symlink()
            or not re.fullmatch(r"[0-9a-f]{64}", expected)
        ):
            return None
        try:
            resolved = path.resolve(strict=True)
            digest = hashlib.sha256(resolved.read_bytes()).hexdigest()
        except (OSError, RuntimeError):
            return None
        if digest != expected:
            return None
        return [str(resolved)]
    # The unpinned route is the canonical command resolved by PATH.  An
    # arbitrary configured alias or wrapper is never accepted as this route.
    if shutil.which("thaliris"):
        return ["thaliris"]
    return None


def _invoke(executable: list[str], root: Path, command: str) -> dict[str, object]:
    try:
        result = subprocess.run(
            [*executable, "--root", str(root), command],
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "ok": False,
            "error": str(exc),
            "session_restart_required": False,
        }
    try:
        payload = json.loads(result.stdout)
    except (TypeError, json.JSONDecodeError):
        return {
            "ok": False,
            "error": "trusted executable returned non-JSON output",
            "stderr": result.stderr[-2000:],
            "session_restart_required": False,
        }
    if not isinstance(payload, dict):
        return {
            "ok": False,
            "error": "trusted executable returned a non-object JSON value",
            "session_restart_required": False,
        }
    if result.returncode != 0:
        return {
            "ok": False,
            "error": "trusted executable returned a nonzero exit status",
            "process_returncode": result.returncode,
            "response": payload,
            # Preserve the native restart signal at this boundary as well as
            # retaining the complete native response for diagnostics.
            "session_restart_required": payload.get("session_restart_required") is True,
        }
    payload["session_restart_required"] = payload.get("session_restart_required") is True
    payload["process_returncode"] = result.returncode
    return payload


def _restart_required(payload: dict[str, object]) -> bool:
    """Normalize the native result's restart signal to an explicit boolean."""
    return payload.get("session_restart_required") is True


def bootstrap(root: Path) -> dict[str, object]:
    """Perform one bootstrap-check and, only when absent, one init attempt."""
    workspace = _repo_root(root)
    executable = _trusted_executable()
    if executable is None:
        return {
            "ok": False,
            "status": "BOOTSTRAP_UNAVAILABLE",
            "manual_action_required": ["canonical_executable_unavailable"],
            "session_restart_required": False,
        }

    facts = _invoke(executable, workspace, "bootstrap-check")
    if facts.get("ok") is not True:
        return {
            "ok": False,
            "status": "BOOTSTRAP_UNAVAILABLE",
            "probe": facts,
            "session_restart_required": _restart_required(facts),
        }
    probe_definition = facts.get("project_definition_present")
    probe_manual = facts.get("manual_action_required") or []
    if not isinstance(probe_manual, list):
        return {
            "ok": False,
            "status": "BOOTSTRAP_UNAVAILABLE",
            "probe": facts,
            "session_restart_required": _restart_required(facts),
        }
    if probe_manual:
        return {
            "ok": False,
            "status": "MANUAL_ACTION_REQUIRED",
            "init_invoked": False,
            "manual_action_required": probe_manual,
            "project_definition_present": probe_definition,
            "session_restart_required": _restart_required(facts),
        }
    if probe_definition == "YES":
        return {
            "ok": True,
            "status": "READY",
            "project_definition_present": "YES",
            "init_invoked": False,
            "session_restart_required": _restart_required(facts),
        }
    if probe_definition != "NO":
        return {
            "ok": False,
            "status": "BOOTSTRAP_UNAVAILABLE",
            "probe": facts,
            "session_restart_required": _restart_required(facts),
        }

    # Exactly one init attempt.  No durable fence, retry, or task-start is
    # performed by this boundary.
    initialized = _invoke(executable, workspace, "init")
    if initialized.get("ok") is not True:
        return {
            "ok": False,
            "status": "BOOTSTRAP_UNAVAILABLE",
            "init_invoked": True,
            "init": initialized,
            "session_restart_required": _restart_required(initialized),
        }
    manual = initialized.get("manual_action_required") or []
    if not isinstance(manual, list):
        manual = [manual]
    if initialized.get("project_definition_present") != "YES" or manual:
        restart_required = _restart_required(initialized)
        return {
            "ok": False,
            "status": "MANUAL_ACTION_REQUIRED",
            "init_invoked": True,
            "manual_action_required": manual,
            "project_definition_present": initialized.get(
                "project_definition_present", "UNKNOWN"
            ),
            "session_restart_required": restart_required,
        }
    if _restart_required(initialized):
        return {
            "ok": False,
            "status": "SESSION_RESTART_REQUIRED",
            "init_invoked": True,
            "session_restart_required": True,
            "message": "Stop this Controller session and start a fresh Codex session; do not task-start here.",
        }
    return {
        "ok": True,
        "status": "READY",
        "init_invoked": True,
        "session_restart_required": False,
    }


def main(argv: list[str] | None = None) -> int:
    """CLI helper retained for direct module use; canonical dispatch is cli.py."""
    import argparse

    class _Parser(argparse.ArgumentParser):
        # Keep direct entrypoint failures machine-readable like the canonical
        # dispatcher, including parse failures before args exists.
        def error(self, message: str) -> None:
            raise ValueError(message)

    parser = _Parser(description="Thaliris one-shot Codex bootstrap")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    try:
        args = parser.parse_args(argv)
        result = bootstrap(args.root)
    except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
        result = {
            "ok": False,
            "status": "BOOTSTRAP_UNAVAILABLE",
            "error": str(exc),
            "session_restart_required": False,
        }
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result.get("ok") else 3


if __name__ == "__main__":
    raise SystemExit(main())
