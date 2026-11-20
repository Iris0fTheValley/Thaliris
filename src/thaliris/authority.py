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
import re
import stat
import unicodedata
from typing import Callable, Mapping
import uuid

from . import core

# ``adaptive``: the Controller may execute directly and may also dispatch children.
MODES = ("delegated", "controller-direct", "single-agent", "adaptive")
_CONTRACT_FIELDS = {"human_instruction", "boundary", "invariants", "acceptance", "execution_mode"}
_OPTIONAL_CONTRACT_FIELDS = {"execution_constraint", "parallel_dispatch", "write_surface"}
# Quick admission: an adaptive contract may omit these; each omitted one is stored as the
# explicit marker below, never inferred. Goal, human_instruction and acceptance stay required.
ADAPTIVE_OPTIONAL_FIELDS = ("boundary", "invariants")
UNSPECIFIED = "unspecified"
WRITE_SURFACE_MAX_GLOBS = 64
_TRUTH_FIELDS = {"version", "project", "task_id", "goal", "contract", "status", "provenance",
                 "state_sha256", "security", "snapshots", "history"}
_CORE_OWNED_FIELDS = _TRUTH_FIELDS - {"provenance"}
_ADAPTER_TRUTH_FIELDS = {"host_actor_assurance"}


def _truth(record: dict) -> dict:
    """Return immutable authority fields plus any adapter-supplied assurance."""
    return {name: record.get(name) for name in _TRUTH_FIELDS | (_ADAPTER_TRUTH_FIELDS & record.keys())}


def validate_contract(value: object) -> dict:
    """Validate selected intent mechanically, without inferring its author."""
    if isinstance(value, dict) and "execution_mode" not in value:
        value = {**value, "execution_mode": "delegated"}
    if isinstance(value, dict) and value["execution_mode"] == "adaptive" and set(ADAPTIVE_OPTIONAL_FIELDS) - value.keys():
        value = {**value, **{name: UNSPECIFIED for name in ADAPTIVE_OPTIONAL_FIELDS if name not in value}}
    fields = set(value) if isinstance(value, dict) else set()
    missing = sorted(_CONTRACT_FIELDS - fields)
    unknown = sorted(str(key)[:64] for key in fields - _CONTRACT_FIELDS - _OPTIONAL_CONTRACT_FIELDS)
    invalid = []
    if isinstance(value, dict):
        invalid = sorted(key for key in ((_CONTRACT_FIELDS - {"execution_mode"}) | _OPTIONAL_CONTRACT_FIELDS) & fields
                         if key not in {"parallel_dispatch", "write_surface"}
                         and (not isinstance(value[key], str) or not value[key].strip() or len(value[key]) > 16384))
        if "write_surface" in value and not _valid_write_surface(value["write_surface"]):
            invalid.append("write_surface")
        if "execution_mode" in value and value["execution_mode"] not in MODES:
            invalid.append("execution_mode")
        if "parallel_dispatch" in value:
            try:
                _validate_parallel_dispatch(value["parallel_dispatch"])
            except ValueError:
                invalid.append("parallel_dispatch")
    if not isinstance(value, dict) or missing or unknown or invalid:
        raise core.ThalirisError(
            "TASK_AUTHORITY_CONTRACT_REQUIRED", "TASK_AUTHORITY_CONTRACT_REQUIRED",
            recovery="supply one contract object with the required field names; correct only the listed fields and retry; authority was not established",
            details={"expected_type": "object", "required_fields": sorted(_CONTRACT_FIELDS),
                     "optional_fields": sorted(_OPTIONAL_CONTRACT_FIELDS), "missing_fields": missing,
                     "unknown_fields": unknown[:16], "unknown_field_count": len(unknown),
                     "invalid_fields": sorted(invalid), "execution_modes": list(MODES),
                     "adaptive_optional_fields": list(ADAPTIVE_OPTIONAL_FIELDS),
                     "write_surface": f"1 to {WRITE_SURFACE_MAX_GLOBS} repo-relative POSIX globs",
                     "text_fields": "nonempty strings of at most 16384 characters"})
    return value


