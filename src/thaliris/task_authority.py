"""External task-intent provenance, under a shared-OS governance boundary.

An explicit Controller assertion records a selected human instruction. It is
not proof of human prompt authorship or of universal native Root identity.
"""
from __future__ import annotations

import hashlib
import base64
import json
import os
import uuid
from pathlib import Path

from . import core, runtime_identity

MODES = ("delegated", "controller-direct", "single-agent")
SECURITY_PATHS = (".context/config.json", ".codex/thaliris.json", ".codex/hooks.json", ".codex/config.toml")


def directory() -> Path:
    # Deliberately independent of CODEX_HOME and repository configuration.
    return Path.home() / ".thaliris" / "task-authority"


def path(root: Path) -> Path:
    location = directory()
    if location.resolve().is_relative_to(root.resolve()) or any(runtime_identity._is_link(item) for item in (location, *location.parents)):
        raise ValueError("TASK_AUTHORITY_EXTERNAL_LOCATION_UNSAFE")
    identity = str(root.resolve()).casefold() if os.name == "nt" else str(root.resolve())
    return location / (hashlib.sha256(identity.encode()).hexdigest() + ".json")


def digest(target: Path) -> str:
    if target.is_symlink() or target.exists() and not target.is_file():
        raise ValueError("TASK_AUTHORITY_UNSAFE_PATH")
    return hashlib.sha256(target.read_bytes()).hexdigest() if target.is_file() else "ABSENT"


def read(root: Path) -> dict | None:
    target = path(root)
    if digest(target) == "ABSENT":
        return None
    record = json.loads(target.read_text(encoding="utf-8"))
    if (not isinstance(record, dict) or record.get("version") != 1 or not isinstance(record.get("project"), str)
            or Path(record["project"]).resolve() != root.resolve()):
        raise ValueError("TASK_AUTHORITY_INVALID")
    return record


def write(root: Path, record: dict) -> None:
    core._atomic_write(path(root), (json.dumps(record, sort_keys=True, indent=2) + "\n").encode())


def contract(filename: str) -> dict:
    value = json.loads(Path(filename).read_text(encoding="utf-8"))
    required = {"human_instruction", "boundary", "invariants", "acceptance", "execution_mode"}
    if not isinstance(value, dict) or set(value) != required or value.get("execution_mode") not in MODES:
        raise ValueError("TASK_AUTHORITY_CONTRACT_REQUIRED")
    if any(not isinstance(value[key], str) or not value[key].strip() or len(value[key]) > 16384
           for key in required - {"execution_mode"}):
        raise ValueError("TASK_AUTHORITY_CONTRACT_REQUIRED")
    return value


def establish(root: Path, state: dict, intent: dict, session_hash: str) -> dict:
    prior = read(root)
    if prior is not None and prior["status"] == "ACTIVE":
        raise ValueError("TASK_AUTHORITY_ALREADY_ACTIVE")
    if prior is not None:
        core._atomic_write(directory() / "history" / f"{path(root).stem}-{prior['task_id']}.json", path(root).read_bytes())
    record = {"version": 1, "project": str(root.resolve()), "task_id": state["task_id"],
              "goal": state["goal"], "contract": intent, "status": "ACTIVE",
              "provenance": "CONTROLLER_ASSERTED_HUMAN_INSTRUCTION",
              "host_actor_assurance": "UNKNOWN", "origin_session_hash": session_hash,
              "state_sha256": digest(core._state_path(root)), "lifecycle_sha256": "ABSENT",
              "security": {name: digest(root / name) for name in SECURITY_PATHS},
              "fenced_sessions": prior.get("fenced_sessions", []) if prior else [],
              "fenced_agents": prior.get("fenced_agents", []) if prior else [],
              "history": prior.get("history", []) + [{"task_id": prior["task_id"], "goal": prior["goal"], "status": prior["status"], "contract": prior["contract"]}] if prior else []}
    record["snapshots"] = {name: base64.b64encode((root / name).read_bytes()).decode() if digest(root / name) != "ABSENT" else None
                           for name in (*SECURITY_PATHS, ".context/state.json")}
    write(root, record)
    return record


def check(root: Path) -> dict | None:
    record = read(root)
    if record is None:
        return None
    if record["status"] != "ACTIVE":
        if digest(core._state_path(root)) != record["state_sha256"]:
            raise ValueError("TASK_AUTHORITY_RETIRED_STATE_CHANGED")
        return None
    if digest(core._state_path(root)) != record["state_sha256"]:
        raise ValueError("TASK_AUTHORITY_STATE_CHANGED")
    if any(digest(root / name) != expected for name, expected in record["security"].items()):
        raise ValueError("TASK_AUTHORITY_SECURITY_CHANGED")
    # Read raw bytes here to avoid recursion through Core or lifecycle.
    state = json.loads(core._state_path(root).read_text(encoding="utf-8"))
    if state.get("task_id") != record["task_id"] or state.get("goal") != record["goal"] or state.get("status") != "ACTIVE":
        raise ValueError("TASK_AUTHORITY_IDENTITY_CHANGED")
    from . import lifecycle
    if digest(lifecycle._lifecycle_path(root, record["task_id"])) != record["lifecycle_sha256"]:
        raise ValueError("TASK_AUTHORITY_LIFECYCLE_CHANGED")
    return record


