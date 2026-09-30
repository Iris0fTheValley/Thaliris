"""Operator-asserted administration while global integration is disconnected.

This is a governance boundary on a shared OS, not cryptographic human consent.
It grants only exact archival, fencing, and release of an incomplete task slot.
It never establishes a Host actor, Controller ownership, or child authority.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import time
import uuid

from . import core, lifecycle

AUTHORITY = "OPERATOR_ASSERTED_USER_DELEGATED_ADMINISTRATION"
_HASH = re.compile(r"[0-9a-f]{64}\Z")


def _disconnected(home: Path) -> dict[str, object]:
    """Observe disk configuration; this does not attest a running Host."""
    for name in ("hooks.json", "AGENTS.md"):
        path = home / name
        if path.exists():
            # Inspect every ancestor, including Windows junctions.
            from .runtime_identity import _safe_file
            _safe_file(path.absolute())
            raw = path.read_bytes()
            if len(raw) > 1024 * 1024:
                raise ValueError("OFFLINE_INTEGRATION_STATE_UNKNOWN")
            if name == "hooks.json":
                document = json.loads(raw)
                if not isinstance(document, dict) or not isinstance(document.get("hooks"), dict):
                    raise ValueError("OFFLINE_INTEGRATION_STATE_UNKNOWN")
                if "thaliris" in json.dumps(document["hooks"]).casefold():
                    raise ValueError("OFFLINE_INTEGRATION_MUST_BE_DISCONNECTED")
            elif b"<!-- thaliris:global:begin -->" in raw:
                raise ValueError("OFFLINE_INTEGRATION_MUST_BE_DISCONNECTED")
    return {"global_configuration": "DISCONNECTED_ON_DISK", "running_host_configuration": "UNKNOWN",
            "operator_assertion": "INTEGRATION_DISCONNECTED", "authority_proof": "NONE_SHARED_OS_GOVERNANCE"}


def _extract(raw: bytes) -> tuple[set[str], set[str], str]:
    """Extract identifiers conservatively even when a ledger cannot be parsed.

    Extracted strings are fencing evidence only, never ownership evidence.
    Partial child records and unknown schema fields are deliberately included.
    """
    sessions: set[str] = set()
    agents: set[str] = set()
    def add(key: str, value: object) -> None:
        if not isinstance(value, str) or not value or len(value) > 4096:
            return
        key = key.casefold()
        target = sessions if "session_id" in key else agents if any(
            part in key for part in ("agent_id", "thread_id", "child_id", "task_name")
        ) else None
        if target is None:
            return
        if key.endswith("_hash"):
            if _HASH.fullmatch(value):
                target.add(value)
        else:
            target.add(hashlib.sha256(value.encode()).hexdigest())
    def walk(value: object) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                add(key, child)
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    try:
        walk(json.loads(raw))
        status = "PARSED_SCHEMA_UNVERIFIED"
    except (ValueError, UnicodeError, RecursionError):
        status = "MALFORMED_BEST_EFFORT"
    # Also catches complete string members in otherwise malformed JSON.
    for match in re.finditer(r'"([^"\\]*(?:session_id|agent_id|thread_id|child_id|task_name)[^"\\]*)"\s*:\s*("(?:[^"\\]|\\.)*")', raw.decode("utf-8", errors="replace")):
        try:
            add(match[1], json.loads(match[2]))
        except ValueError:
            pass
    return sessions, agents, status


def recover(root: Path, task_id: str, revision: int, state_sha256: str,
            lifecycle_sha256: str, reason: str, *, codex_home: Path,
            operator_asserted_user_delegation: bool = False,
            integration_disconnected: bool = False) -> dict[str, object]:
    if not operator_asserted_user_delegation or not integration_disconnected:
        raise ValueError("OFFLINE_OPERATOR_ASSERTIONS_REQUIRED")
    root = core._repo_root(root)
    uuid.UUID(task_id)
    if type(revision) is not int or revision < 1 or not _HASH.fullmatch(state_sha256):
        raise ValueError("invalid exact state recovery packet")
    if lifecycle_sha256 != "ABSENT" and not _HASH.fullmatch(lifecycle_sha256):
        raise ValueError("invalid exact lifecycle recovery packet")
    if not reason.strip() or len(reason) > 4096 or any(ord(c) < 32 and c not in "\n\t" for c in reason):
        raise ValueError("offline recovery requires a bounded reason")
    with core._lock(root):
        observation = _disconnected(codex_home)
        state_path = core._safe_without_final_symlink(root, ".context/state.json")
        raw = state_path.read_bytes()
        if len(raw) > 512 * 1024 or hashlib.sha256(raw).hexdigest() != state_sha256:
            raise ValueError("offline recovery state bytes changed")
        state = json.loads(raw)
        if not isinstance(state, dict) or state.get("status") != "ACTIVE" or state.get("task_id") != task_id or type(state.get("revision")) is not int or state.get("revision") != revision:
            raise ValueError("offline recovery task identity or revision changed")
        ledger_path = core._safe_without_final_symlink(root, lifecycle._lifecycle_path(root, task_id).relative_to(root).as_posix())
        try:
            ledger_raw = ledger_path.read_bytes()
        except FileNotFoundError:
            ledger_raw = None
        actual = hashlib.sha256(ledger_raw).hexdigest() if ledger_raw is not None else "ABSENT"
        if actual != lifecycle_sha256 or (ledger_raw is not None and len(ledger_raw) > 512 * 1024):
            raise ValueError("offline recovery lifecycle bytes changed")
        sessions, agents, state_extraction = _extract(raw)
        ledger_extraction = "ABSENT"
        if ledger_raw is not None:
            old_sessions, old_agents, ledger_extraction = _extract(ledger_raw)
            sessions |= old_sessions
            agents |= old_agents
        # Validate existing fences before writing anything. A damaged fence
        # needs a separate informed repair, not silent loss of old evidence.
        session_fence = lifecycle._read_session_fence(root) | sessions
        children = lifecycle._read_abandoned_child_fence(root)
        owners = lifecycle._read_abandoned_owner_hashes(root) | sessions
        complete, provenance = lifecycle._read_abandoned_spawn_provenance(root)
        agent_fence = lifecycle._read_abandoned_agent_hashes(root) | agents
        archive = core._safe_without_final_symlink(root, f".context/audit/abandoned/{lifecycle._task_key(task_id)}-{uuid.uuid4().hex}")
        archive.mkdir(parents=True, exist_ok=False)
        core._atomic_write(archive / "state.json", raw)
        if ledger_raw is not None:
            core._atomic_write(archive / "lifecycle.json", ledger_raw)
        record = {"version": 1, "status": "ABANDONED", "lifecycle_status": "RECOVERED_INCOMPLETE",
                  "task_id": task_id, "revision": revision, "state_sha256": state_sha256,
                  "lifecycle_sha256": lifecycle_sha256, "reason": reason,
                  "recovery_mode": "OFFLINE_ADMINISTRATIVE_RECOVERY", "recovery_authority": AUTHORITY,
                  "integration_observation": observation, "recovery_session_id_hash": "UNKNOWN",
                  "recovery_host_attestation": "ABSENT", "old_owner_assurance": "UNKNOWN",
                  "host_termination": "UNKNOWN", "unbound_child_identity": "UNKNOWN",
                  "incompatible_fields": "PRESERVED_UNVERIFIED", "state_identity_extraction": state_extraction,
                  "lifecycle_identity_extraction": ledger_extraction, "identity_extraction_completeness": "UNKNOWN",
                  "fenced_session_id_hashes": sorted(sessions), "fenced_agent_id_hashes": sorted(agents),
                  "recovered_at_ns": time.time_ns()}
        core._atomic_write(archive / "manifest.json", (json.dumps(record, sort_keys=True, indent=2) + "\n").encode())
        if (archive / "state.json").read_bytes() != raw or (ledger_raw is not None and (archive / "lifecycle.json").read_bytes() != ledger_raw):
            raise ValueError("offline recovery archive verification failed")
        lifecycle._write_capture(lifecycle._session_fence_path(root), {"version": 1, "session_id_hashes": sorted(session_fence)})
        lifecycle._write_capture(lifecycle._abandoned_child_fence_path(root), {"version": 1, "children": children,
            "agent_id_hashes": sorted(agent_fence), "owner_session_id_hashes": sorted(owners),
            "owner_spawn_provenance_complete": sorted(complete), "owner_spawn_provenance": provenance})
        if lifecycle._read_session_fence(root) != session_fence or lifecycle._read_abandoned_agent_hashes(root) != agent_fence:
            raise ValueError("offline recovery fence verification failed")
        # Retest configuration immediately before releasing the exact slot.
        _disconnected(codex_home)
        # Absence is part of the exact packet too. Do not substitute the old
        # observation for a current read: a late child ledger must retain the
        # task slot until its bytes and identities can be archived and fenced.
        current_ledger_path = core._safe_without_final_symlink(root, ledger_path.relative_to(root).as_posix())
        try:
            current_ledger_raw = current_ledger_path.read_bytes()
        except FileNotFoundError:
            current_ledger_raw = None
        if state_path.read_bytes() != raw or current_ledger_raw != ledger_raw:
            raise ValueError("offline recovery evidence changed before release")
        state_path.unlink()
    return {"ok": True, "status": "ABANDONED", "task_id": task_id, "revision": revision,
            "archive": archive.relative_to(root).as_posix(), "recovery_mode": record["recovery_mode"],
            "recovery_authority": AUTHORITY, "host_termination": "UNKNOWN"}