def _valid_write_surface(value: object) -> bool:
    """Shape of the optional write-surface globs; Core only compares the task surface against them."""
    if not isinstance(value, list) or not 1 <= len(value) <= WRITE_SURFACE_MAX_GLOBS or len(set(map(str, value))) != len(value):
        return False
    for glob in value:
        if not isinstance(glob, str) or not glob.strip() or len(glob) > 256 or "\\" in glob or glob.startswith("/"):
            return False
        if any(part in {"", ".", ".."} for part in glob.rstrip("/").split("/")) or any(ord(char) < 32 for char in glob):
            return False
    return True


_SCOPE_META = set("*?")
_SHORT_NAME = re.compile(r"^[^.~]{1,6}~\d{1,6}(\.[^.]{0,3})?$", re.IGNORECASE)
_PARENT_HINT = "; declare a parent directory instead"


def canonical_scope(value: str) -> str:
    """Return the canonical repo-relative spelling of a dispatch scope.

    Scopes are literal paths, never patterns: ``[ ] { } ( )`` are ordinary characters.
    NFC, casefolded on every platform (a false overlap refusal is the conservative
    direction), backslash becomes ``/``, repeated ``/`` collapse and a leading ``./``
    or leading/trailing ``/`` is stripped.  Raises ``ValueError`` (naming the failed
    rule) for empty scopes, ``.``/``..`` segments, drive-letter, UNC or ``~`` home
    forms, ``*``/``?``, segments ending in a dot or space, ``:`` and control
    characters.  Windows 8.3-looking segments (``PROGRA~1``) are admitted; see
    ``scopes_overlap`` for how they are compared.
    """
    if not isinstance(value, str):
        raise ValueError("invalid scope: must be a string")
    text = unicodedata.normalize("NFC", value.strip()).replace("\\", "/")
    if text.startswith("//"):
        raise ValueError("invalid scope: UNC paths are not repo-relative" + _PARENT_HINT)
    if any(ord(c) < 32 or ord(c) == 127 for c in text):
        raise ValueError("invalid scope: control characters are not allowed")
    if _SCOPE_META & set(text):
        raise ValueError("invalid scope: '*' and '?' are glob-only characters and invalid in Windows file names" + _PARENT_HINT)
    if ":" in text:
        raise ValueError("invalid scope: ':' (drive letter or stream form) is not allowed; use a repo-relative path")
    text = re.sub(r"/+", "/", text)
    while text.startswith("./"):
        text = text[2:]
    text = text.strip("/")
    if not text:
        raise ValueError("invalid scope: empty scope")
    if text.startswith("~"):
        raise ValueError("invalid scope: a leading '~' means a home directory; use a repo-relative path")
    segments = text.split("/")
    for part in segments:
        if part in {".", ".."}:
            raise ValueError("invalid scope: '.' and '..' segments are not allowed")
        if part.endswith((".", " ")) or part != part.strip():
            raise ValueError("invalid scope: a segment may not start or end with a space or end with a dot" + _PARENT_HINT)
    return unicodedata.normalize("NFC", "/".join(segments).casefold())


def scopes_overlap(a: str, b: str) -> bool:
    """True when the canonical scopes may name the same write domain.

    Equal or path-segment prefix overlaps.  A segment that looks like a Windows 8.3
    short name (``PROGRA~1``) may alias any sibling under the same parent, so if either
    scope has one at index i the scopes also overlap when both have at least i segments
    and agree on every segment below i.  This can over-refuse siblings; it never
    under-detects.
    """
    return _canonical_overlap(canonical_scope(a), canonical_scope(b))


def _canonical_overlap(ca: str, cb: str) -> bool:
    if ca == cb or ca.startswith(cb + "/") or cb.startswith(ca + "/"):
        return True
    sa, sb = ca.split("/"), cb.split("/")
    for segs in (sa, sb):
        for i, part in enumerate(segs):
            if _SHORT_NAME.match(part) and len(sa) >= i and len(sb) >= i and sa[:i] == sb[:i]:
                return True
    return False


