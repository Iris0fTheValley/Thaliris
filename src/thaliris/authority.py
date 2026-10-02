"""Core-owned task intent and exact-byte authority anchors.

Adapters authorize operations and supply protected paths and native evidence.
This module does not identify actors, interpret intent, or certify completion.
The external store is a shared-OS governance boundary, not authentication.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import stat
from typing import Callable, Mapping
import uuid

from . import core

MODES = ("delegated", "controller-direct", "single-agent")
_CONTRACT_FIELDS = {"human_instruction", "boundary", "invariants", "acceptance", "execution_mode"}
_TRUTH_FIELDS = {"version", "project", "task_id", "goal", "contract", "status", "provenance",
                 "state_sha256", "security", "snapshots", "history"}
_CORE_OWNED_FIELDS = _TRUTH_FIELDS - {"provenance"}
_ADAPTER_TRUTH_FIELDS = {"host_actor_assurance"}


def _truth(record: dict) -> dict:
    """Return immutable authority fields plus any adapter-supplied assurance."""
    return {name: record.get(name) for name in _TRUTH_FIELDS | (_ADAPTER_TRUTH_FIELDS & record.keys())}


def validate_contract(value: object) -> dict:
    """Validate selected intent mechanically, without inferring its author."""
    if not isinstance(value, dict) or set(value) != _CONTRACT_FIELDS or value.get("execution_mode") not in MODES:
        raise ValueError("TASK_AUTHORITY_CONTRACT_REQUIRED")
    if any(not isinstance(value[key], str) or not value[key].strip() or len(value[key]) > 16384
           for key in _CONTRACT_FIELDS - {"execution_mode"}):
        raise ValueError("TASK_AUTHORITY_CONTRACT_REQUIRED")
    return value


def digest(target: Path) -> str:
    if target.is_symlink() or target.exists() and not target.is_file():
        raise ValueError("TASK_AUTHORITY_UNSAFE_PATH")
    return hashlib.sha256(target.read_bytes()).hexdigest() if target.is_file() else "ABSENT"


def _is_link(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        info = path.stat(follow_symlinks=False)
    except OSError:
        return False
    return bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _relative(root: Path, name: str) -> str:
    # Validate spelling without inspecting mutable repository configuration:
    # anchor lookup must remain available when protected paths have conflicts.
    if not isinstance(name, str) or "\\" in name or not name or name.startswith("/") or any(part in {"", ".", ".."} for part in name.split("/")):
        raise ValueError("path must be normalized POSIX repo-relative")
    if Path(name).is_absolute() or Path(name).drive:
        raise ValueError("path escapes repository")
    return name


class AuthorityStore:
    """One external anchor for the Core task ledger in a resolved workspace.

    ``storage_directory`` is explicit and outside the workspace. Protected
    configuration paths are chosen by the adapter, never read from mutable
    configuration. Native evidence remains adapter-owned; evidence checks map
    an existing record digest field to (path, conflict error). Mutations require
    adapter authorization and a previously checked command boundary. Ordinary
    ledger operations use Core's lock; recovery holds that same lock throughout.
    """

    def __init__(self, root: Path, storage_directory: Path, *, protected_paths: tuple[str, ...] = ()):
        self.root = root
        self.directory = storage_directory
        self.protected_paths = tuple(_relative(root, name) for name in protected_paths)

    def path(self) -> Path:
        location = self.directory
        if location.resolve().is_relative_to(self.root.resolve()) or any(_is_link(item) for item in (location, *location.parents)):
            raise ValueError("TASK_AUTHORITY_EXTERNAL_LOCATION_UNSAFE")
        identity = str(self.root.resolve()).casefold() if os.name == "nt" else str(self.root.resolve())
        return location / (hashlib.sha256(identity.encode()).hexdigest() + ".json")

    def read(self) -> dict | None:
        target = self.path()
        if digest(target) == "ABSENT":
            return None
        record = json.loads(target.read_text(encoding="utf-8"))
        if (not isinstance(record, dict) or record.get("version") != 1 or not isinstance(record.get("project"), str)
                or Path(record["project"]).resolve() != self.root.resolve()):
            raise ValueError("TASK_AUTHORITY_INVALID")
        return record

    def write(self, record: dict) -> None:
        """Persist an adapter-authorized record; this is not an authority grant."""
        core._atomic_write(self.path(), (json.dumps(record, sort_keys=True, indent=2) + "\n").encode())

    def establish(self, state: dict, intent: dict, *, adapter_fields: dict | None = None) -> dict:
        intent = validate_contract(intent)
        fields = adapter_fields or {}
        if _CORE_OWNED_FIELDS & fields.keys():
            raise ValueError("TASK_AUTHORITY_IDENTITY_CHANGED")
        # Only an existing ACTIVE Core ledger can be anchored. No second task
        # state or host-specific task identity is created here.
        current = json.loads(core._state_path(self.root).read_text(encoding="utf-8"))
        if current.get("task_id") != state["task_id"] or current.get("goal") != state["goal"] or current.get("status") != "ACTIVE":
            raise ValueError("TASK_AUTHORITY_IDENTITY_CHANGED")
        prior = self.read()
        if prior is not None and prior["status"] == "ACTIVE":
            raise ValueError("TASK_AUTHORITY_ALREADY_ACTIVE")
        if prior is not None:
            core._atomic_write(self.directory / "history" / f"{self.path().stem}-{prior['task_id']}.json", self.path().read_bytes())
        record = {"version": 1, "project": str(self.root.resolve()), "task_id": state["task_id"],
                  "goal": state["goal"], "contract": intent, "status": "ACTIVE",
                  "provenance": "SELECTED_TASK_INTENT",
                  "state_sha256": digest(core._state_path(self.root)),
                  "security": {name: digest(self.root / name) for name in self.protected_paths},
                  "history": prior.get("history", []) + [{"task_id": prior["task_id"], "goal": prior["goal"],
                      "status": prior["status"], "contract": prior["contract"]}] if prior else [], **fields}
        record["snapshots"] = {name: base64.b64encode((self.root / name).read_bytes()).decode()
                               if digest(self.root / name) != "ABSENT" else None
                               for name in (*self.protected_paths, ".context/state.json")}
        self.write(record)
        return record

    def check(self, *, evidence: Mapping[str, tuple[Path, str]] | None = None) -> dict | None:
        record = self.read()
        if record is None:
            return None
        if record["status"] != "ACTIVE":
            if digest(core._state_path(self.root)) != record["state_sha256"]:
                raise ValueError("TASK_AUTHORITY_RETIRED_STATE_CHANGED")
            return None
        if digest(core._state_path(self.root)) != record["state_sha256"]:
            raise ValueError("TASK_AUTHORITY_STATE_CHANGED")
        if any(digest(self.root / name) != expected for name, expected in record["security"].items()):
            raise ValueError("TASK_AUTHORITY_SECURITY_CHANGED")
        state = json.loads(core._state_path(self.root).read_text(encoding="utf-8"))
        if state.get("task_id") != record["task_id"] or state.get("goal") != record["goal"] or state.get("status") != "ACTIVE":
            raise ValueError("TASK_AUTHORITY_IDENTITY_CHANGED")
        for field, (target, error) in (evidence or {}).items():
            if digest(target) != record[field]:
                raise ValueError(error)
        return record

    def checkpoint(self) -> None:
        """Anchor a checked ledger mutation, including DONE or deleted state.

        The task identity and selected contract are never changed. Deletion
        retires authority as ABANDONED; it does not prove task completion.
        """
        record = self.read()
        if record is None or record["status"] != "ACTIVE":
            return
        record["state_sha256"] = digest(core._state_path(self.root))
        record["snapshots"][".context/state.json"] = base64.b64encode(core._state_path(self.root).read_bytes()).decode() if record["state_sha256"] != "ABSENT" else None
        if record["state_sha256"] == "ABSENT":
            record["status"] = "ABANDONED"
        else:
            state = json.loads(core._state_path(self.root).read_text(encoding="utf-8"))
            if state["task_id"] != record["task_id"] or state["goal"] != record["goal"]:
                raise ValueError("TASK_AUTHORITY_IDENTITY_CHANGED")
            record["status"] = state["status"]
        self.write(record)

    def recover(self, expected: str, reason: str, *,
                archive_paths: Mapping[str, Path] | Callable[[dict], Mapping[str, Path]] | None = None,
                restore_adapter: Callable[[dict], None] | None = None,
                evidence: Mapping[str, tuple[Path, str]] | Callable[[dict], Mapping[str, tuple[Path, str]]] | None = None) -> dict:
        """CAS archive and restore recorded bytes; adapter restores its evidence.

        An adapter recovery callback may add fences and reset native evidence.
        It must never expand intent or claim native death/completion. Core owns
        exact-byte restoration of protected configuration and ledger state.
        Callable path/evidence maps resolve adapter facts from the locked record.
        """
        if not reason.strip() or len(reason) > 4096:
            raise ValueError("TASK_AUTHORITY_RECOVERY_REASON_REQUIRED")
        with core._lock(self.root):
            if digest(self.path()) != expected:
                raise ValueError("TASK_AUTHORITY_CHANGED")
            record = self.read()
            if record is None or record["status"] != "ACTIVE":
                raise ValueError("TASK_AUTHORITY_NOT_ACTIVE")
            truth = json.dumps(_truth(record), sort_keys=True)
            paths = archive_paths(record) if callable(archive_paths) else archive_paths or {}
            if json.dumps(_truth(record), sort_keys=True) != truth:
                raise ValueError("TASK_AUTHORITY_IDENTITY_CHANGED")
            # Validate/decode all restoration bytes before any repository write.
            restored = {}
            for name, encoded in record["snapshots"].items():
                _relative(self.root, name)
                restored[name] = None if encoded is None else base64.b64decode(encoded, validate=True)
            for name in paths:
                _relative(self.directory, name)
                if name in {"authority.json", *restored}:
                    raise ValueError("TASK_AUTHORITY_ARCHIVE_PATH_CONFLICT")
            archive = self.directory / "recovery" / (expected + "-" + uuid.uuid4().hex)
            archive.mkdir(parents=True, exist_ok=False)
            core._atomic_write(archive / "authority.json", self.path().read_bytes())
            for name in restored:
                if digest(self.root / name) != "ABSENT":
                    core._atomic_write(archive / name, (self.root / name).read_bytes())
            for name, target in paths.items():
                if digest(target) != "ABSENT":
                    core._atomic_write(archive / name, target.read_bytes())
            record.setdefault("recoveries", []).append({"reason": reason, "archive": str(archive)})
            for name, content in restored.items():
                target = self.root / name
                if content is None:
                    if target.is_file():
                        target.unlink()
                else:
                    core._atomic_write(target, content)
            if restore_adapter is not None:
                restore_adapter(record)
                if json.dumps(_truth(record), sort_keys=True) != truth:
                    raise ValueError("TASK_AUTHORITY_IDENTITY_CHANGED")
            checks = evidence(record) if callable(evidence) else evidence
            if json.dumps(_truth(record), sort_keys=True) != truth:
                raise ValueError("TASK_AUTHORITY_IDENTITY_CHANGED")
            self.write(record)
            self.check(evidence=checks)
        return {"ok": True, "status": "TASK_AUTHORITY_RECOVERED", "task_id": record["task_id"],
                "authority_provenance": record["provenance"]}
