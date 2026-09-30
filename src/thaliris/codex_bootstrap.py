"""One-shot project-external bootstrap for a Codex Git workspace.

This module shares protocol constants with the lifecycle adapter.  It is
installed with the canonical ``thaliris`` command, so it remains available
before a workspace has a project definition and is independent of workspace
instruction files.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess

from . import core, lifecycle, runtime_identity, task_authority

EXPECTED_MANAGED_HOOK_ABI = lifecycle.MANAGED_HOOK_ABI
EXPECTED_ADAPTER_PROTOCOL_VERSION = lifecycle.CODEX_ADAPTER_PROTOCOL_VERSION


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
    """Resolve only the full Host-installed runtime identity."""
    home = lifecycle._host_home_path()
    manifest = home / runtime_identity.MANIFEST_NAME
    try:
        if manifest.is_symlink() or not manifest.is_file():
            return None
        contents = manifest.read_bytes()
        record = runtime_identity.validate_manifest_record(contents)
        executable = Path(str(record["executable"]))
        runtime_identity.validate_manifest(contents, executable, runtime_identity.manifest_identity(contents))
        return [str(executable)]
    except (OSError, ValueError, RuntimeError, TypeError):
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
    if command in {"bootstrap-check", "init"} and (
        payload.get("managed_hook_abi") != EXPECTED_MANAGED_HOOK_ABI
        or payload.get("executable_adapter_protocol_version") != EXPECTED_ADAPTER_PROTOCOL_VERSION
        or not _bridge_fields(payload)
    ):
        return {
            "ok": False,
            "status": "EXECUTABLE_PROTOCOL_SKEW",
            "error": "trusted executable does not expose the current hook ABI and Controller bridge protocol",
            "observed_managed_hook_abi": payload.get("managed_hook_abi"),
            "observed_adapter_protocol_version": payload.get("executable_adapter_protocol_version"),
            "session_restart_required": False,
        }
    if payload.get("session_restart_required") is True:
        return {
            "ok": False,
            "status": "EXECUTABLE_PROTOCOL_SKEW",
            "error": "trusted executable emitted an obsolete restart signal",
            "session_restart_required": False,
        }
    payload["session_restart_required"] = False
    payload["process_returncode"] = result.returncode
    return payload


def _restart_required(payload: dict[str, object]) -> bool:
    """The current bootstrap protocol has no restart prediction."""
    return False


def _bridge_fields(payload: dict[str, object]) -> dict[str, object]:
    """Expose one opaque receipt while keeping instruction bytes internal."""
    content = payload.get("controller_bridge_content")
    digest = payload.get("controller_bridge_sha256")
    if isinstance(content, str) and isinstance(digest, str) and hashlib.sha256(content.encode("utf-8")).hexdigest() == digest:
        return {"task_start_receipt": digest}
    return {}


def _definition_recovery_fields(payload: dict[str, object]) -> dict[str, object]:
    """Keep the exact managed-span recovery decision visible at bootstrap."""
    return {
        key: payload[key]
        for key in (
            "definition_recovery_status",
            "instruction_definition_present",
            "managed_instruction_state",
            "managed_instruction_sha256",
            "expected_managed_instruction_sha256",
            "managed_instruction_recovery_action",
        )
        if key in payload
    }


def _task_preflight(root: Path) -> dict[str, object]:
    """Read exact task evidence before any project initialization."""
    path = core._state_path(root)
    if path.is_symlink() or (path.exists() and not path.is_file()):
        return {"status": "INVALID_STATE"}
    if not path.exists():
        return {"status": "NO_TASK"}
    try:
        raw = path.read_bytes()
        if len(raw) > 512 * 1024:
            raise ValueError("task state exceeds 512 KiB")
        state = core._validate_state(root, json.loads(raw.decode("utf-8")))
        if state["status"] != "ACTIVE":
            return {"status": "NO_TASK"}
        task_id = str(state["task_id"])
        lifecycle_path = lifecycle._lifecycle_path(root, task_id)
        if lifecycle_path.is_symlink() or (lifecycle_path.exists() and not lifecycle_path.is_file()):
            raise ValueError("invalid lifecycle path")
        lifecycle_raw = lifecycle_path.read_bytes() if lifecycle_path.is_file() else None
        ledger = lifecycle._load_lifecycle(lifecycle_path, task_id)
        owner = ledger.get("owner_session_id_hash")
        provenance = "TASK_START" if owner is not None else "UNKNOWN"
        pending = ledger.get("pending_authorized_spawn")
        if owner is None and isinstance(pending, dict) and pending.get("depth") == 1 and pending.get("parent_role") == "controller":
            owner = pending.get("session_id_hash")
            provenance = "DEPTH_ONE_PENDING_RESERVATION"
        if owner is not None and (not isinstance(owner, str) or re.fullmatch(r"[0-9a-f]{64}", owner) is None):
            raise ValueError("invalid lifecycle Controller owner")
        return {
            "status": "ACTIVE",
            "task_id": task_id,
            "revision": state["revision"],
            "state_sha256": hashlib.sha256(raw).hexdigest(),
            "lifecycle_sha256": hashlib.sha256(lifecycle_raw).hexdigest() if lifecycle_raw is not None else "ABSENT",
            "owner_session_id_hash": owner or "UNKNOWN",
            "owner_provenance": provenance,
            "current_session_owner_match": "UNKNOWN",
        }
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
        return {"status": "INVALID_STATE"}


def _bootstrap(root: Path, hook_attestation: str | None = None) -> dict[str, object]:
    """Perform one bootstrap-check and, only when absent, one init attempt."""
    workspace = _repo_root(root)
    executable = _trusted_executable()
    if executable is None:
        manifest = lifecycle._host_home_path() / runtime_identity.MANIFEST_NAME
        diagnosis = (runtime_identity.diagnose_manifest(manifest.read_bytes())
                     if manifest.is_file() and not manifest.is_symlink() else
                     {"status": "UNKNOWN", "error": "canonical installed manifest is unavailable", "execution_assurance": "UNKNOWN"})
        return {
            "ok": False,
            "status": "BOOTSTRAP_UNAVAILABLE",
            "manual_action_required": ["canonical_executable_unavailable"],
            "session_restart_required": False,
            "runtime_drift": diagnosis,
            "ordinary_workspace_work_allowed": True,
        }

    task = _task_preflight(workspace)
    if task["status"] == "ACTIVE":
        anchor = task_authority.check(workspace)
        if anchor is not None:
            return {"ok": True, "status": "CURRENT_CONTINUATION", "recovery": task,
                    "task_authority": {"provenance": anchor["provenance"], "execution_mode": anchor["contract"]["execution_mode"]},
                    "init_invoked": False, "session_restart_required": False}
        session_hash = lifecycle.consume_bootstrap_observation(workspace, str(task["task_id"]), hook_attestation)
        owner = task["owner_session_id_hash"]
        if session_hash is not None and owner != "UNKNOWN":
            current = session_hash == owner
            task["current_session_owner_match"] = "YES" if current else "NO"
            status = "CURRENT_CONTINUATION" if current else "FOREIGN_RECOVERY_DECISION"
        else:
            status = "UNKNOWN"
        return {"ok": False, "status": status, "recovery": task, "init_invoked": False, "session_restart_required": False}
    if task["status"] == "INVALID_STATE":
        return {"ok": False, "status": "INVALID_STATE", "init_invoked": False, "session_restart_required": False}

    facts = _invoke(executable, workspace, "bootstrap-check")
    if facts.get("ok") is not True:
        return {
            "ok": False,
            "status": "BOOTSTRAP_UNAVAILABLE",
            "probe": facts,
            "session_restart_required": _restart_required(facts),
        }
    if facts.get("session_restart_required") is True:
        return {
            "ok": False,
            "status": "EXECUTABLE_PROTOCOL_SKEW",
            "init_invoked": False,
            "error": "trusted executable emitted an obsolete restart signal",
            "session_restart_required": False,
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
            **_definition_recovery_fields(facts),
        }
    if probe_definition == "YES":
        return {
            "ok": True,
            "status": "READY",
            "project_definition_present": "YES",
            "init_invoked": False,
            "session_restart_required": _restart_required(facts),
            **_bridge_fields(facts),
        }
    if probe_definition != "NO":
        return {
            "ok": False,
            "status": "BOOTSTRAP_UNAVAILABLE",
            "probe": facts,
            "session_restart_required": _restart_required(facts),
        }

    task = _task_preflight(workspace)
    if task["status"] != "NO_TASK":
        return {"ok": False, "status": task["status"], "recovery": task if task["status"] == "ACTIVE" else None, "init_invoked": False, "session_restart_required": False}

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
    if initialized.get("session_restart_required") is True:
        return {
            "ok": False,
            "status": "EXECUTABLE_PROTOCOL_SKEW",
            "init_invoked": True,
            "error": "trusted executable emitted an obsolete restart signal",
            "session_restart_required": False,
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
            **_definition_recovery_fields(initialized),
            **_bridge_fields(initialized),
        }
    if initialized.get("role_catalog_changed") is True:
        return {
            "ok": False,
            "status": "NEW_ROLE_CATALOG_IDENTITY_NOT_ACTIVE",
            "init_invoked": True,
            "new_role_profile_files": initialized.get("new_role_profile_files", []),
            "session_restart_required": False,
            **_bridge_fields(initialized),
        }
    return {
        "ok": True,
        "status": "READY",
        "init_invoked": True,
        "session_restart_required": False,
        **_bridge_fields(initialized),
    }


def bootstrap(root: Path, hook_attestation: str | None = None) -> dict[str, object]:
    result = _bootstrap(root, hook_attestation)
    assurance = lifecycle._controller_actor_assurance({})
    result.update(controller_actor_assurance=assurance, ordinary_workspace_work_allowed=True)
    if assurance != "CONTROLLER":
        result["managed_control_authority"] = "PERSISTENT_TASK_INTENT" if result.get("task_authority") else "EXPLICIT_CONTROLLER_ASSERTION_REQUIRED"
        if result.get("status") == "READY":
            result["status"] = "DEFINITION_READY_ACTOR_UNKNOWN"
        elif result.get("status") == "CURRENT_CONTINUATION" and not result.get("task_authority"):
            result["status"] = "UNKNOWN"
            result["session_owner_hash_match"] = "YES"
    return result


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