def _first_short_index(segs: list[str]) -> int | None:
    for i, part in enumerate(segs):
        if _SHORT_NAME.match(part):
            return i
    return None


class _WriteScopeIndex:
    """Near-linear equivalent of pairwise ``_canonical_overlap`` over claimed scopes.

    ``claimed`` holds whole scopes, ``prefixes`` every prefix (including the empty one
    and the scope itself) of every claimed scope, and ``short_parents`` the canonical
    parent prefix of the first 8.3-looking segment of each claimed scope.  Only the first
    8.3 segment matters: agreement below a later one implies agreement below the first.
    """

    def __init__(self) -> None:
        self.claimed: set[tuple[str, ...]] = set()
        self.prefixes: set[tuple[str, ...]] = set()
        self.short_parents: set[tuple[str, ...]] = set()

    def overlaps(self, canonical: str) -> bool:
        segs = tuple(canonical.split("/"))
        # equal to, or a descendant of, a claimed scope
        if any(segs[:k] in self.claimed for k in range(1, len(segs) + 1)):
            return True
        # an ancestor of (or equal to) a claimed scope
        if segs in self.prefixes:
            return True
        # a claimed 8.3 segment may alias one of our segments
        if any(segs[:j] in self.short_parents for j in range(len(segs) + 1)):
            return True
        # our 8.3 segment may alias a sibling of any claimed scope that extends the parent
        i = _first_short_index(list(segs))
        return i is not None and segs[:i] in self.prefixes

    def add(self, canonical: str) -> None:
        segs = tuple(canonical.split("/"))
        self.claimed.add(segs)
        self.prefixes.update(segs[:k] for k in range(len(segs) + 1))
        i = _first_short_index(list(segs))
        if i is not None:
            self.short_parents.add(segs[:i])


# State-size guard only: total characters across all declared workstream strings.
PARALLEL_DISPATCH_MAX_TEXT = 1 << 20


def _validate_parallel_dispatch(value: object) -> None:
    """Validate the optional user-directed parallel dispatch contract.

    Parallelism is the user's choice: there is no program-side count cap.  ``budget``
    is optional and, when present, is the user's explicit positive number.
    ``workstreams`` is optional (absent or empty means read-only fan-out).  The only
    mechanical refusal is overlapping *write* scopes, across all domains, by equality
    or path prefix.  Native identity, fences, CAS and ownership remain adapter/runtime
    concerns; unknown fields are rejected so a malformed contract cannot silently widen
    dispatch.
    """
    if not isinstance(value, dict) or not {"enabled"} <= set(value) <= {"enabled", "budget", "workstreams"}:
        raise ValueError("invalid parallel_dispatch contract")
    if value.get("enabled") is not True:
        raise ValueError("invalid parallel_dispatch enabled")
    if "budget" in value and (type(value["budget"]) is not int or value["budget"] < 1):
        raise ValueError("invalid parallel_dispatch budget")
    streams = value.get("workstreams", [])
    if not isinstance(streams, list):
        raise ValueError("invalid parallel_dispatch workstreams")
    ids: set[str] = set()
    write_scopes = _WriteScopeIndex()
    text = 0
    for stream in streams:
        if not isinstance(stream, dict) or set(stream) != {"id", "domain", "scope", "worktree", "mode"}:
            raise ValueError("invalid parallel_dispatch workstream")
        ident, domain, scope, worktree, mode = (stream.get(k) for k in ("id", "domain", "scope", "worktree", "mode"))
        if any(not isinstance(item, str) or not item.strip() or len(item) > 256 for item in (ident, domain)):
            raise ValueError("invalid parallel_dispatch workstream identity")
        if ident in ids:
            raise ValueError("duplicate parallel_dispatch workstream id")
        ids.add(ident)
        if mode not in {"read", "write"}:
            raise ValueError("invalid parallel_dispatch workstream mode")
        if isinstance(scope, str):
            scopes = [scope]
        elif isinstance(scope, list) and scope and all(isinstance(item, str) for item in scope):
            scopes = scope
        else:
            raise ValueError("invalid parallel_dispatch scope")
        if worktree is not None and (not isinstance(worktree, str) or not worktree.strip() or len(worktree) > 256):
            raise ValueError("invalid parallel_dispatch worktree")
        text += len(ident) + len(domain) + len(worktree or "") + sum(len(item) for item in scopes)
        if text > PARALLEL_DISPATCH_MAX_TEXT:
            raise ValueError("parallel_dispatch contract too large")
        normalized = [canonical_scope(item) for item in scopes]
        if mode != "write":
            continue
        for item in normalized:
            if write_scopes.overlaps(item):
                raise ValueError("overlapping parallel_dispatch write scopes")
        for item in normalized:
            write_scopes.add(item)


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


