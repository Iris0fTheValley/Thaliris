"""Codex compatibility facade for Core-owned external task authority.

Codex chooses its security paths, session facts, lifecycle snapshots and fences.
Core stores selected intent and restores the original protected bytes. Neither
layer proves human authorship or universal native Root identity.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import authority, core
from .authority import MODES, digest

SECURITY_PATHS = (".context/config.json", ".codex/thaliris.json", ".codex/hooks.json", ".codex/config.toml")


def directory() -> Path:
    # Deliberately independent of CODEX_HOME and repository configuration.
    return Path.home() / ".thaliris" / "task-authority"


def _store(root: Path) -> authority.AuthorityStore:
    return authority.AuthorityStore(root, directory(), protected_paths=SECURITY_PATHS)


def path(root: Path) -> Path:
    return _store(root).path()


def read(root: Path) -> dict | None:
    return _store(root).read()


def write(root: Path, record: dict) -> None:
    _store(root).write(record)


def contract(filename: str) -> dict:
    return authority.validate_contract(json.loads(Path(filename).read_text(encoding="utf-8")))


def establish(root: Path, state: dict, intent: dict, session_hash: str) -> dict:
    prior = read(root)
    if prior is not None and prior["status"] == "ACTIVE":
        raise ValueError("TASK_AUTHORITY_ALREADY_ACTIVE")
    return _store(root).establish(state, intent, adapter_fields={
        "provenance": "CONTROLLER_ASSERTED_HUMAN_INSTRUCTION", "host_actor_assurance": "UNKNOWN",
        "origin_session_hash": session_hash, "lifecycle_sha256": "ABSENT",
        "fenced_sessions": prior.get("fenced_sessions", []) if prior else [],
        "fenced_agents": prior.get("fenced_agents", []) if prior else [],
    })


def _evidence(root: Path, record: dict) -> dict:
    from . import lifecycle
    return {"lifecycle_sha256": (lifecycle._lifecycle_path(root, record["task_id"]), "TASK_AUTHORITY_LIFECYCLE_CHANGED")}


def check(root: Path) -> dict | None:
    store = _store(root)
    record = store.check()
    if record is None:
        return None
    return store.check(evidence=_evidence(root, record))


def checkpoint(root: Path) -> None:
    """Only trusted command closures call this after previously checked writes."""
    _store(root).checkpoint()


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
    """Restore the recorded authority and fence old Codex children.

    This continues the recorded authority without a new human grant. Unknown
    native delegates remain indistinguishable; Hook checks known ones.
    """
    def archive_paths(record: dict) -> dict:
        from . import lifecycle
        return {"lifecycle.json": lifecycle._lifecycle_path(root, record["task_id"])}

    def restore_adapter(record: dict) -> None:
        from . import lifecycle
        ledger_path = lifecycle._lifecycle_path(root, record["task_id"])
        ledger = record.get("lifecycle_snapshot", {})
        record["fenced_agents"] = sorted(set(record["fenced_agents"]) |
            {child["agent_id_hash"] for child in ledger.get("children", []) if child.get("agent_id_hash")})
        if ledger:
            # Core archived the exact old provenance. A fresh handoff is
            # required; no old child is called Completed.
            ledger = {**ledger, "children": [], "pending_authorized_spawn": None,
                      "pending_spawn_terminal_evidence": None, "stall": None}
            core._atomic_write(ledger_path, (json.dumps(ledger, sort_keys=True, indent=2) + "\n").encode())
            record["lifecycle_snapshot"] = ledger
            record["lifecycle_sha256"] = digest(ledger_path)
        elif ledger_path.is_file():
            ledger_path.unlink()
        record["recoveries"][-1]["death_proof"] = "UNKNOWN"

    result = _store(root).recover(expected, reason, archive_paths=archive_paths,
                                  restore_adapter=restore_adapter, evidence=lambda record: _evidence(root, record))
    return {**result, "host_actor_assurance": "UNKNOWN", "child_death_proof": "UNKNOWN"}