def checkpoint(root: Path) -> None:
    """Only trusted command closures call this after previously checked writes."""
    record = read(root)
    if record is None or record["status"] != "ACTIVE":
        return
    record["state_sha256"] = digest(core._state_path(root))
    record["snapshots"][".context/state.json"] = base64.b64encode(core._state_path(root).read_bytes()).decode() if record["state_sha256"] != "ABSENT" else None
    if record["state_sha256"] == "ABSENT":
        record["status"] = "ABANDONED"
    else:
        state = json.loads(core._state_path(root).read_text(encoding="utf-8"))
        if state["task_id"] != record["task_id"] or state["goal"] != record["goal"]:
            raise ValueError("TASK_AUTHORITY_IDENTITY_CHANGED")
        record["status"] = state["status"]
    write(root, record)


def capture(path_: Path, value: dict) -> None:
    """Update an external lifecycle/fence copy only for a checked adapter write."""
    if path_.parent.name == "lifecycle" and path_.parent.parent.name == "audit":
        root = path_.parents[3]
        record = read(root)
        if record is not None and record["status"] == "ACTIVE":
            from . import lifecycle
            if path_ != lifecycle._lifecycle_path(root, record["task_id"]):
                raise ValueError("TASK_AUTHORITY_LIFECYCLE_IDENTITY_CHANGED")
            record["lifecycle_sha256"] = digest(path_)
            record["lifecycle_snapshot"] = value
            write(root, record)
    elif path_.name in {"session-fence.json", "abandoned-child-fence.json"}:
        root = path_.parents[3] if path_.name == "session-fence.json" else path_.parents[2]
        record = read(root)
        if record is not None:
            if path_.name == "session-fence.json":
                record["fenced_sessions"] = sorted(set(record["fenced_sessions"]) | set(value.get("session_id_hashes", [])))
            else:
                record["fenced_agents"] = sorted(set(record["fenced_agents"]) | set(value.get("agent_id_hashes", [])) |
                    {item["agent_id_hash"] for item in value.get("children", [])})
            write(root, record)


def recover(root: Path, expected: str, reason: str) -> dict:
    """Restore the recorded authority, never bless current repository bytes.

    This continues the recorded authority without a new human grant. It can
    only restore the original baseline and add fences, never expand authority.
    Unknown native delegates remain indistinguishable; Hook checks known ones.
    """
    if not reason.strip() or len(reason) > 4096:
        raise ValueError("TASK_AUTHORITY_RECOVERY_REASON_REQUIRED")
    with core._lock(root):
        if digest(path(root)) != expected:
            raise ValueError("TASK_AUTHORITY_CHANGED")
        record = read(root)
        if record is None or record["status"] != "ACTIVE":
            raise ValueError("TASK_AUTHORITY_NOT_ACTIVE")
        from . import lifecycle
        ledger_path = lifecycle._lifecycle_path(root, record["task_id"])
        archive = directory() / "recovery" / (expected + "-" + uuid.uuid4().hex)
        archive.mkdir(parents=True, exist_ok=False)
        core._atomic_write(archive / "authority.json", path(root).read_bytes())
        for name in (*SECURITY_PATHS, ".context/state.json"):
            if digest(root / name) != "ABSENT":
                core._atomic_write(archive / name, (root / name).read_bytes())
        if digest(ledger_path) != "ABSENT":
            core._atomic_write(archive / "lifecycle.json", ledger_path.read_bytes())
        ledger = record.get("lifecycle_snapshot", {})
        record["fenced_agents"] = sorted(set(record["fenced_agents"]) |
            {child["agent_id_hash"] for child in ledger.get("children", []) if child.get("agent_id_hash")})
        record.setdefault("recoveries", []).append({"reason": reason, "archive": str(archive), "death_proof": "UNKNOWN"})
        for name, encoded in record["snapshots"].items():
            target = root / name
            if encoded is None:
                if target.is_file():
                    target.unlink()
            else:
                core._atomic_write(target, base64.b64decode(encoded, validate=True))
        if ledger:
            # Keep exact old child provenance in the external archive. A new
            # managed handoff is required; no old child is called Completed.
            ledger = {**ledger, "children": [], "pending_authorized_spawn": None,
                      "pending_spawn_terminal_evidence": None, "stall": None}
            core._atomic_write(ledger_path, (json.dumps(ledger, sort_keys=True, indent=2) + "\n").encode())
            record["lifecycle_snapshot"] = ledger
            record["lifecycle_sha256"] = digest(ledger_path)
        elif ledger_path.is_file():
            ledger_path.unlink()
        write(root, record)
        check(root)
    return {"ok": True, "status": "TASK_AUTHORITY_RECOVERED", "task_id": record["task_id"],
            "authority_provenance": record["provenance"], "host_actor_assurance": "UNKNOWN", "child_death_proof": "UNKNOWN"}