# Anchor record versions. Reading promotes an older record forward in memory (it is written in the
# current shape on the next anchor write, like task state); only a newer version is refused, with a
# recovery that names the upgrade. Promotion never invents tamper evidence: ``state_sha256`` and the
# identity fields stay required, and every digest the record holds is compared exactly.
ANCHOR_VERSION = 1
_ANCHOR_REQUIRED_FIELDS = ("project", "task_id", "goal", "contract", "status", "state_sha256")
# Fields an older writer may not have recorded, and the value that means "nothing recorded".
_ANCHOR_DEFAULTS: dict[str, Callable[[], object]] = {"security": dict, "snapshots": dict, "history": list}


def _promote_anchor_0_to_1(record: dict) -> dict:
    """An unversioned anchor predates the version field; its shape is version 1 without the marker."""
    return {**record, "version": 1}


# Prior anchor version -> step that lifts it by one version (absent ``version`` reads as 0).
_ANCHOR_PROMOTIONS: dict[int, Callable[[dict], dict]] = {0: _promote_anchor_0_to_1}


def _anchor_invalid(name: str, reason: str, **details: object) -> core.ThalirisError:
    return core.ThalirisError(
        core.errors.TASK_AUTHORITY_INVALID, "TASK_AUTHORITY_INVALID",
        recovery=("the external authority anchor is not a readable Core authority record; Core does not repair or "
                  "replace it; restore its exact bytes from a copy or use the adapter's recovery procedure"),
        details={"reason": reason, "anchor": name, **details})


def _promoted_anchor(record: object, name: str) -> dict:
    """The current-version, defaults-filled form of a stored anchor record (in memory only)."""
    if not isinstance(record, dict):
        raise _anchor_invalid(name, "anchor is not a JSON object")
    version = record.get("version", 0)
    if type(version) is not int or version < 0:
        raise _anchor_invalid(name, "anchor version is not a non-negative integer")
    if version > ANCHOR_VERSION:
        raise core.ThalirisError(
            core.errors.TASK_AUTHORITY_INVALID, "TASK_AUTHORITY_INVALID",
            recovery=(f"the anchor was written by a newer Thaliris (anchor version {version}; this Core reads up to "
                      f"{ANCHOR_VERSION}); upgrade Thaliris Core and its adapter; the anchor is unchanged"),
            details={"reason": "anchor version is newer than this Core", "anchor": name, "version": version,
                     "supported_version": ANCHOR_VERSION, "upgrade_required": True})
    for step in range(version, ANCHOR_VERSION):
        if step not in _ANCHOR_PROMOTIONS:
            raise _anchor_invalid(name, "anchor version has no promotion path", version=version)
        record = _ANCHOR_PROMOTIONS[step](record)
    missing = [field for field in _ANCHOR_REQUIRED_FIELDS if field not in record]
    if missing:
        raise _anchor_invalid(name, "anchor lacks required fields", missing_fields=missing)
    if not isinstance(record["contract"], dict) or not isinstance(record["state_sha256"], str):
        raise _anchor_invalid(name, "anchor contract or state digest has the wrong type")
    promoted = dict(record)
    for field, default in _ANCHOR_DEFAULTS.items():
        if field not in promoted:
            promoted[field] = default()
        elif not isinstance(promoted[field], type(default())):
            raise _anchor_invalid(name, f"anchor {field} has the wrong type")
    if "execution_mode" not in promoted["contract"]:
        # Contracts recorded before execution modes are delegated (validate_contract's default).
        promoted["contract"] = {**promoted["contract"], "execution_mode": "delegated"}
    return promoted


class AuthorityStore:
    """Task ID scoped external anchors, with exact legacy-byte preservation.

    ``storage_directory`` is explicit and outside the workspace. Protected
    configuration paths are chosen by the adapter, never read from mutable
    configuration. Native evidence remains adapter-owned; evidence checks map
    an existing record digest field to (path, conflict error). Mutations require
    adapter authorization and a previously checked command boundary. Ordinary
    ledger operations use Core's lock; recovery holds that same lock throughout.
    """

    def __init__(self, root: Path, storage_directory: Path, *, protected_paths: tuple[str, ...] = (), task_id: str | None = None):
        self.root = root
        self.task_id = task_id
        self.directory = storage_directory
        self.protected_paths = tuple(_relative(root, name) for name in protected_paths)

    def path(self) -> Path:
        location = self.directory
        if location.resolve().is_relative_to(self.root.resolve()) or any(_is_link(item) for item in (location, *location.parents)):
            raise ValueError("TASK_AUTHORITY_EXTERNAL_LOCATION_UNSAFE")
        identity = str(self.root.resolve()).casefold() if os.name == "nt" else str(self.root.resolve())
        key = hashlib.sha256(identity.encode()).hexdigest()
        task_id = self.task_id or core.selected_task(self.root)
        legacy = location / (key + ".json")
        def checked(target: Path) -> Path:
            # A workspace-key directory is mutable too. Checking only the
            # storage root would follow a Junction into user/project files.
            if (_is_link(target) or _is_link(target.parent)
                    or not target.resolve().is_relative_to(location.resolve())
                    or target.resolve().is_relative_to(self.root.resolve())):
                raise ValueError("TASK_AUTHORITY_EXTERNAL_LOCATION_UNSAFE")
            return target
        if task_id is None:
            return checked(legacy)
        if str(uuid.UUID(task_id)) != task_id:
            raise ValueError("TASK_AUTHORITY_INVALID_TASK_ID")
        indexed = checked(location / key / (task_id + ".json"))
        if indexed.exists():
            return indexed
        if legacy.is_file():
            try:
                if json.loads(legacy.read_text(encoding="utf-8")).get("task_id") == task_id:
                    return checked(legacy)
            except (OSError, ValueError, AttributeError):
                pass
        return indexed

    def read(self) -> dict | None:
        target = self.path()
        if digest(target) == "ABSENT":
            return None
        try:
            record = json.loads(target.read_text(encoding="utf-8"))
        except ValueError as exc:  # JSONDecodeError and UnicodeDecodeError
            raise core.ThalirisError(
                core.errors.TASK_AUTHORITY_INVALID, "TASK_AUTHORITY_INVALID",
                recovery=("the external authority anchor is not readable JSON; Core does not repair or replace it; "
                          "restore its exact bytes from a copy or use the adapter's recovery procedure"),
                details={"reason": "anchor is not valid UTF-8 JSON", "anchor": target.name}) from exc
        record = _promoted_anchor(record, target.name)
        if not isinstance(record.get("project"), str) or Path(record["project"]).resolve() != self.root.resolve():
            raise ValueError("TASK_AUTHORITY_INVALID")
        selected = self.task_id or core.selected_task(self.root)
        if selected is not None and record.get("task_id") != selected:
            raise ValueError("TASK_AUTHORITY_IDENTITY_CHANGED")
        self.task_id = record.get("task_id")
        if ".context/state.json" in record.get("snapshots", {}):
            core.remember_legacy_task(self.root, self.task_id)
        return record

    def write(self, record: dict) -> None:
        """Persist an adapter-authorized record; this is not an authority grant."""
        core._atomic_write(self.path(), (json.dumps(record, sort_keys=True, indent=2) + "\n").encode())

    def _state_snapshot(self, record: dict) -> bytes | None:
        name = core._state_path(self.root, record["task_id"]).relative_to(self.root).as_posix()
        encoded = record["snapshots"].get(name)
        return None if encoded is None else base64.b64decode(encoded, validate=True)

    def _capture_state(self, record: dict) -> bytes | None:
        """Use the same ledger bytes for the snapshot, the digest and the identity check."""
        path = core._state_path(self.root, record["task_id"])
        if path.is_symlink() or path.exists() and not path.is_file():
            raise ValueError("TASK_AUTHORITY_UNSAFE_PATH")
        try:
            raw = core.read_state_bytes(path)
        except FileNotFoundError:
            raw = None
        record["state_sha256"] = "ABSENT" if raw is None else hashlib.sha256(raw).hexdigest()
        record["snapshots"][path.relative_to(self.root).as_posix()] = None if raw is None else base64.b64encode(raw).decode()
        return raw

    def _write_with_pins(self, record: dict, previous: bytes | None, current: bytes | None) -> None:
        """Called under the archive lock. A failure can leave extra pins, never a new unpinned anchor."""
        location = str(self.path().resolve())
        key = "anchor-" + hashlib.sha256(os.path.normcase(location).encode("utf-8")).hexdigest()[:32]
        core.pin_anchor_segments(self.root, record["task_id"], key, [previous, current])
        self.write(record)
        try:
            core.pin_anchor_segments(self.root, record["task_id"], key, [current] if record["status"] == "ACTIVE" else [])
        except (OSError, ValueError):
            pass  # The previous and current snapshot segments are still pinned.

    def establish(self, state: dict, intent: dict, *, adapter_fields: dict | None = None) -> dict:
        intent = validate_contract(intent)
        fields = adapter_fields or {}
        if _CORE_OWNED_FIELDS & fields.keys():
            raise ValueError("TASK_AUTHORITY_IDENTITY_CHANGED")
        # Only an existing ACTIVE Core ledger can be anchored. No second task
        # state or host-specific task identity is created here.
        self.task_id = state["task_id"]
        with core._archive_gc_lock(self.root, self.task_id):
            record = {"version": 1, "project": str(self.root.resolve()), "task_id": self.task_id,
                      "goal": state["goal"], "contract": intent, "status": "ACTIVE",
                      "provenance": "SELECTED_TASK_INTENT",
                      "security": {name: digest(self.root / name) for name in self.protected_paths},
                      "history": [], **fields}
            record["snapshots"] = {name: base64.b64encode((self.root / name).read_bytes()).decode()
                                   if record["security"][name] != "ABSENT" else None for name in self.protected_paths}
            raw = self._capture_state(record)
            current = {} if raw is None else json.loads(raw)
            if current.get("task_id") != self.task_id or current.get("goal") != state["goal"] or current.get("status") != "ACTIVE":
                raise ValueError("TASK_AUTHORITY_IDENTITY_CHANGED")
            prior = self.read()
            if prior is not None:
                raise ValueError("TASK_AUTHORITY_ALREADY_ACTIVE" if prior["status"] == "ACTIVE" else "TASK_AUTHORITY_RETIRED_NO_REESTABLISH")
            self._write_with_pins(record, None, raw)
        return record

    def check(self, *, evidence: Mapping[str, tuple[Path, str]] | None = None) -> dict | None:
        record = self.read()
        if record is None:
            return None
        if record["status"] != "ACTIVE":
            if digest(core._state_path(self.root, self.task_id)) != record["state_sha256"]:
                raise ValueError("TASK_AUTHORITY_RETIRED_STATE_CHANGED")
            return None
        if digest(core._state_path(self.root, self.task_id)) != record["state_sha256"]:
            raise ValueError("TASK_AUTHORITY_STATE_CHANGED")
        if any(digest(self.root / name) != expected for name, expected in record["security"].items()):
            raise ValueError("TASK_AUTHORITY_SECURITY_CHANGED")
        state = json.loads(core._state_path(self.root, self.task_id).read_text(encoding="utf-8"))
        if state.get("task_id") != record["task_id"] or state.get("goal") != record["goal"] or state.get("status") != "ACTIVE":
            raise ValueError("TASK_AUTHORITY_IDENTITY_CHANGED")
        for field, (target, error) in (evidence or {}).items():
            # An adapter evidence digest that an older adapter or Core never recorded has nothing
            # to compare against; every digest the anchor does hold is compared exactly.
            if field in record and digest(target) != record[field]:
                raise ValueError(error)
        return record

    def checkpoint(self) -> None:
        """Anchor a checked ledger mutation, including DONE or deleted state.

        The task identity and selected contract are never changed. Deletion
        retires authority as ABANDONED; it does not prove task completion.
        """
        task_id = self.task_id or core.selected_task(self.root)
        if task_id is None:
            self.read()  # exact legacy anchor, if present
            task_id = self.task_id
        if task_id is None:
            return
        with core._archive_gc_lock(self.root, task_id):
            record = self.read()
            if record is None or record["status"] != "ACTIVE":
                return
            previous = self._state_snapshot(record)
            current = self._capture_state(record)
            if current is None:
                record["status"] = "ABANDONED"
            else:
                state = json.loads(current)
                if state["task_id"] != task_id or state["goal"] != record["goal"]:
                    raise ValueError("TASK_AUTHORITY_IDENTITY_CHANGED")
                record["status"] = state["status"]
            self._write_with_pins(record, previous, current)

    def switch_mode(self, expected: str, base_revision: int, mode: str, human_instruction: str) -> dict:
        """Apply an adapter-authorized selection; all other intent stays frozen.

        The CAS prevents a stale Controller decision changing a newer contract.
        Native descendants are observed/handled by the adapter before calling.
        """
        if mode not in MODES or not isinstance(human_instruction, str) or not human_instruction.strip() or len(human_instruction) > 16384:
            raise ValueError("TASK_AUTHORITY_MODE_SELECTION_REQUIRED")
        with core._lock(self.root):
            if digest(self.path()) != expected:
                raise ValueError("TASK_AUTHORITY_CHANGED")
            record = self.check()
            if record is None:
                raise ValueError("TASK_AUTHORITY_NOT_ACTIVE")
            state = core._load_state(self.root, active=True)
            if state["task_id"] != record["task_id"]:
                raise core.ThalirisError(core.errors.TASK_IDENTITY_CONFLICT, "task revision conflict",
                                         details={"expected_task_id": record["task_id"], "task_id": state["task_id"]})
            core.check_revision(state, base_revision)
            record.setdefault("mode_history", []).append({"execution_mode": record["contract"]["execution_mode"],
                "human_instruction": human_instruction, "revision": base_revision})
            record["contract"] = {**record["contract"], "execution_mode": mode}
            previous = self._state_snapshot(record)
            state["revision"] += 1
            core._write_state(self.root, state)
            with core._archive_gc_lock(self.root, record["task_id"]):
                self._write_with_pins(record, previous, self._capture_state(record))
        return {"ok": True, "task_id": record["task_id"], "revision": state["revision"], "execution_mode": mode}

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
                try:
                    restored[name] = None if encoded is None else base64.b64decode(encoded, validate=True)
                except (TypeError, ValueError) as exc:
                    raise core.ThalirisError(
                        core.errors.TASK_AUTHORITY_INVALID, "TASK_AUTHORITY_INVALID",
                        recovery="a recorded snapshot is not valid base64; nothing was restored",
                        details={"reason": "snapshot is not valid base64", "path": name}) from exc
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
            with core._archive_gc_lock(self.root, record["task_id"]):
                self._write_with_pins(record, None, self._state_snapshot(record))
            self.check(evidence=checks)
        return {"ok": True, "status": "TASK_AUTHORITY_RECOVERED", "task_id": record["task_id"],
                "authority_provenance": record.get("provenance")}
