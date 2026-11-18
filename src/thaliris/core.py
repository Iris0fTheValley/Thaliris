"""Git-native Markdown operations; adapters never decide correctness."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import base64
import copy
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import math
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import uuid

if os.name == "nt":
    import ctypes
    import msvcrt
    from ctypes import wintypes

    class _Overlapped(ctypes.Structure):
        _fields_ = [
            ("Internal", ctypes.c_void_p),
            ("InternalHigh", ctypes.c_void_p),
            ("Offset", wintypes.DWORD),
            ("OffsetHigh", wintypes.DWORD),
            ("hEvent", wintypes.HANDLE),
        ]

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.LockFileEx.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
                                     wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(_Overlapped)]
    _kernel32.LockFileEx.restype = wintypes.BOOL
    _kernel32.UnlockFileEx.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                       wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(_Overlapped)]
    _kernel32.UnlockFileEx.restype = wintypes.BOOL

from . import errors as _errors
from .errors import ThalirisError, error_envelope
from .claims import CLAIM_BASES, CLAIM_BLOCK_INFO, CLAIM_POLARITIES, CLAIMS_MAX, CLAIM_TEXT_MAX, parse_claim_block

errors = _errors
from .markdown import Entry, durable_descriptors, evidence_status, freshness_detail_budget_placeholder, parse, parse_text
from .models import ContextConfig

# Every Git call Core makes (some under the repository lock) is bounded, so one stuck Git
# cannot block that repository's tasks indefinitely. Same bound as identity_basis.
GIT_TIMEOUT_SECONDS = 60

IGNORE_START = "# thaliris:begin"
IGNORE_END = "# thaliris:end"
IGNORE_RULES = (
    ".context/backups/",
    ".context/recovery/",
    ".context/state.json",
    ".context/tasks/",
    ".context/context.lock",
)

def _safe(root: Path, relative: str) -> Path:
    if not relative or Path(relative).is_absolute():
        raise ValueError("path escapes repository")
    target = (root / relative).resolve(strict=False)
    try:
        target.relative_to(root.resolve(strict=True))
    except ValueError as exc:
        raise ValueError("path escapes repository") from exc
    return target


def _digest(data: bytes | None) -> str | None:
    return hashlib.sha256(data).hexdigest() if data is not None else None


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_root(root: Path) -> Path | None:
    """Return an established Git root, None for a proven non-Git directory.

    An unavailable Git executable remains optional for ordinary directories.
    Existing repository metadata or an unexpected discovery failure stays
    UNKNOWN so callers cannot silently adopt a different managed identity.
    """
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("--root must be an existing directory")

    def entry_kind(target: Path, *, directory: bool) -> bool:
        try:
            mode = target.stat().st_mode
        except FileNotFoundError:
            return False
        except OSError as exc:
            raise ValueError("Git metadata status is UNKNOWN; refusing to select a managed root") from exc
        return stat.S_ISDIR(mode) if directory else stat.S_ISREG(mode)

    metadata = (
        entry_kind(root / "HEAD", directory=False)
        and entry_kind(root / "config", directory=False)
        and entry_kind(root / "objects", directory=True)
    )
    current = root
    while True:
        marker = current / ".git"
        try:
            marker.lstat()
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise ValueError("Git metadata status is UNKNOWN; refusing to select a managed root") from exc
        else:
            metadata = True
            break
        if current == current.parent:
            break
        current = current.parent

    discovery_environment = any(
        os.environ.get(name) for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR")
    )
    try:
        # Git prints paths as UTF-8 regardless of the console code page. Decode
        # explicitly (not via the locale) so non-ASCII roots survive on Windows;
        # surrogateescape keeps undecodable POSIX bytes round-trippable.
        proc = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=root, capture_output=True,
                              text=True, encoding="utf-8", errors="surrogateescape", check=False,
                              timeout=GIT_TIMEOUT_SECONDS)
    except FileNotFoundError as exc:
        missing_program = exc.filename is None or Path(exc.filename).name.casefold() in {"git", "git.exe"}
        if missing_program and root.is_dir() and not metadata and not discovery_environment:
            return None
        raise ValueError("Git root discovery is UNKNOWN; refusing to select a managed root") from exc
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError("Git root discovery is UNKNOWN; refusing to select a managed root") from exc
    if proc.returncode == 0 and proc.stdout.strip():
        return Path(proc.stdout.strip()).resolve()
    if (
        proc.returncode != 0
        and not metadata
        and not discovery_environment
        and "not a git repository" in (proc.stderr or "").casefold()
    ):
        return None
    raise ValueError("Git root discovery is UNKNOWN; refusing to select a managed root")


def _repo_root(root: Path) -> Path:
    """Validate an explicit managed directory, retaining Git root semantics."""
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("--root must be an existing directory")
    actual = _git_root(root)
    if actual is not None and root != actual:
        raise ValueError("--root must be the git repository root")
    return root


@contextmanager
def _lock(root: Path):
    """Serialize context operations until the current holder releases the lock."""
    with _file_lock(_safe(root, ".context/context.lock")):
        yield


@contextmanager
def _file_lock(path: Path):
    """Hold an exclusive OS lock on ``path`` (created if needed) until release."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    acquired = False
    overlap = None
    try:
        if os.name == "nt":
            overlap = _Overlapped()
            os_handle = wintypes.HANDLE(msvcrt.get_osfhandle(handle.fileno()))
            if not _kernel32.LockFileEx(os_handle, 0x2, 0, 1, 0, ctypes.byref(overlap)):
                raise ctypes.WinError(ctypes.get_last_error())
            acquired = True
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            acquired = True
        yield
    finally:
        try:
            if acquired and os.name == "nt":
                if not _kernel32.UnlockFileEx(os_handle, 0, 1, 0, ctypes.byref(overlap)):
                    raise ctypes.WinError(ctypes.get_last_error())
            elif acquired:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally: handle.close()


def _atomic_write(target: Path, content: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, target)
    except BaseException:
        try: os.unlink(temporary)
        except FileNotFoundError: pass
        raise


def _apply_with_backup(root: Path, writes: dict[str, bytes], deletes: list[str], action: str) -> str:
    changes: list[dict[str, str | None]] = []
    for relative in sorted(set(writes) | set(deletes)):
        target = _safe(root, relative)
        old = target.read_bytes() if target.is_file() else None
        changes.append({"path": relative, "old": base64.b64encode(old).decode() if old is not None else None,
                        "old_hash": _digest(old), "written_hash": _digest(writes.get(relative))})
    backup_id = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}"
    backup = {"version": 1, "action": action, "created_at": datetime.now(timezone.utc).isoformat(), "changes": changes}
    _atomic_write(_safe(root, f".context/backups/{backup_id}.json"), (json.dumps(backup, sort_keys=True, indent=2) + "\n").encode())
    by_path = {str(change["path"]): change for change in changes}
    applied: list[str] = []
    try:
        for relative, content in writes.items():
            _atomic_write(_safe(root, relative), content)
            applied.append(relative)
        for relative in deletes:
            _safe(root, relative).unlink()
            applied.append(relative)
    except BaseException as mutation_error:
        conflicts: list[str] = []
        for relative in reversed(applied):
            change = by_path[relative]
            target = _safe(root, relative)
            current = target.read_bytes() if target.is_file() else None
            if _digest(current) != change.get("written_hash"):
                conflicts.append(relative)
                continue
            old = change.get("old")
            if old is None:
                target.unlink(missing_ok=True)
            else:
                _atomic_write(target, base64.b64decode(old))
        if conflicts:
            raise OSError(f"mutation failed; recovery conflict; backup={backup_id}; paths={','.join(conflicts)}") from mutation_error
        raise
    return backup_id


def _entry(title: str, body: str, *, evidence: str = "NONE") -> bytes:
    for field, value, maximum in (
        ("title", title, 300),
        ("evidence", evidence, 65_536),
    ):
        if not isinstance(value, str) or not value.strip() or len(value) > maximum or "\n" in value or "\r" in value:
            raise ValueError(f"invalid durable {field}")
    if not isinstance(body, str):
        raise ValueError("invalid durable body")
    rendered = f"---\nEvidence: {evidence}\nRevision: 1\n---\n\n# {title}\n\n{body}\n"
    parse_text(rendered)
    return rendered.encode()


def _template_files() -> dict[str, bytes]:
    return {
        ".agent-memory/INDEX.md": _entry(
            "Durable memory index",
            "Maintain a thin global map here. The model chooses directory names, hierarchy, and document links.",
        ),
        ".milestones/INDEX.md": _entry(
            "Milestone index",
            "Maintain a thin global milestone map here. The model chooses its structure and links.",
        ),
    }


def _managed_span(current: str, start_marker: str, end_marker: str, label: str) -> tuple[int, int] | None:
    counts = current.count(start_marker), current.count(end_marker)
    if counts == (0, 0):
        return None
    if counts == (1, 1):
        start, end_start = current.index(start_marker), current.index(end_marker)
        end = end_start + len(end_marker)
    else:
        raise ValueError(f"{label} has duplicate or damaged managed markers")
    if start >= end_start:
        raise ValueError(f"{label} has duplicate or damaged managed markers")
    return start, end


def _managed_gitignore(current: str) -> str:
    span = _managed_span(current, IGNORE_START, IGNORE_END, ".gitignore")
    if span is None and set(IGNORE_RULES) <= set(current.splitlines()): return current
    newline = "\r\n" if "\r\n" in current else "\n"
    block = newline.join((IGNORE_START, *IGNORE_RULES, IGNORE_END)) + newline
    if span is None:
        separator = "" if not current or current.endswith(("\n", "\r")) else newline
        return current + separator + block
    start, end = span
    suffix = current[end:]
    if suffix.startswith("\r\n"): suffix = suffix[2:]
    elif suffix.startswith("\n"): suffix = suffix[1:]
    return current[:start] + block + suffix


def _init_plan(root: Path) -> tuple[dict[str, bytes], list[str]]:
    root = _repo_root(root)
    # Validate before creating even the operational lock file: corrupt markers
    # must fail without a tool-owned filesystem mutation.
    pre_ignore = _safe(root, ".gitignore")
    _managed_gitignore(pre_ignore.read_bytes().decode("utf-8") if pre_ignore.exists() else "")
    files = {path: content for path, content in _template_files().items() if not _safe(root, path).exists()}
    manual: list[str] = []
    ignore = _safe(root, ".gitignore"); current_ignore = ignore.read_bytes().decode("utf-8") if ignore.exists() else ""
    rendered_ignore = _managed_gitignore(current_ignore)
    if current_ignore != rendered_ignore: files[".gitignore"] = rendered_ignore.encode()
    if not _safe(root, ".context/config.json").exists(): files[".context/config.json"] = ContextConfig().write(root)
    return files, manual


def init(root: Path) -> dict[str, object]:
    root = _repo_root(root)
    _init_plan(root)
    with _lock(root):
        files, manual = _init_plan(root)
        if not files: return {"ok": True, "changed": False, "backup": None, "manual_action_required": manual}
        return {"ok": True, "changed": True, "backup": _apply_with_backup(root, files, [], "init"), "files": sorted(files), "manual_action_required": manual}


# Project identity history is append-only: its backups preserve prior bytes as
# recovery evidence, never as a replayable undo (see thaliris.identity).
_IDENTITY_BACKUP_PREFIX = "identity-"


def rollback(root: Path, backup_id: str) -> dict[str, object]:
    root = _repo_root(root)
    if not re.fullmatch(r"[0-9TZ-]+-[0-9a-f]{8}", backup_id): raise ValueError("invalid backup id")
    with _lock(root):
        path = _safe(root, f".context/backups/{backup_id}.json")
        if not path.is_file(): raise ValueError("backup not found")
        data = json.loads(path.read_text(encoding="utf-8")); guarded = []; applied = []
        if isinstance(data, dict) and str(data.get("action", "")).startswith(_IDENTITY_BACKUP_PREFIX):
            raise ValueError("backup was produced by a project identity mutation; rollback refuses it. "
                             "Reverse an identity change with a new amendment, a challenge dismissal or a relation retraction")
        for change in data.get("changes", []):
            target = _safe(root, str(change["path"])); now = target.read_bytes() if target.is_file() else None
            current_hash = _digest(now)
            if current_hash == change.get("old_hash"):
                continue
            if current_hash == change.get("written_hash"):
                applied.append(change)
                continue
            guarded.append(str(change["path"]))
        if guarded: return {"ok": False, "rolled_back": False, "guarded": guarded}
        writes, deletes = {}, []
        for change in applied:
            if change.get("old") is None: deletes.append(str(change["path"]))
            else: writes[str(change["path"])] = base64.b64decode(change["old"])
        backup = _apply_with_backup(root, writes, deletes, "rollback") if writes or deletes else None
        return {"ok": True, "rolled_back": True, "backup": backup, "deleted": deletes}


def _uninstall_plan(root: Path) -> tuple[dict[str, bytes], list[str], list[str], list[str]]:
    root = _repo_root(root)
    # Validate before acquiring the operational lock: corrupt markers must fail
    # without creating the tool-owned .context directory or lock file.
    pre_ignore = _safe(root, ".gitignore")
    if pre_ignore.is_file():
        current = pre_ignore.read_bytes().decode("utf-8")
        _managed_span(current, IGNORE_START, IGNORE_END, ".gitignore")
    private_state_present = any(
        (_safe(root, relative).is_file() or _safe(root, relative).is_dir())
        for relative in (".context/backups", ".context/state.json", ".context/context.lock")
    )
    writes: dict[str, bytes] = {}; deletes: list[str] = []; kept: list[str] = []; manual: list[str] = []
    ignore = _safe(root, ".gitignore")
    if ignore.is_file() and not private_state_present:
        current = ignore.read_bytes().decode("utf-8")
        span = _managed_span(current, IGNORE_START, IGNORE_END, ".gitignore")
        if span is not None:
            start, end = span
            suffix = current[end:]
            if suffix.startswith("\r\n"): suffix = suffix[2:]
            elif suffix.startswith("\n"): suffix = suffix[1:]
            stripped = current[:start] + suffix
            if stripped: writes[".gitignore"] = stripped.encode()
            else: deletes.append(".gitignore")
    expected = _template_files() | {".context/config.json": ContextConfig().write(root)}
    for relative, template in expected.items():
        target = _safe(root, relative)
        if not target.is_file(): continue
        if _digest(target.read_bytes()) == _digest(template): deletes.append(relative)
        else: kept.append(relative)
    return writes, deletes, kept, manual


def uninstall(root: Path) -> dict[str, object]:
    root = _repo_root(root)
    with _lock(root):
        writes, deletes, kept, manual = _uninstall_plan(root)
        if not writes and not deletes: return {"ok": True, "changed": False, "kept": sorted(set(kept)), "backup": None, "manual_action_required": manual}
        return {"ok": True, "changed": True, "kept": sorted(set(kept)), "backup": _apply_with_backup(root, writes, deletes, "uninstall"), "deleted": sorted(deletes), "manual_action_required": manual}


def entries(root: Path) -> list[Entry]:
    base = root / ".agent-memory"
    return [parse(path) for path in sorted(base.rglob("*.md")) if not path.is_symlink()] if base.exists() else []


def stale(root: Path) -> dict[str, object]:
    result = []
    for entry in entries(root):
        state, details = evidence_status(entry, root)
        result.append({"path": str(entry.path.relative_to(root)).replace("\\", "/"), "state": state, "detail": details})
    return {"ok": True, "entries": result, "not_fresh": sum(x["state"] in {"CHANGED", "MISSING"} for x in result)}


# Task state is a mechanical ledger. Models author record labels and interpret
# them; Core validates only shape, identity, references, bounds, and CAS.
_STATE_NAME = ".context/state.json"
# Schema history. 7 is the oldest on-disk shape this Core reads as-is; 8 added Controller-local
# provenance, 9 the verification-first ledger (declared checks and their run results, requirement
# kinds, typed claims, handoff usage and gate overrides), 10 compact serialization with hot/cold
# archive segments (``archive`` index and ``archived`` stubs), and 11 full eviction of settled objects
# (eviction entries in ``archive`` and the ``settled`` table). Every earlier supported schema is a
# valid subset of the next one, so promotion is a forward chain (``_COMPATIBLE_PRIOR_SCHEMAS``): a
# state is read as the current schema in memory and is written as the current schema on its next
# write. Only a schema newer than this code is refused (``STATE_SCHEMA_INCOMPATIBLE``: upgrade Core).
_BASE_SCHEMA_VERSION = 7
_CONTROLLER_LOCAL_SCHEMA_VERSION = 8
_VERIFICATION_SCHEMA_VERSION = 9
_ARCHIVE_SCHEMA_VERSION = 10
_EVICTION_SCHEMA_VERSION = 11
_STATE_SCHEMA_VERSION = _EVICTION_SCHEMA_VERSION  # the current schema; every write produces it
_SUPPORTED_SCHEMAS = (_BASE_SCHEMA_VERSION, _CONTROLLER_LOCAL_SCHEMA_VERSION, _VERIFICATION_SCHEMA_VERSION,
                      _ARCHIVE_SCHEMA_VERSION, _EVICTION_SCHEMA_VERSION)
_SCHEMA9_STATE_FIELDS = {"checks", "closure"}
_SCHEMA10_STATE_FIELDS = {"archive"}
_SCHEMA11_STATE_FIELDS = {"settled"}
_SCHEMA9_CONTINUITY_FIELDS = {
    "requirements": {"kind", "surface"},
    "handoffs": {"claims", "usage"},
    "observations": {"claim", "mechanism"},
    "judgments": {"override_reason", "overridden_checks"},
}
ROUTING_STATE_MAX_BYTES = 8 * 1024
# The hot ledger file (``state.json``) never exceeds this many bytes. Adapters read the bound from
# ``task_state_capacity()`` / ``read_state_bytes()`` instead of hard-coding it.
STATE_MAX_BYTES = 512 * 1024
# Eviction (see "Hot/cold archive" below) runs inside a write whose serialized hot state would exceed
# this high-water mark (70% of the cap), or whose hot list would exceed or approach its item cap.
STATE_ARCHIVE_HIGH_WATER_BYTES = (STATE_MAX_BYTES * 7) // 10
# Below the cap, an eviction pass is committed only when it frees at least this much, so a ledger whose
# hot part is mostly open evidence does not write a tiny segment on every write. At or over the cap any
# saving counts.
STATE_ARCHIVE_MIN_SAVINGS_BYTES = 16 * 1024
# Item caps of ledger lists. Hot items count against ``STATE_LIST_MAX``; a schema-10 archived stub does
# not, but a list holds at most ``STATE_ARCHIVED_LIST_MAX`` items in total (the byte cap binds first).
# Requirements are never evicted, so their list is capped at ``STATE_ARCHIVED_LIST_MAX``. Evicted
# objects (ids in the archive index) count toward no list cap.
STATE_LIST_MAX = 512
STATE_ARCHIVED_LIST_MAX = 8192
EXPLICIT_DOCUMENT_MAX_BYTES = 64 * 1024
DURABLE_INDEX_RECOMMENDED_BYTES = 3 * 1024
DURABLE_INDEX_HARD_MAX_BYTES = 16 * 1024
SURFACE_MAX_ENTRIES = 512
SURFACE_MAX_BYTES = 128 * 1024
SURFACE_MAX_FILE_BYTES = 4 * 1024 * 1024
SURFACE_MAX_TOTAL_FILE_BYTES = 16 * 1024 * 1024
_STATE_FIELDS = {
    "schema_version", "revision", "task_id", "status", "goal", "current_milestone",
    "records", "active_work", "pending_results", "artifact_refs", "evidence_refs",
    "verification_results", "task_surface_baseline", "task_base_head",
}
_RECORD_FIELDS = {"id", "kind", "text", "producer", "revision", "source_refs", "status", "supersedes"}


def _promote_state_6_to_7(raw: dict[str, object]) -> dict[str, object]:
    """6 -> 7 only widened ``task_surface_baseline`` (it may be the string "UNAVAILABLE"); no field changed."""
    return {**raw, "schema_version": 7}


def _promote_by_version(target: int):
    """A step whose new schema only adds optional content: the old shape is valid as it is."""
    def step(raw: dict[str, object]) -> dict[str, object]:
        return {**raw, "schema_version": target}
    step.__name__ = f"_promote_state_to_{target}"
    return step


# Earlier on-disk schema versions this Core reads, mapped to the step that lifts a state by one
# version. The chain runs up to the current schema, so every listed version is read as the current
# schema in memory only and becomes the current version on its next write. Add an entry only when the
# old shape is valid under the next version's rules (or the step makes it so); versions below the
# first key and states that do not validate stay refused with the schema-mismatch diagnostic. The
# disk is never touched by reading, so external byte digests (authority anchors) are unaffected.
_COMPATIBLE_PRIOR_SCHEMAS = {
    6: _promote_state_6_to_7,
    _BASE_SCHEMA_VERSION: _promote_by_version(_CONTROLLER_LOCAL_SCHEMA_VERSION),
    _CONTROLLER_LOCAL_SCHEMA_VERSION: _promote_by_version(_VERIFICATION_SCHEMA_VERSION),
    _VERIFICATION_SCHEMA_VERSION: _promote_by_version(_ARCHIVE_SCHEMA_VERSION),
    _ARCHIVE_SCHEMA_VERSION: _promote_by_version(_EVICTION_SCHEMA_VERSION),
}


def _promoted_prior_state(root: Path, raw: object) -> dict[str, object] | None:
    """The validated current-schema form of a compatible older state, else None (refuse as before).

    The state is validated once, at the first supported version the chain reaches (its own version
    for 7-9, so version-specific rules still hold for the bytes on disk), then lifted to the current
    schema. Lifting only changes ``schema_version``.
    """
    if not isinstance(raw, dict) or type(raw.get("schema_version")) is not int:
        return None
    version = raw["schema_version"]
    if version >= _STATE_SCHEMA_VERSION or any(step not in _COMPATIBLE_PRIOR_SCHEMAS for step in range(version, _STATE_SCHEMA_VERSION)):
        return None
    lifted: dict[str, object] = raw
    validated = False
    try:
        for step in range(version, _STATE_SCHEMA_VERSION):
            if not validated and step in _SUPPORTED_SCHEMAS:
                _validate_state(root, lifted)
                validated = True
            lifted = _COMPATIBLE_PRIOR_SCHEMAS[step](lifted)
        if not validated:
            _validate_state(root, lifted)
    except ValueError:
        return None
    return lifted


class TaskStateSchemaIncompatible(ValueError):
    """An older or newer task ledger needs an explicit recovery decision."""

    def __init__(self, diagnostic: dict[str, object], task_id: str | None = None) -> None:
        self.diagnostic = diagnostic
        self.task_id = task_id
        super().__init__("invalid task state schema")


_selected_tasks: ContextVar[dict[str, str]] = ContextVar("thaliris_selected_tasks", default={})
_legacy_tasks: ContextVar[dict[str, str]] = ContextVar("thaliris_legacy_tasks", default={})


def _selection_key(root: Path) -> str:
    key = str(root.resolve())
    return key.casefold() if os.name == "nt" else key


def remember_legacy_task(root: Path, task_id: str) -> None:
    """Retain an exact legacy location learned from ledger/anchor evidence."""
    known = dict(_legacy_tasks.get())
    known[_selection_key(root)] = task_id
    _legacy_tasks.set(known)


def select_task(root: Path, task_id: str | None) -> None:
    """Select an opaque task explicitly for this operation context.

    Selection is navigation, not authorization, and is never persisted as a
    workspace-wide current task. Adapters associate their own session facts.
    """
    selected = dict(_selected_tasks.get())
    key = _selection_key(root)
    if task_id is None:
        selected.pop(key, None)
    else:
        if not isinstance(task_id, str) or str(uuid.UUID(task_id)) != task_id:
            raise ValueError("invalid task id")
        selected[key] = task_id
    _selected_tasks.set(selected)


def selected_task(root: Path) -> str | None:
    return _selected_tasks.get().get(_selection_key(root))


def _state_path(root: Path, task_id: str | None = None) -> Path:
    task_id = task_id or selected_task(root)
    legacy = root / _STATE_NAME
    if task_id is None:
        # Legacy navigation is available for explicit diagnostics only. Native
        # adapters must not infer a session association from this fallback.
        return legacy
    if str(uuid.UUID(task_id)) != task_id:
        raise ValueError("invalid task id")
    indexed = _safe_without_final_symlink(root, f".context/tasks/{task_id}/state.json")
    if indexed.exists():
        return indexed
    if _legacy_tasks.get().get(_selection_key(root)) == task_id:
        return legacy
    if legacy.is_file():
        try:
            if json.loads(legacy.read_text(encoding="utf-8")).get("task_id") == task_id:
                remember_legacy_task(root, task_id)
                return legacy
        except (OSError, ValueError, AttributeError):
            pass
    return indexed


def _task_state_schema_diagnostic(raw: object, raw_bytes: bytes) -> dict[str, object] | None:
    """Classify schema-version mismatch without migrating or mutating it."""
    if not isinstance(raw, dict):
        return None
    version = raw.get("schema_version")
    if type(version) is not int or version in _SUPPORTED_SCHEMAS:
        return None
    task_id = raw.get("task_id")
    try:
        uuid.UUID(str(task_id))
        valid_task_id = isinstance(task_id, str)
    except (ValueError, AttributeError, TypeError):
        valid_task_id = False
    status = raw.get("status")
    older_supported_for_archive = 0 < version < _BASE_SCHEMA_VERSION
    recoverable = older_supported_for_archive and valid_task_id and (status == "ACTIVE" or status == "DONE")
    newer = version > _STATE_SCHEMA_VERSION
    digest = hashlib.sha256(raw_bytes).hexdigest()
    action = "NONE"
    if recoverable:
        action = f"use the adapter's task-state recovery procedure with expected sha256 {digest}"
    elif newer:
        action = (f"upgrade Thaliris Core (and the adapter that bundles it) to a release that reads task state schema "
                  f"{version}; this Core reads schemas up to {_STATE_SCHEMA_VERSION}; the state is unchanged")
    return {
        "ok": False,
        "status": "STATE_SCHEMA_INCOMPATIBLE",
        "error": "invalid task state schema",
        "from_version": version,
        "to_version": _STATE_SCHEMA_VERSION,
        "state_sha256": digest,
        "recoverable": recoverable,
        "abandon_active_confirmation_required": status == "ACTIVE" and recoverable,
        "upgrade_required": newer,
        "recovery_action": action,
    }


def task_state_schema_diagnostic(root: Path) -> dict[str, object] | None:
    """Read a bounded schema mismatch diagnostic without loading task content."""
    root = _repo_root(root)
    if (root / _STATE_NAME).is_symlink():
        return None
    path = _state_path(root)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > STATE_MAX_BYTES:
        return None
    try:
        with path.open("rb") as stream:
            raw_bytes = stream.read(STATE_MAX_BYTES + 1)
        if len(raw_bytes) > STATE_MAX_BYTES:
            return None
        raw = json.loads(raw_bytes.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if _promoted_prior_state(root, raw) is not None:
        return None
    return _task_state_schema_diagnostic(raw, raw_bytes)


def _state_ignored(root: Path) -> bool:
    try:
        return subprocess.run(["git", "check-ignore", "-q", "--", _STATE_NAME], cwd=root, check=False,
                              timeout=GIT_TIMEOUT_SECONDS).returncode == 0
    except subprocess.TimeoutExpired as exc:
        raise ValueError("whether the task state is ignored is UNKNOWN: git check-ignore timed out") from exc


def _capacity_error(field: str, limit: int, count: int, *, unit: str = "entries", message: str | None = None,
                    recovery: str | None = None) -> ThalirisError:
    """The stable, field-naming refusal for a full bounded ledger list or file."""
    return ThalirisError(
        _errors.TASK_STATE_CAPACITY_EXCEEDED,
        message or f"state list exceeds limit: {field} holds at most {limit} {unit}, this write needs {count}",
        recovery=recovery or (
            f"the task state is unchanged; other lists stay writable and task-close still works; to keep recording "
            f"{field}, close this task and start a new one that cites this Task ID"),
        details={"field": field, "limit": limit, "count": count, "unit": unit},
    )


# Control characters other than tab and newline (refused in ledger text), and all of them.
_CONTROL_CHARACTERS = re.compile("[\x00-\x08\x0b-\x1f]")
_ALL_CONTROL_CHARACTERS = re.compile("[\x00-\x1f]")


def _check_json(value: object, field: str = "state") -> None:
    """Shape and size check; ``field`` is the nearest enclosing object key, named in capacity errors."""
    if isinstance(value, str):
        if len(value) > 16_384 or _CONTROL_CHARACTERS.search(value):
            raise ValueError("state contains control characters or oversized text")
    elif isinstance(value, list):
        # An archived stub (a Core-written object carrying ``archived``) does not count toward the
        # hot item cap; the whole list stays bounded by STATE_ARCHIVED_LIST_MAX. Requirements are
        # never evicted and are capped at STATE_ARCHIVED_LIST_MAX.
        if len(value) > STATE_LIST_MAX:
            hot = sum(not (isinstance(item, dict) and "archived" in item) for item in value)
            limit = STATE_ARCHIVED_LIST_MAX if field == "requirements" else STATE_LIST_MAX
            if hot > limit:
                raise _capacity_error(field, limit, hot)
            if len(value) > STATE_ARCHIVED_LIST_MAX:
                raise _capacity_error(field, STATE_ARCHIVED_LIST_MAX, len(value), unit="entries including archived stubs")
        for item in value:
            _check_json(item, field)
    elif isinstance(value, dict):
        if len(value) > 64:
            raise ValueError("state object exceeds limit")
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("state keys must be strings")
            _check_json(item, key)
    elif value is not None and type(value) not in {int, bool, float}:
        raise ValueError("state contains unsupported JSON value")


def _bounded_label(value: object, field: str, maximum: int = 64) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum or not re.fullmatch(r"[A-Za-z0-9_.:-]+", value):
        raise ValueError(f"invalid {field}")
    return value


def _valid_relative(root: Path, value: object) -> str:
    if not isinstance(value, str) or "\\" in value or not value or value.startswith("/") or any(part in {"", ".", ".."} for part in value.split("/")):
        raise ValueError("path must be normalized POSIX repo-relative")
    target = root.joinpath(*value.split("/"))
    parent = root
    for part in value.split("/")[:-1]:
        parent = parent / part
        if parent.is_symlink():
            raise ValueError("path traverses a symlink")
    return value


def _safe_without_final_symlink(root: Path, relative: str) -> Path:
    """Resolve a validated path only after rejecting a symlink final component."""
    normalized = _valid_relative(root, relative)
    lexical = root.joinpath(*normalized.split("/"))
    if lexical.is_symlink():
        raise ValueError("path final component must not be a symlink")
    return _safe(root, normalized)


def _surface_identity(root: Path, path: str, status: str) -> dict[str, object]:
    raw = root.joinpath(*path.split("/"))
    if raw.is_symlink():
        try:
            link = os.readlink(raw)
        except OSError:
            link = ""
        return {"path": path, "state": "SYMLINK", "identity": _digest(link.encode("utf-8")), "mode": raw.lstat().st_mode & 0o7777, "git_status": status}
    if not raw.exists():
        return {"path": path, "state": "MISSING", "identity": None, "mode": None, "git_status": status}
    if not raw.is_file():
        return {"path": path, "state": "SPECIAL", "identity": None, "mode": raw.lstat().st_mode & 0o7777, "git_status": status}
    return {"path": path, "state": "FILE", "identity": _file_digest(raw), "mode": raw.stat().st_mode & 0o7777, "git_status": status}


def _surface_snapshot(root: Path) -> list[dict[str, object]] | str:
    try:
        proc = subprocess.run(["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"], cwd=root, capture_output=True, check=False,
                              timeout=GIT_TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError):  # includes TimeoutExpired: the surface stays UNAVAILABLE
        return "UNAVAILABLE"
    if proc.returncode or not isinstance(proc.stdout, bytes) or len(proc.stdout) > SURFACE_MAX_BYTES:
        return "UNAVAILABLE"
    fields = proc.stdout.decode("utf-8", errors="surrogateescape").split("\0")
    result: list[dict[str, object]] = []
    total_file_bytes = 0
    index = 0
    while index < len(fields):
        item = fields[index]
        index += 1
        if not item:
            continue
        status, path = item[:2], item[3:].replace("\\", "/")
        if status[:1] in {"R", "C"} and index < len(fields):
            # Porcelain -z reports the current/destination path in this item
            # and the source/old path in the following field.
            index += 1
        if len(result) >= SURFACE_MAX_ENTRIES:
            return "UNAVAILABLE"
        _valid_relative(root, path)
        raw = root.joinpath(*path.split("/"))
        if not raw.is_symlink() and raw.is_file():
            size = os.stat(raw).st_size
            total_file_bytes += size
            if size > SURFACE_MAX_FILE_BYTES or total_file_bytes > SURFACE_MAX_TOTAL_FILE_BYTES:
                return "UNAVAILABLE"
        result.append(_surface_identity(root, path, status))
    return sorted(result, key=lambda item: str(item["path"]))


def _surface_delta(root: Path, baseline: list[dict[str, object]] | str) -> dict[str, object]:
    current = _surface_snapshot(root)
    if baseline == "UNAVAILABLE" or current == "UNAVAILABLE":
        return {"status": "UNAVAILABLE", "before": baseline, "after": current, "paths": None}
    before = {str(item["path"]): item for item in baseline}
    after = {str(item["path"]): item for item in current}
    paths = sorted(path for path in set(before) | set(after) if before.get(path) != after.get(path))
    return {"status": "AVAILABLE", "before": [before[path] for path in paths if path in before], "after": [after[path] for path in paths if path in after], "paths": paths}


def _git_head(root: Path) -> str | None:
    try:
        proc = subprocess.run(["git", "rev-parse", "--verify", "HEAD"], cwd=root, capture_output=True,
                              text=True, encoding="utf-8", errors="replace", check=False,
                              timeout=GIT_TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError):  # includes TimeoutExpired: HEAD stays unknown
        return None
    value = proc.stdout.strip().lower()
    return value if proc.returncode == 0 and re.fullmatch(r"[0-9a-f]{40,64}", value) else None


def _record(value: object, source_ids: set[str], record_ids: set[str], *, stored: bool = False) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) - ({"archived"} if stored else set()) != _RECORD_FIELDS:
        raise ValueError("invalid task record")
    identifier = _bounded_label(value.get("id"), "record id")
    if identifier in record_ids:
        raise ValueError("duplicate task record id")
    _bounded_label(value.get("kind"), "record kind")
    _bounded_label(value.get("producer"), "record producer")
    _bounded_label(value.get("status"), "record status")
    text = value.get("text")
    if not isinstance(text, str) or not text.strip() or len(text) > 16_384:
        raise ValueError("invalid task record text")
    if type(value.get("revision")) is not int or value["revision"] < 1:
        raise ValueError("invalid task record revision")
    refs = value.get("source_refs")
    supersedes = value.get("supersedes")
    if not isinstance(refs, list) or len(refs) > 64 or not all(isinstance(ref, str) and ref in source_ids for ref in refs):
        raise ValueError("invalid task record source refs")
    if not isinstance(supersedes, list) or len(supersedes) > 64 or len(set(supersedes)) != len(supersedes) or identifier in supersedes or not all(isinstance(item, str) and item in record_ids for item in supersedes):
        raise ValueError("invalid task record supersedes")
    return value


def _evidence_ref(value: object, ids: set[str], *, stored: bool = False) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("invalid source reference")
    allowed = {"id", "kind", "locator", "summary", "confidence", "source_refs"} | ({"archived"} if stored else set())
    if set(value) - allowed or not {"id", "kind", "locator", "summary"} <= set(value):
        raise ValueError("invalid source reference")
    identifier = _bounded_label(value.get("id"), "source id")
    _bounded_label(value.get("kind"), "source kind")
    if identifier in ids:
        raise ValueError("duplicate source reference id")
    if not isinstance(value.get("locator"), str) or not value["locator"] or len(value["locator"]) > 4096:
        raise ValueError("invalid source locator")
    if not isinstance(value.get("summary"), str) or len(value["summary"]) > 4096:
        raise ValueError("invalid source summary")
    if "confidence" in value and (not isinstance(value["confidence"], str) or len(value["confidence"]) > 64):
        raise ValueError("invalid source metadata")
    refs = value.get("source_refs", [])
    if not isinstance(refs, list) or len(refs) > 64 or not all(isinstance(ref, str) for ref in refs):
        raise ValueError("invalid source refs")
    return value


def _artifact_ref(root: Path, value: object, *, require_target: bool = False) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("invalid artifact reference")
    allowed = {
        "id", "path", "summary", "producer_role", "producer", "registered_by", "scope",
        "source_refs", "content_sha256", "supersedes", "task_id",
        "revision", "created_at",
    }
    if set(value) - allowed or not {"id", "path", "summary"} <= set(value):
        raise ValueError("invalid artifact reference")
    _bounded_label(value.get("id"), "artifact id")
    path = _valid_relative(root, value.get("path"))
    if path == ".git" or path.startswith(".git/") or path == ".context" or path.startswith(".context/"):
        raise ValueError("artifact path targets private control data")
    if not isinstance(value.get("summary"), str) or not value["summary"].strip() or len(value["summary"]) > 4096:
        raise ValueError("invalid artifact summary")
    identity = value.get("content_sha256")
    if identity is not None and (not isinstance(identity, str) or not re.fullmatch(r"[0-9a-f]{64}", identity)):
        raise ValueError("invalid artifact content identity")
    refs = value.get("source_refs", [])
    if not isinstance(refs, list) or len(refs) > 64 or len(set(refs)) != len(refs) or not all(isinstance(ref, str) for ref in refs):
        raise ValueError("invalid artifact source refs")
    supersedes = value.get("supersedes", [])
    if not isinstance(supersedes, list) or len(supersedes) > 64 or len(set(supersedes)) != len(supersedes) or value["id"] in supersedes or not all(isinstance(item, str) for item in supersedes):
        raise ValueError("invalid artifact supersession")
    if require_target:
        try:
            target = _safe_without_final_symlink(root, path)
        except ValueError as exc:
            raise ValueError("artifact path must name an existing regular file") from exc
        if not target.is_file():
            raise ValueError("artifact path must name an existing regular file")
    return value


def _artifact_freshness(root: Path, artifact: dict[str, object]) -> str:
    try:
        target = _safe_without_final_symlink(root, str(artifact["path"]))
    except ValueError:
        return "MISSING"
    if not target.is_file():
        return "MISSING"
    identity = artifact.get("content_sha256")
    if not isinstance(identity, str):
        return "UNKNOWN"
    return "FRESH" if _file_digest(target) == identity else "CHANGED"


def _artifact_activity(artifacts: list[dict[str, object]]) -> set[str]:
    ids = {str(item["id"]) for item in artifacts}
    inactive: set[str] = set()
    for item in artifacts:
        targets = item.get("supersedes", [])
        if any(target not in ids for target in targets):
            raise ValueError("artifact supersession target is not registered")
        inactive.update(targets)
    return ids - inactive


def _verification_result(value: object, source_ids: set[str] | None = None, *, stored: bool = False) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("invalid verification observation")
    required = {"id", "kind", "outcome", "summary", "source_refs", "observed_by", "observed_at", "observed_at_revision", "candidate_identity", "observed_files", "result_hash"}
    present = set(value) - ({"archived"} if stored else set())
    if present != required and present != required | _CHECK_RESULT_FIELDS:
        raise ValueError("invalid verification observation")
    if "check_id" in value:
        _check_run_fields(value)
    _bounded_label(value.get("id"), "verification id")
    _bounded_label(value.get("kind"), "verification kind")
    _bounded_label(value.get("outcome"), "verification outcome")
    _bounded_label(value.get("observed_by"), "verification observer")
    if not isinstance(value.get("summary"), str) or len(value["summary"]) > 4096:
        raise ValueError("invalid verification summary")
    refs = value.get("source_refs")
    if not isinstance(refs, list) or len(refs) > 64 or not all(isinstance(ref, str) for ref in refs) or len(set(refs)) != len(refs):
        raise ValueError("invalid verification source refs")
    if source_ids is not None and any(ref not in source_ids for ref in refs):
        raise ValueError("verification source reference is unknown")
    if not isinstance(value.get("observed_at"), str) or type(value.get("observed_at_revision")) is not int:
        raise ValueError("invalid verification timestamp")
    if not isinstance(value.get("candidate_identity"), str) or not re.fullmatch(r"[0-9a-f]{64}", value["candidate_identity"]):
        raise ValueError("invalid verification candidate identity")
    if not isinstance(value.get("observed_files"), list):
        raise ValueError("invalid verification observed files")
    for item in value["observed_files"]:
        if not isinstance(item, dict) or "path" not in item:
            raise ValueError("invalid verification observed files")
    if not isinstance(value.get("result_hash"), str) or not re.fullmatch(r"[0-9a-f]{64}", value["result_hash"]):
        raise ValueError("invalid verification result hash")
    return value


def _check_archive_json(value: object) -> None:
    """JSON shape check for the archive index and settled table (their sizes are bounded by their own
    validators and the hot file cap, not by the generic list cap)."""
    if isinstance(value, str):
        if len(value) > 16_384 or _ALL_CONTROL_CHARACTERS.search(value):
            raise ValueError("state contains control characters or oversized text")
    elif isinstance(value, list):
        for item in value:
            _check_archive_json(item)
    elif isinstance(value, dict):
        if len(value) > 64 or not all(isinstance(key, str) for key in value):
            raise ValueError("state object exceeds limit")
        for item in value.values():
            _check_archive_json(item)
    elif value is not None and type(value) not in {int, bool, float}:
        raise ValueError("state contains unsupported JSON value")


def _validate_state(root: Path, state: object) -> dict[str, object]:
    if isinstance(state, dict):
        _check_json({key: value for key, value in state.items() if key not in ("archive", "settled")})
        _check_archive_json([state.get("archive"), state.get("settled")])
    else:
        _check_json(state)
    if not isinstance(state, dict):
        raise ValueError("invalid task state schema")
    if (set(state) - {"evidence_continuity"} - _SCHEMA9_STATE_FIELDS - _SCHEMA10_STATE_FIELDS - _SCHEMA11_STATE_FIELDS != _STATE_FIELDS
            or state.get("schema_version") not in _SUPPORTED_SCHEMAS):
        raise ValueError("invalid task state schema")
    if type(state.get("revision")) is not int or state["revision"] < 1:
        raise ValueError("invalid task state revision")
    try:
        uuid.UUID(str(state.get("task_id")))
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError("invalid task id") from exc
    if state.get("status") not in {"ACTIVE", "DONE"} or not isinstance(state.get("goal"), str) or not state["goal"].strip() or len(state["goal"]) > 16_384:
        raise ValueError("invalid task status or goal")
    milestone = state.get("current_milestone")
    if milestone is not None and (not isinstance(milestone, str) or len(milestone) > 128):
        raise ValueError("invalid milestone label")
    for field in ("active_work", "pending_results"):
        values = state.get(field)
        if isinstance(values, list) and len(values) > 64:
            raise _capacity_error(field, 64, len(values), recovery=(
                f"the task state is unchanged; replace {field} with fewer entries in task-update, "
                "or move long content into a Record or Artifact"))
        if not isinstance(values, list) or not all(isinstance(item, str) and item.strip() and len(item) <= 4096 for item in values):
            raise ValueError(f"invalid {field}")
    routing_bytes = len(json.dumps(
        {"active_work": state["active_work"], "pending_results": state["pending_results"]},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8"))
    if routing_bytes > ROUTING_STATE_MAX_BYTES:
        raise _capacity_error(
            "active_work+pending_results", ROUTING_STATE_MAX_BYTES, routing_bytes, unit="UTF-8 bytes",
            message=(f"Active Work + Pending Results exceed {ROUTING_STATE_MAX_BYTES} UTF-8 bytes; "
                     "store long content as a Record or Artifact"),
            recovery=("the task state is unchanged; shorten Active Work and Pending Results in task-update, "
                      "or move long content into a Record or Artifact"),
        )

    # Evicted ids (archive index) are present for every reference and reserved for uniqueness.
    index_map = _validate_archive_index(state)
    sources = state.get("evidence_refs")
    if not isinstance(sources, list):
        raise ValueError("invalid source references")
    source_ids: set[str] = set(index_map["evidence_refs"])
    for source in sources:
        _evidence_ref(source, source_ids, stored=True)
        source_ids.add(str(source["id"]))
    if any(any(ref not in source_ids for ref in source.get("source_refs", [])) for source in sources):
        raise ValueError("source reference points to an unknown source")

    records = state.get("records")
    if not isinstance(records, list):
        raise ValueError("invalid task records")
    record_ids: set[str] = set(index_map["records"])
    for item in records:
        _record(item, source_ids, record_ids, stored=True)
        record_ids.add(str(item["id"]))

    artifacts = state.get("artifact_refs")
    if isinstance(artifacts, list) and len(artifacts) > 256:
        raise _capacity_error("artifact_refs", 256, len(artifacts))
    if not isinstance(artifacts, list):
        raise ValueError("invalid artifact references")
    artifact_ids: set[str] = set()
    for artifact in artifacts:
        _artifact_ref(root, artifact)
        identifier = str(artifact["id"])
        if identifier in artifact_ids:
            raise ValueError("duplicate artifact reference id")
        artifact_ids.add(identifier)
    if any(any(ref not in source_ids for ref in artifact.get("source_refs", [])) for artifact in artifacts):
        raise ValueError("artifact source reference is unknown")
    _artifact_activity(artifacts)

    results = state.get("verification_results")
    if isinstance(results, list) and _hot_count(results) > 256:
        raise _capacity_error("verification_results", 256, _hot_count(results))
    if not isinstance(results, list):
        raise ValueError("invalid verification observations")
    result_ids: set[str] = set(index_map["verification_results"]) | set(index_map["check_runs"])
    if len(result_ids) != len(index_map["verification_results"]) + len(index_map["check_runs"]):
        raise ThalirisError(_errors.TASK_OBJECT_ID_COLLISION, "task object id collision",
                            details={"ids": sorted(set(index_map["verification_results"]) & set(index_map["check_runs"]))[:8]})
    for result in results:
        _verification_result(result, source_ids, stored=True)
        if result["id"] in result_ids:
            raise ValueError("duplicate verification observation id")
        result_ids.add(str(result["id"]))

    check_ids = _validate_checks(root, state)
    object_groups = (source_ids, record_ids, artifact_ids, result_ids, check_ids)
    if sum(len(group) for group in object_groups) != len(set().union(*object_groups)):
        seen: set[str] = set()
        duplicates = sorted({identifier for group in object_groups for identifier in group if identifier in seen or seen.add(identifier)})
        raise ThalirisError(_errors.TASK_OBJECT_ID_COLLISION, "task object id collision",
                            details={"ids": duplicates[:8]})

    baseline = state.get("task_surface_baseline")
    if baseline != "UNAVAILABLE" and not isinstance(baseline, list):
        raise ValueError("invalid task surface baseline")
    if isinstance(baseline, list):
        for item in baseline:
            if not isinstance(item, dict) or set(item) != {"path", "state", "identity", "mode", "git_status"}:
                raise ValueError("invalid task surface baseline")
            _valid_relative(root, item.get("path"))
    base_head = state.get("task_base_head")
    if base_head is not None and (not isinstance(base_head, str) or not re.fullmatch(r"[0-9a-f]{40,64}", base_head)):
        raise ValueError("invalid task base head")
    _validate_continuity(state, index_map)
    _validate_verification_state(state)
    _validate_archive_totals(state, index_map)
    return state


def _serialize_state(state: dict[str, object]) -> bytes:
    """The exact bytes Core writes for a state: compact, key-sorted UTF-8 JSON plus a newline.

    Schema 10 dropped the indented form (about a fifth of the file). Loading accepts both forms;
    digests (authority anchors) are always over the exact bytes written.
    """
    return (json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _state_capacity_error(size: int, state: dict[str, object] | None = None, *, archived: bool = False) -> ThalirisError:
    details_extra: dict[str, object] = {}
    reason = ""
    if state is not None:
        try:
            pending, unresolved, _ = _continuity_open(state, latest=False)
            evicted = len(_indexed_ids(state))
        except (KeyError, TypeError, AttributeError, ValueError):
            pending, unresolved, evicted = [], [], 0
        details_extra = {"open_observation_edges": len(pending), "unresolved_judgments": len(unresolved),
                         "archived_items": sum(1 for _ in _archived_items(state)) + evicted}
        reason = (f"Core already evicted every settled object into archive segments{' in this write' if archived else ''}; "
                  f"what stays hot is open evidence ({len(pending)} unincorporated observation edges, {len(unresolved)} "
                  "unresolved judgments, the observations and handoffs they need), current records and the sources they "
                  "cite, requirements, check declarations, the archive index and the task surface; ")
    error = _capacity_error(
        "state_file", STATE_MAX_BYTES, size, unit="bytes", message="task state exceeds 512 KiB",
        recovery=("the task state is unchanged; " + reason + "judge the open observations or resolve the unresolved "
                  "judgments so they can be evicted, shorten current records, or close this task (task-close still "
                  "works) and start a new one that cites this Task ID"))
    if error.details is not None:
        error.details.update(details_extra)
    return error


def _state_payload(root: Path, state: dict[str, object]) -> bytes:
    """Validate and serialize a state as the current schema; no eviction (see ``_write_state``)."""
    state["schema_version"] = _STATE_SCHEMA_VERSION
    state = _validate_state(root, state)
    payload = _serialize_state(state)
    if len(payload) > STATE_MAX_BYTES:
        raise _state_capacity_error(len(payload), state)
    return payload


def _write_state(root: Path, state: dict[str, object]) -> None:
    """Write a state as the current schema, evicting settled objects when the hot ledger is under pressure.

    Pressure is a serialized size above ``STATE_ARCHIVE_HIGH_WATER_BYTES`` or a hot list above its
    item cap (or close to it). Evicted sources that hot objects cite again are re-hydrated first
    (best effort). The eviction pass works on a copy: the segment file is written first, then the
    state that references it. Any refusal leaves the disk state and ``state`` unchanged; a segment
    written before a failed state write is an unreferenced orphan, which is harmless.
    """
    path = _state_path(root)
    _register_archive_root(root, state)
    state["schema_version"] = _STATE_SCHEMA_VERSION
    working = state
    if _cited_evicted_sources(state):
        working = copy.deepcopy(state)
        if not _rehydrate_cited_sources(root, working):
            working = state
    pressure: ThalirisError | None = None
    try:
        _validate_state(root, working)
    except ThalirisError as exc:
        if exc.code != _errors.TASK_STATE_CAPACITY_EXCEEDED or (exc.details or {}).get("field") not in _ARCHIVE_COLLECTIONS:
            raise
        pressure = exc
    payload = _serialize_state(working)
    crowded = _crowded_collections(working)

    def commit(candidate: dict[str, object], content: bytes) -> None:
        _atomic_write(path, content)
        if candidate is not state:
            state.clear()
            state.update(candidate)

    if pressure is None and len(payload) <= STATE_ARCHIVE_HIGH_WATER_BYTES and not crowded:
        commit(working, payload)
        return
    required = pressure is not None or len(payload) > STATE_MAX_BYTES
    try:
        keep = _hot_keep(working)
        if not required and not crowded and _evictable_bytes(working, keep) < STATE_ARCHIVE_MIN_SAVINGS_BYTES:
            # Mostly open evidence, current objects and aggregates: nothing worth a segment yet.
            evicted = None
        else:
            evicted = _evict_settled(working, keep)
    except (KeyError, TypeError, AttributeError):
        if pressure is not None:
            raise pressure from None
        evicted = None
    if evicted is not None:
        candidate, segment = evicted
        segments = [segment]
        compacted = _compact_archive(root, candidate)
        if compacted is not None:
            candidate, merged = compacted
            segments.append(merged)
        _validate_state(root, candidate)
        candidate_payload = _serialize_state(candidate)
        worthwhile = (required or bool(crowded)
                      or len(payload) - len(candidate_payload) >= STATE_ARCHIVE_MIN_SAVINGS_BYTES)
        if worthwhile and len(candidate_payload) <= STATE_MAX_BYTES:
            for raw in segments:
                _write_archive_segment(root, str(candidate["task_id"]), raw)
            commit(candidate, candidate_payload)
            return
        if required and len(candidate_payload) > STATE_MAX_BYTES:
            raise _state_capacity_error(len(candidate_payload), candidate, archived=True)
    if pressure is not None:
        raise pressure
    if len(payload) > STATE_MAX_BYTES:
        raise _state_capacity_error(len(payload), working)
    commit(working, payload)


# --- Hot/cold archive: eviction segments (schema 11) and schema-10 stubs ---------------------------
#
# The hot ledger (``state.json``) holds what gates, status views and validators read about current
# and open work. When a write would leave it under pressure (see ``_write_state``), Core *evicts*
# every settled object (see ``_hot_keep``): the object leaves its hot list and moves, whole, into an
# immutable, content-addressed segment ``.context/tasks/<task id>/archive/<sha256>.json`` that is
# written temp-then-rename before the state that references it. The state's ``archive`` index keeps,
# per segment,
#
# - ``ids``: the ids it holds per collection, compactly encoded (``_encode_ids``) together with the
#   list position of every continuity object, so ledger order stays exact and the ids stay reserved:
#   the validator treats them as present for every reference and for uniqueness, and they count
#   toward no list cap;
# - ``totals``: pre-aggregated facts about what it evicted (counts, dispatch usage, claims, judgment
#   overrides, tamper and support dedupe keys).
#
# ``settled.latest`` keeps, per (requirement, candidate), the latest and the first evicted judgment
# (id, outcome, override flag, observation count, positions). Hot readers combine hot objects with
# these aggregates, so the close and withholding gates, evidence summaries, continuity status,
# usage, claims and dedupes answer exactly as before the eviction. Segments are read only for
# explicit retrieval (task-get, promotion of an evicted source) and for re-hydration: an evicted
# object that new evidence needs again (a source it cites, a handoff that receives late usage,
# claims, observations or a child, a judgment a new judgment addresses) returns to its exact hot
# position.
#
# Schema 10 (Core 3ed67e1) left full-field stubs carrying ``archived: <sha256>`` in the hot lists,
# with ``{sha256, revision, items, collections}`` index entries and version-1 segments. Such states
# load unchanged; their stubs are evicted, as stubs, on the next pressured write, and retrieval
# follows the chain from the eviction segment to the version-1 segment.

ARCHIVE_SEGMENT_FORMAT = "thaliris-task-archive"
ARCHIVE_SEGMENT_VERSION = 2
_ARCHIVE_SEGMENT_VERSIONS = (1, 2)
ARCHIVE_SEGMENT_MAX_BYTES = 16 * 1024 * 1024
# The archive index holds at most this many segment entries, and all entries together at most
# ``ARCHIVE_IDS_MAX`` reserved ids.
ARCHIVE_INDEX_MAX = STATE_LIST_MAX
ARCHIVE_IDS_MAX = 1_000_000
# Above this many eviction entries, small segments are merged (see ``_compact_archive``).
ARCHIVE_COMPACT_ENTRIES = 12
ARCHIVE_COMPACT_SEGMENT_BYTES = 2 * 1024 * 1024
ARCHIVE_COMPACT_MAX_BYTES = 8 * 1024 * 1024
_ARCHIVE_INDEX_FIELDS = {"sha256", "revision", "items", "collections"}  # schema-10 stub segments
_EVICTION_INDEX_FIELDS = {"sha256", "revision", "ids", "totals"}       # schema-11 eviction segments
_ARCHIVE_COLLECTIONS = ("evidence_refs", "records", "verification_results", "handoffs", "observations", "judgments")
_ARCHIVE_TOP_LEVEL = ("evidence_refs", "records", "verification_results")
# Continuity lists are ordered; their evicted ids carry list positions.
_POSITIONED = ("handoffs", "observations", "judgments")
# Index collections: check-run results are indexed apart from other verification results because
# ``record_check_run`` drops a check's results beyond its history, evicted or not.
_INDEX_COLLECTIONS = ("evidence_refs", "records", "verification_results", "check_runs", "handoffs", "observations", "judgments")
_OBJECT_TYPES = {"evidence_refs": "source", "records": "record", "verification_results": "verification",
                 "check_runs": "verification"}
_ARCHIVE_LIST_CAPS = {"verification_results": 256}
# A hot list above 7/8 of its cap is crowded and forces an eviction pass.
_ARCHIVE_CROWDED_FRACTION = (7, 8)
# Verification results kept hot per check (or per kind for other results).
_ARCHIVE_KEEP_RUNS = 2
# Status lists show the last 8 overrides, handoffs without typed claims and truncated claim blocks;
# those objects stay hot.
_ARCHIVE_KEEP_LISTED = 8
_SUPPORT_KEY_BYTES = 6
_SUPPORT_KEYS_PER_STRING = 2040
_ID_LABEL = re.compile(r"[A-Za-z0-9_.:-]{1,64}")
_ID_PARTS = re.compile(r"([A-Za-z0-9_.:-]*?)(0|[1-9][0-9]*)([A-Za-z_.:-]*)")
_FRACTION = re.compile(r"(0|[1-9][0-9]{0,400})/([1-9][0-9]{0,400})")
_USAGE_SUM_FIELDS = ("input_tokens", "output_tokens", "total_tokens", "cost_usd", "duration_ms", "tool_uses")
_USAGE_GROUP_FIELDS = ("total_tokens", "cost_usd")
_CLAIM_TALLIES = ("ingested", "missing", "malformed", "truncated")
# The project root each loaded task's segments live under, so in-memory transactions (adapter-owned
# locked writes) can re-hydrate evicted objects. Set by ``_load_state`` and ``_write_state``.
_archive_roots: ContextVar[dict[str, Path]] = ContextVar("thaliris_archive_roots", default={})


def _register_archive_root(root: Path, state: dict[str, object]) -> None:
    task_id = state.get("task_id") if isinstance(state, dict) else None
    if isinstance(task_id, str) and _archive_roots.get().get(task_id) != root:
        roots = dict(_archive_roots.get())
        roots[task_id] = root
        _archive_roots.set(roots)


def _hot_count(values: list[object]) -> int:
    return sum(not (isinstance(item, dict) and "archived" in item) for item in values)


def _archive_collection(state: dict[str, object], name: str) -> list[dict[str, object]]:
    if name == "check_runs":
        name = "verification_results"
    if name in _ARCHIVE_TOP_LEVEL:
        values = state.get(name)
    else:
        values = (state.get("evidence_continuity") or {}).get(name)
    return values if isinstance(values, list) else []


def _archived_items(state: dict[str, object]):
    """Schema-10 stubs still in the hot lists."""
    for name in _ARCHIVE_COLLECTIONS:
        for item in _archive_collection(state, name):
            if isinstance(item, dict) and "archived" in item:
                yield name, item


def _crowded_collections(state: dict[str, object]) -> set[str]:
    crowded: set[str] = set()
    numerator, denominator = _ARCHIVE_CROWDED_FRACTION
    for name in _ARCHIVE_COLLECTIONS:
        values = _archive_collection(state, name)
        cap = _ARCHIVE_LIST_CAPS.get(name, STATE_LIST_MAX)
        if len(values) * denominator > cap * numerator and _hot_count(values) * denominator > cap * numerator:
            crowded.add(name)
    return crowded


def _eviction_entries(state: dict[str, object]) -> list[dict[str, object]]:
    return [entry for entry in state.get("archive") or [] if isinstance(entry, dict) and "ids" in entry]


# --- compact id encoding ---

def _id_parts(identifier: str) -> tuple[str, int, str] | None:
    """(prefix, number, suffix) around the last canonical digit run of an id, or None."""
    match = _ID_PARTS.fullmatch(identifier)
    return (match.group(1), int(match.group(2)), match.group(3)) if match else None


def _id_sort_key(identifier: str) -> tuple[str, str, int, str]:
    parts = _id_parts(identifier)
    return (identifier, "", -1, identifier) if parts is None else (parts[0], parts[2], parts[1], identifier)


def _id_run(prefix: str, start: int, count: int, suffix: str, step: int) -> list[object]:
    run: list[object] = [prefix, start, count]
    if suffix or step != 1:
        run.append(suffix)
    if step != 1:
        run.append(step)
    return run


def _run_fields(element: list[object]) -> tuple[str, int, int, str, int]:
    """(prefix, start, count, suffix, step) of an id run."""
    return (element[0], element[1], element[2], element[3] if len(element) > 3 else "", element[4] if len(element) > 4 else 1)


def _encode_ids(pairs: list[tuple[str, int | None]], positioned: bool) -> list[object]:
    """Encode ids (with list positions when ``positioned``) as a compact list.

    Elements: an id string occupies the next position; a run ``[prefix, start, count]``,
    ``[prefix, start, count, suffix]`` or ``[prefix, start, count, suffix, step]`` stands for
    ``count`` ids ``prefix + str(start + k * step) + suffix`` at consecutive positions; an integer
    sets the position of the next id (positions start at 0). ``pairs`` are in position order when
    positioned; otherwise they are sorted so numbered ids form runs.
    """
    if not positioned:
        pairs = sorted(pairs, key=lambda pair: _id_sort_key(pair[0]))
    encoded: list[object] = []
    cursor = 0
    previous: tuple[str, int, str] | None = None
    for identifier, position in pairs:
        if positioned and position != cursor:
            encoded.append(position)
            previous = None
        parts = _id_parts(identifier)
        extended = False
        if previous is not None and parts is not None and parts[0] == previous[0] and parts[2] == previous[2]:
            last = encoded[-1]
            if isinstance(last, list):
                step = _run_fields(last)[4]
                if parts[1] == previous[1] + step:
                    last[2] += 1
                    extended = True
            elif isinstance(last, str) and parts[1] > previous[1]:
                encoded[-1] = _id_run(previous[0], previous[1], 2, previous[2], parts[1] - previous[1])
                extended = True
        if not extended:
            encoded.append(identifier)
        previous = parts
        if positioned:
            cursor = int(position) + 1
    # A two-id run is longer than the two ids unless it is a plain consecutive pair.
    compact: list[object] = []
    for element in encoded:
        if isinstance(element, list) and element[2] == 2 and len(element) > 3:
            prefix, start, _, suffix, step = _run_fields(element)
            compact += [f"{prefix}{start}{suffix}", f"{prefix}{start + step}{suffix}"]
        else:
            compact.append(element)
    return compact


def _decode_ids(encoded: list[object], positioned: bool):
    """Yield (id, position or None) from ``_encode_ids`` output."""
    cursor = 0
    for element in encoded:
        if type(element) is int:
            cursor = element
        elif isinstance(element, str):
            yield element, (cursor if positioned else None)
            cursor += 1
        else:
            prefix, start, count, suffix, step = _run_fields(element)
            for offset in range(count):
                yield f"{prefix}{start + offset * step}{suffix}", (cursor if positioned else None)
                cursor += 1


def _encoded_ids_problem(encoded: object, positioned: bool) -> tuple[str | None, int]:
    """(problem, number of ids) for an encoded id list."""
    if not isinstance(encoded, list) or not encoded:
        return "a non-empty encoded id list", 0
    cursor, total, after_position = 0, 0, False
    for element in encoded:
        if type(element) is int:
            if not positioned or element < cursor or after_position:
                return "increasing positions only in continuity collections, each followed by an id", total
            cursor, after_position = element, True
            continue
        after_position = False
        if isinstance(element, str):
            if not _ID_LABEL.fullmatch(element):
                return "task object ids", total
            count = 1
        elif isinstance(element, list) and len(element) in (3, 4, 5):
            prefix, start, count, suffix, step = _run_fields(element)
            if (not isinstance(prefix, str) or type(start) is not int or start < 0 or type(count) is not int or count < 2
                    or not isinstance(suffix, str) or type(step) is not int or step < 1
                    or (len(element) == 4 and not suffix) or (len(element) == 5 and step == 1)):
                return "id runs [prefix, start, count >= 2, suffix?, step >= 2?]", total
            end = start + (count - 1) * step
            first, last = f"{prefix}{start}{suffix}", f"{prefix}{end}{suffix}"
            if (not _ID_LABEL.fullmatch(first) or not _ID_LABEL.fullmatch(last) or _id_parts(first) != (prefix, start, suffix)
                    or _id_parts(last) != (prefix, end, suffix)):
                return "canonical id runs of task object ids", total
        else:
            return "id strings, id runs and positions", total
        total += count
        cursor += count
        if total > ARCHIVE_IDS_MAX:
            return f"at most {ARCHIVE_IDS_MAX} ids", total
    if after_position:
        return "a position followed by an id", total
    return None, total


# What the index decodes to is a pure function of the ``archive`` list, so it is cached by the
# digest of its compact serialization (a few hundred microseconds) instead of decoding every
# reserved id on every read and validation. Cached values are shared: callers must not mutate them.
_ARCHIVE_DERIVED: dict[str, dict[str, object]] = {}
_ARCHIVE_DERIVED_MAX = 8


def _archive_derived(state: dict[str, object]) -> dict[str, object]:
    """Decoded eviction index: ``map`` (collection -> id -> (entry number, position)), ``ids`` (all
    evicted ids), sorted evicted ``positions`` and ``at`` (position -> id) per continuity list,
    per-entry ``counts`` and ``observations``, and ``problem`` (code, message, details) or None."""
    archive = state.get("archive") or []
    key = hashlib.sha256(json.dumps(archive, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()
    derived = _ARCHIVE_DERIVED.get(key)
    if derived is not None:
        return derived
    result: dict[str, dict[str, tuple[int, int | None]]] = {name: {} for name in _INDEX_COLLECTIONS}
    counts: dict[int, dict[str, int]] = {}
    observations: dict[int, set[str]] = {}
    problem: tuple[str, str, dict[str, object]] | None = None
    total = 0
    for number, entry in enumerate(archive):
        if not isinstance(entry, dict) or not isinstance(entry.get("ids"), dict):
            continue
        for name, encoded in entry["ids"].items():
            bucket = result.get(name)
            found, count = _encoded_ids_problem(encoded, name in _POSITIONED) if bucket is not None else ("a known collection", 0)
            total += count
            if found or total > ARCHIVE_IDS_MAX:
                problem = problem or (_errors.TASK_STATE_INVALID, "invalid archive index ids",
                                      {"segment": entry.get("sha256"), "collection": name,
                                       "expected": found or f"at most {ARCHIVE_IDS_MAX} evicted ids"})
                continue
            tally = counts.setdefault(number, {})
            for identifier, position in _decode_ids(encoded, name in _POSITIONED):
                if identifier in bucket:
                    problem = problem or (_errors.TASK_OBJECT_ID_COLLISION, "task object id collision",
                                          {"ids": [identifier], "collection": name})
                bucket[identifier] = (number, position)
                tally[name] = tally.get(name, 0) + 1
                if name == "observations":
                    observations.setdefault(number, set()).add(identifier)
    ids: set[str] = set()
    for name, bucket in result.items():
        ids.update(bucket)
    if problem is None and len(ids) != sum(len(bucket) for bucket in result.values()):
        seen: set[str] = set()
        duplicates = sorted({identifier for bucket in result.values() for identifier in bucket if identifier in seen or seen.add(identifier)})
        problem = (_errors.TASK_OBJECT_ID_COLLISION, "task object id collision", {"ids": duplicates[:8]})
    positions: dict[str, list[int]] = {}
    at: dict[str, dict[int, str]] = {}
    for name in _POSITIONED:
        at[name] = {position: identifier for identifier, (_, position) in result[name].items()}
        positions[name] = sorted(at[name])
        if problem is None and len(at[name]) != len(result[name]):
            problem = (_errors.TASK_STATE_INVALID, "invalid archive index ids",
                       {"collection": name, "expected": "one evicted object per list position"})
    derived = {"map": result, "ids": ids, "positions": positions, "at": at, "counts": counts,
               "observations": observations, "problem": problem}
    if len(_ARCHIVE_DERIVED) >= _ARCHIVE_DERIVED_MAX:
        _ARCHIVE_DERIVED.pop(next(iter(_ARCHIVE_DERIVED)))
    _ARCHIVE_DERIVED[key] = derived
    return derived


_EMPTY_INDEX_MAP: dict[str, dict[str, tuple[int, int | None]]] = {name: {} for name in _INDEX_COLLECTIONS}


def _index_map(state: dict[str, object]) -> dict[str, dict[str, tuple[int, int | None]]]:
    """Evicted ids per index collection: id -> (archive entry number, list position or None). Read-only."""
    if not _eviction_entries(state):
        return _EMPTY_INDEX_MAP
    return _archive_derived(state)["map"]  # type: ignore[return-value]


def _indexed_ids(state: dict[str, object], index_map: dict[str, dict[str, tuple[int, int | None]]] | None = None) -> set[str]:
    """Every evicted id (a copy)."""
    if not _eviction_entries(state):
        return set()
    if index_map is None:
        return set(_archive_derived(state)["ids"])  # type: ignore[arg-type]
    return {identifier for bucket in index_map.values() for identifier in bucket}


def _known_ids(state: dict[str, object], name: str) -> set[str]:
    """Hot and evicted ids of one top-level collection (``verification_results`` includes check runs)."""
    ids = {str(item["id"]) for item in _archive_collection(state, name)}
    if _eviction_entries(state):
        index_map = _index_map(state)
        ids.update(index_map[name])
        if name == "verification_results":
            ids.update(index_map["check_runs"])
    return ids


def _hot_positions(state: dict[str, object], name: str,
                   index_map: dict[str, dict[str, tuple[int, int | None]]] | None = None) -> list[int]:
    """Ledger positions of the hot objects of a continuity list (evicted positions are skipped)."""
    hot = _archive_collection(state, name)
    if not _eviction_entries(state):
        return list(range(len(hot)))
    if index_map is None:
        evicted: list[int] = _archive_derived(state)["positions"][name]  # type: ignore[index]
    else:
        evicted = sorted(position for _, position in index_map[name].values())
    positions: list[int] = []
    cursor, skip = 0, 0
    while len(positions) < len(hot):
        if skip < len(evicted) and evicted[skip] == cursor:
            skip += 1
        else:
            positions.append(cursor)
        cursor += 1
    return positions


def _collection_totals(state: dict[str, object]) -> dict[str, int]:
    """Hot plus evicted object counts per archivable collection (check runs count as verification results)."""
    totals = {name: len(_archive_collection(state, name)) for name in _ARCHIVE_COLLECTIONS}
    for entry in _eviction_entries(state):
        for name, count in entry["totals"].get("counts", {}).items():
            target = "verification_results" if name == "check_runs" else name
            totals[target] = totals.get(target, 0) + count
    return totals


# --- pre-aggregated totals ---

def _fraction_text(value: Fraction) -> str:
    return f"{value.numerator}/{value.denominator}"


def _usage_value(usage: dict[str, object], field: str) -> object:
    value = usage[field]
    if value is None and field == "total_tokens" and usage["input_tokens"] is not None and usage["output_tokens"] is not None:
        value = usage["input_tokens"] + usage["output_tokens"]
    return value


class _UsageSum:
    """Exact usage sums: integer token/duration sums and an exact rational cost sum.

    ``view`` gives the shape ``usage_summary`` reports. Cost is summed exactly and rounded once,
    so the total does not depend on the order (or the segments) the values come from.
    """

    def __init__(self, fields: tuple[str, ...] = _USAGE_SUM_FIELDS) -> None:
        self.fields = fields
        self.handoffs = 0
        self.present = {field: 0 for field in fields}
        self.sums: dict[str, object] = {field: (Fraction(0) if field == "cost_usd" else 0) for field in fields}
        self.floats = 0

    def add(self, usage: dict[str, object], sign: int = 1) -> None:
        self.handoffs += sign
        for field in self.fields:
            value = _usage_value(usage, field)
            if value is None:
                continue
            self.present[field] += sign
            if field == "cost_usd":
                self.sums[field] += sign * Fraction(value)
                self.floats += sign * (type(value) is float)
            else:
                self.sums[field] += sign * value

    def merge(self, other: "_UsageSum", sign: int = 1) -> None:
        self.handoffs += sign * other.handoffs
        for field in self.fields:
            self.present[field] += sign * other.present[field]
            self.sums[field] += sign * other.sums[field]
        self.floats += sign * other.floats

    def view(self) -> dict[str, object]:
        result: dict[str, object] = {"handoffs": self.handoffs}
        for field in self.fields:
            if not self.present[field]:
                result[field] = None
            elif field == "cost_usd":
                total = self.sums[field]
                result[field] = round(float(total), 6) if self.floats else round(int(total), 6)
            else:
                result[field] = self.sums[field]
        return result

    def export(self) -> list[object]:
        values: list[object] = [self.handoffs]
        for field in self.fields:
            values += [self.present[field], _fraction_text(self.sums[field]) if field == "cost_usd" else self.sums[field]]
        return values + [self.floats]

    @classmethod
    def load(cls, values: list[object], fields: tuple[str, ...] = _USAGE_SUM_FIELDS) -> "_UsageSum":
        total = cls(fields)
        total.handoffs = values[0]
        for offset, field in enumerate(fields):
            present, value = values[1 + 2 * offset], values[2 + 2 * offset]
            total.present[field] = present
            if field == "cost_usd":
                numerator, denominator = _FRACTION.fullmatch(value).groups()
                total.sums[field] = Fraction(int(numerator), int(denominator))
            else:
                total.sums[field] = value
        total.floats = values[-1]
        return total

    def problem(self) -> str | None:
        if self.handoffs < 1 or not 0 <= self.floats <= self.present.get("cost_usd", 0):
            return "usage totals with at least one handoff"
        for field in self.fields:
            if not 0 <= self.present[field] <= self.handoffs or self.sums[field] < 0 or (not self.present[field] and self.sums[field]):
                return "usage totals with non-negative sums of at most one value per handoff"
        return None


def _usage_sum_problem(values: object, fields: tuple[str, ...]) -> str | None:
    if not isinstance(values, list) or len(values) != 2 + 2 * len(fields):
        return "usage totals [handoffs, present, sum, ..., floats]"
    if not all(type(value) is int for index, value in enumerate(values) if index != 2 + 2 * fields.index("cost_usd")):
        return "integer usage totals"
    cost = values[2 + 2 * fields.index("cost_usd")]
    if not isinstance(cost, str) or not _FRACTION.fullmatch(cost):
        return "an exact cost sum `numerator/denominator`"
    return _UsageSum.load(values, fields).problem()


def _support_key(candidate: object, requirement: object, evidence: object) -> bytes:
    return hashlib.sha256(json.dumps([candidate, requirement, evidence], ensure_ascii=False).encode("utf-8")).digest()[:_SUPPORT_KEY_BYTES]


class _Totals:
    """Aggregates of evicted objects; ``export`` is the index entry ``totals`` form."""

    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.usage = _UsageSum()
        self.by_role: dict[str, _UsageSum] = {}
        self.by_model: dict[str, _UsageSum] = {}
        self.outcomes: dict[str, int] = {}
        self.claims = dict.fromkeys(_CLAIM_TALLIES, 0)
        self.supports: dict[str, int] = {}
        self.support_keys: dict[str, set[bytes]] = {}
        self.overrides = 0
        self.mechanism: dict[tuple[str, str], str] = {}

    def add(self, name: str, item: dict[str, object], sign: int = 1) -> None:
        self.counts[name] = self.counts.get(name, 0) + sign
        if name == "handoffs":
            usage = item.get("usage")
            if isinstance(usage, dict):
                self.usage.add(usage, sign)
                for groups, key in ((self.by_role, str(item["producer"])), (self.by_model, str(usage["model"] or "unknown"))):
                    groups.setdefault(key, _UsageSum(_USAGE_GROUP_FIELDS)).add(usage, sign)
                outcome = str(usage["outcome"] or "unknown")
                self.outcomes[outcome] = self.outcomes.get(outcome, 0) + sign
            claims = item.get("claims")
            if isinstance(claims, dict):
                self.claims["ingested"] += sign
                self.claims["missing"] += sign * (claims["status"] == "missing")
                self.claims["malformed"] += sign * (claims["status"] == "malformed")
                self.claims["truncated"] += sign * bool(claims.get("truncated"))
                for support in claims.get("supports", []):
                    self.supports[str(support["requirement"])] = self.supports.get(str(support["requirement"]), 0) + sign
                    if sign > 0 and claims["status"] == "present":
                        self.support_keys.setdefault(str(item["candidate"]), set()).add(
                            _support_key(item["candidate"], support["requirement"], support["evidence"]))
        elif name == "observations" and isinstance(item.get("mechanism"), dict):
            key = (str(item["mechanism"]["check_id"]), str(item["mechanism"]["files_digest"]))
            if sign > 0:
                self.mechanism[key] = str(item["id"])
            elif self.mechanism.get(key) == item["id"]:
                del self.mechanism[key]
        elif name == "judgments" and "override_reason" in item:
            self.overrides += sign

    def merge(self, other: "_Totals") -> None:
        for name, count in other.counts.items():
            self.counts[name] = self.counts.get(name, 0) + count
        self.usage.merge(other.usage)
        for mine, theirs, fields in ((self.by_role, other.by_role, _USAGE_GROUP_FIELDS), (self.by_model, other.by_model, _USAGE_GROUP_FIELDS)):
            for key, value in theirs.items():
                mine.setdefault(key, _UsageSum(fields)).merge(value)
        for key, count in other.outcomes.items():
            self.outcomes[key] = self.outcomes.get(key, 0) + count
        for key in _CLAIM_TALLIES:
            self.claims[key] += other.claims[key]
        for key, count in other.supports.items():
            self.supports[key] = self.supports.get(key, 0) + count
        for key, values in other.support_keys.items():
            self.support_keys.setdefault(key, set()).update(values)
        self.overrides += other.overrides
        self.mechanism.update(other.mechanism)

    def export(self) -> dict[str, object]:
        totals: dict[str, object] = {"counts": {name: count for name, count in sorted(self.counts.items()) if count}}
        if self.usage.handoffs:
            totals["usage"] = {
                "all": self.usage.export(),
                "by_role": [[key, *value.export()] for key, value in sorted(self.by_role.items()) if value.handoffs],
                "by_model": [[key, *value.export()] for key, value in sorted(self.by_model.items()) if value.handoffs],
                "outcomes": [[key, count] for key, count in sorted(self.outcomes.items()) if count],
            }
        if self.claims["ingested"]:
            totals["claims"] = [self.claims[key] for key in _CLAIM_TALLIES]
        ones = [(key, None) for key, count in self.supports.items() if count == 1]
        more = [[key, count] for key, count in sorted(self.supports.items()) if count > 1]
        if ones or more:
            totals["supports"] = [_encode_ids(ones, False) if ones else [], more]
        keys: list[list[str]] = []
        for candidate, values in sorted(self.support_keys.items()):
            ordered = sorted(values)
            for start in range(0, len(ordered), _SUPPORT_KEYS_PER_STRING):
                chunk = b"".join(ordered[start:start + _SUPPORT_KEYS_PER_STRING])
                keys.append([candidate, base64.urlsafe_b64encode(chunk).decode("ascii").rstrip("=")])
        if keys:
            totals["support_keys"] = keys
        if self.overrides:
            totals["overrides"] = self.overrides
        if self.mechanism:
            totals["mechanism"] = [[check, digest, identifier] for (check, digest), identifier in sorted(self.mechanism.items())]
        return totals

    @classmethod
    def load(cls, totals: dict[str, object]) -> "_Totals":
        result = cls()
        result.counts = dict(totals.get("counts", {}))
        usage = totals.get("usage")
        if usage:
            result.usage = _UsageSum.load(usage["all"])
            result.by_role = {row[0]: _UsageSum.load(row[1:], _USAGE_GROUP_FIELDS) for row in usage["by_role"]}
            result.by_model = {row[0]: _UsageSum.load(row[1:], _USAGE_GROUP_FIELDS) for row in usage["by_model"]}
            result.outcomes = {row[0]: row[1] for row in usage["outcomes"]}
        if "claims" in totals:
            result.claims = dict(zip(_CLAIM_TALLIES, totals["claims"]))
        if "supports" in totals:
            ones, more = totals["supports"]
            result.supports = {identifier: 1 for identifier, _ in _decode_ids(ones, False)}
            result.supports.update((row[0], row[1]) for row in more)
        for candidate, text in totals.get("support_keys", []):
            raw = base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
            result.support_keys.setdefault(candidate, set()).update(
                raw[start:start + _SUPPORT_KEY_BYTES] for start in range(0, len(raw), _SUPPORT_KEY_BYTES))
        result.overrides = totals.get("overrides", 0)
        result.mechanism = {(row[0], row[1]): row[2] for row in totals.get("mechanism", [])}
        return result


def _archive_totals(state: dict[str, object]) -> _Totals:
    """All eviction entries' totals combined (a fresh object the caller may extend)."""
    combined = _Totals()
    entries = _eviction_entries(state)
    if not entries:
        return combined
    derived = _archive_derived(state)
    cached = derived.get("totals")
    if cached is None:
        cached = _Totals()
        for entry in entries:
            cached.merge(_Totals.load(entry["totals"]))
        derived["totals"] = cached
    combined.merge(cached)  # type: ignore[arg-type]
    return combined


def _totals_problem(totals: object, counts: dict[str, int], entry_observations: set[str],
                    requirements: set[str]) -> str | None:
    """Check what is checkable in one entry's totals against its decoded ids."""
    allowed = {"counts", "usage", "claims", "supports", "support_keys", "overrides", "mechanism"}
    if not isinstance(totals, dict) or set(totals) - allowed or totals.get("counts") != counts:
        return "totals whose counts match the entry's ids"
    handoffs = counts.get("handoffs", 0)
    usage = totals.get("usage")
    if usage is not None:
        if not isinstance(usage, dict) or set(usage) != {"all", "by_role", "by_model", "outcomes"}:
            return "usage totals {all, by_role, by_model, outcomes}"
        problem = _usage_sum_problem(usage["all"], _USAGE_SUM_FIELDS)
        if problem:
            return problem
        all_handoffs = usage["all"][0]
        if all_handoffs > handoffs:
            return "usage totals for at most the evicted handoffs"
        for field in ("by_role", "by_model"):
            rows = usage[field]
            if not isinstance(rows, list) or not rows or not all(isinstance(row, list) and row and isinstance(row[0], str) and 0 < len(row[0]) <= 128 for row in rows):
                return f"usage {field} rows [name, ...totals]"
            if len({row[0] for row in rows}) != len(rows):
                return f"unique usage {field} names"
            for row in rows:
                problem = _usage_sum_problem(row[1:], _USAGE_GROUP_FIELDS)
                if problem:
                    return problem
            if sum(row[1] for row in rows) != all_handoffs:
                return f"usage {field} rows that add up to the usage total"
        rows = usage["outcomes"]
        if (not isinstance(rows, list) or not all(isinstance(row, list) and len(row) == 2 and isinstance(row[0], str)
                                                   and type(row[1]) is int and row[1] >= 1 for row in rows)
                or len({row[0] for row in rows}) != len(rows) or sum(row[1] for row in rows) != all_handoffs):
            return "usage outcome counts that add up to the usage total"
    claims = totals.get("claims")
    if claims is not None:
        if (not isinstance(claims, list) or len(claims) != len(_CLAIM_TALLIES) or not all(type(value) is int and value >= 0 for value in claims)
                or not 1 <= claims[0] <= handoffs or claims[1] + claims[2] > claims[0] or claims[3] > claims[0]):
            return "claims tallies [ingested, missing, malformed, truncated] for at most the evicted handoffs"
    supports = totals.get("supports")
    if supports is not None:
        if not isinstance(supports, list) or len(supports) != 2 or not isinstance(supports[1], list) or claims is None:
            return "support counts [requirements with one support, [[requirement, count >= 2], ...]]"
        ones: list[str] = []
        if supports[0]:
            problem, _ = _encoded_ids_problem(supports[0], False)
            if problem:
                return "support counts: " + problem
            ones = [identifier for identifier, _ in _decode_ids(supports[0], False)]
        more = supports[1]
        if not all(isinstance(row, list) and len(row) == 2 and type(row[1]) is int and row[1] >= 2 for row in more):
            return "support counts [[requirement, count >= 2], ...]"
        named = ones + [row[0] for row in more]
        if not named or len(set(named)) != len(named) or not set(named) <= requirements:
            return "support counts per registered requirement"
    keys = totals.get("support_keys", [])
    if not isinstance(keys, list):
        return "support dedupe keys"
    for row in keys:
        if not isinstance(row, list) or len(row) != 2 or not isinstance(row[0], str) or not _ID_LABEL.fullmatch(row[0]) or not isinstance(row[1], str):
            return "support dedupe keys [candidate, base64]"
        try:
            raw = base64.urlsafe_b64decode(row[1] + "=" * (-len(row[1]) % 4))
        except (ValueError, TypeError):
            return "support dedupe keys [candidate, base64]"
        if not raw or len(raw) % _SUPPORT_KEY_BYTES:
            return f"support dedupe keys of {_SUPPORT_KEY_BYTES} bytes each"
    overrides = totals.get("overrides", 0)
    if type(overrides) is not int or overrides < 0 or overrides > counts.get("judgments", 0) or ("overrides" in totals and not overrides):
        return "an override count of at most the evicted judgments"
    mechanism = totals.get("mechanism", [])
    if (not isinstance(mechanism, list) or not all(
            isinstance(row, list) and len(row) == 3 and isinstance(row[0], str) and _CHECK_ID.fullmatch(row[0])
            and _is_hex64(row[1]) and row[2] in entry_observations for row in mechanism)
            or len({(row[0], row[1]) for row in mechanism}) != len(mechanism)):
        return "tamper dedupe keys [check id, files digest, evicted observation id]"
    return None


# --- the latest evicted judgment per (requirement, candidate) ---

def _outcome_code(item: dict[str, object]) -> int:
    return _JUDGMENT_OUTCOMES.index(item["outcome"]) + (4 if "override_reason" in item else 0)


def _judgment_at(state: dict[str, object], positions: list[int] | None = None) -> dict[int, str]:
    """Judgment id per ledger position (evicted and hot)."""
    if not _eviction_entries(state):
        return {}
    at = dict(_archive_derived(state)["at"]["judgments"])  # type: ignore[index]
    judgments = (state.get("evidence_continuity") or {}).get("judgments", [])
    at.update(zip(_hot_positions(state, "judgments") if positions is None else positions, (item["id"] for item in judgments)))
    return at


def _settled_latest_rows(state: dict[str, object], at: dict[int, str] | None = None):
    """Yield (requirement, candidate, [first, last, id, code, observation count]) from ``settled.latest``.

    A row is ``[requirement, outcome code, last position, first position?, observation count?]``
    (first defaults to last, the count to 1); the latest id is the judgment at the last position.
    """
    settled = state.get("settled")
    if not settled:
        return
    at = _judgment_at(state) if at is None else at
    for candidate, rows in settled.get("latest", []):
        for row in rows:
            first = row[3] if len(row) > 3 else row[2]
            count = row[4] if len(row) > 4 else 1
            yield row[0], candidate, [first, row[2], at.get(row[2]), row[1], count]


def _judgment_keys(state: dict[str, object]) -> list[tuple[tuple[str, str], list[object]]]:
    """Every (requirement, candidate) judged in this task with [first position, last position, latest id,
    outcome code, observation count], in order of first judgment (hot and evicted combined)."""
    keys: dict[tuple[str, str], list[object]] = {}
    judgments = (state.get("evidence_continuity") or {}).get("judgments", [])
    positions = _hot_positions(state, "judgments")
    if state.get("settled"):
        for requirement, candidate, row in _settled_latest_rows(state, _judgment_at(state, positions)):
            keys[(requirement, candidate)] = row
    for item, position in zip(judgments, positions):
        key = (item["requirement_ref"], item["candidate"])
        row = keys.get(key)
        latest = [position, item["id"], _outcome_code(item), len(item["observation_refs"])]
        if row is None:
            keys[key] = [position, *latest]
        else:
            row[0] = min(row[0], position)
            if position >= row[1]:
                row[1:] = latest
    return sorted(keys.items(), key=lambda pair: pair[1][0])


def _latest_rows_problem(state: dict[str, object], index_map: dict[str, dict[str, tuple[int, int | None]]],
                         requirements: set[str]) -> str | None:
    settled = state.get("settled")
    if settled is None:
        return None
    if not isinstance(settled, dict) or set(settled) != {"latest"} or not isinstance(settled["latest"], list):
        return "a settled table {latest: [[candidate, rows], ...]}"
    judgments = (state.get("evidence_continuity") or {}).get("judgments", [])
    total = len(judgments) + len(index_map["judgments"])
    at = _judgment_at(state)
    seen: set[tuple[str, str]] = set()
    for group in settled["latest"]:
        if (not isinstance(group, list) or len(group) != 2 or not isinstance(group[0], str) or not _ID_LABEL.fullmatch(group[0])
                or not isinstance(group[1], list) or not group[1]):
            return "latest judgment groups [candidate, rows]"
        for row in group[1]:
            if (not isinstance(row, list) or not 3 <= len(row) <= 5 or not all(type(value) is int for value in row[1:])
                    or row[0] not in requirements or (group[0], row[0]) in seen):
                return "latest judgment rows [requirement, outcome code, last, first?, observations?] per registered requirement"
            seen.add((group[0], row[0]))
            code, last = row[1], row[2]
            first = row[3] if len(row) > 3 else last
            count = row[4] if len(row) > 4 else 1
            if code not in range(5) or not 0 <= first <= last < total or not 1 <= count <= 64 or last not in at:
                return "latest judgment rows whose positions name judgments of this task"
    return None


def _merge_latest(state: dict[str, object], evicted: list[tuple[dict[str, object], int]]) -> None:
    """Fold evicted judgments (with their positions) into ``settled.latest``."""
    keys = {(requirement, candidate): row for requirement, candidate, row in _settled_latest_rows(state, {})}
    for item, position in evicted:
        key = (item["requirement_ref"], item["candidate"])
        latest = [position, item["id"], _outcome_code(item), len(item["observation_refs"])]
        row = keys.get(key)
        if row is None:
            keys[key] = [position, *latest]
        else:
            row[0] = min(row[0], position)
            if position >= row[1]:
                row[1:] = latest
    groups: dict[str, list[list[object]]] = {}
    for (requirement, candidate), (first, last, _, code, count) in sorted(keys.items(), key=lambda pair: (pair[0][1], pair[1][0])):
        row: list[object] = [requirement, code, last]
        if first != last or count != 1:
            row.append(first)
        if count != 1:
            row.append(count)
        groups.setdefault(candidate, []).append(row)
    if groups:
        state["settled"] = {"latest": [[candidate, rows] for candidate, rows in groups.items()]}


# --- what stays hot ---

def _hot_keep(state: dict[str, object]) -> dict[str, set[str]]:
    """Ids of hot objects that must stay hot; every other object of an archivable list may be evicted.

    Hot: open evidence (unincorporated observations, unresolved judgments and the observations they
    cite, handoffs with open observations or no returned result yet), every judgment that cites a hot
    observation (incorporation and citation of hot observations are computed from hot judgments) and
    every judgment that resolves a hot repair/unknown judgment, the handoff of every hot observation,
    the last ``CHANGES_SINCE_RECENT_MAX`` handoffs, observations and judgments (``changes_since``),
    the last 8 overridden judgments, handoffs without typed claims and handoffs with truncated claims
    (status lists), current records and records written in the last ``CHANGES_SINCE_RECENT_MAX``
    revisions, the last two runs of every declared check (and of every other verification kind), and
    every source a hot object, an artifact or a hot source cites. Requirements, checks, artifacts,
    authority and closure are never evicted.
    """
    tail = CHANGES_SINCE_RECENT_MAX
    data = state.get("evidence_continuity") or {}
    observations = data.get("observations", [])
    judgments = data.get("judgments", [])
    handoffs = data.get("handoffs", [])
    pending, unresolved, _ = _continuity_open(state, latest=False)
    unresolved_ids = {item["id"] for item in unresolved}
    by_id = {item["id"]: item for item in judgments}
    keep_obs = {item["observation_id"] for item in pending}
    for identifier in unresolved_ids:
        keep_obs.update(by_id[identifier]["observation_refs"])
    open_obs = set(keep_obs)
    keep_obs.update(item["id"] for item in observations[-tail:])
    keep_obs &= {item["id"] for item in observations}
    keep_j = set(unresolved_ids) | {item["id"] for item in judgments[-tail:]}
    keep_j.update([item["id"] for item in judgments if "override_reason" in item][-_ARCHIVE_KEEP_LISTED:])
    keep_j.update(item["id"] for item in judgments if any(ref in keep_obs for ref in item["observation_refs"]))
    order = {item["id"]: index for index, item in enumerate(judgments)}
    frontier = list(keep_j)
    while frontier:
        identifier = frontier.pop()
        judgment = by_id[identifier]
        if judgment["outcome"] not in ("repair", "unknown") or identifier in unresolved_ids:
            continue
        basis = set(judgment["observation_refs"])
        for later in judgments[order[identifier] + 1:]:
            if later["id"] not in keep_j and (identifier in later.get("judgment_refs", []) or (
                    later["requirement_ref"] == judgment["requirement_ref"] and basis <= set(later["observation_refs"]))):
                keep_j.add(later["id"])
                frontier.append(later["id"])
    returned = {item["handoff_id"] for item in observations if item.get("handoff_id")}
    keep_h = {item["id"] for item in handoffs if not (
        item["id"] in returned or "claims" in item or (isinstance(item.get("usage"), dict) and item["usage"].get("outcome")))}
    keep_h.update(item["handoff_id"] for item in observations
                  if (item["id"] in keep_obs or item["id"] in open_obs) and item.get("handoff_id"))
    keep_h.update(item["id"] for item in handoffs[-tail:])
    keep_h.update([item["id"] for item in handoffs if "claims" in item and item["claims"]["status"] != "present"][-_ARCHIVE_KEEP_LISTED:])
    keep_h.update([item["id"] for item in handoffs if "claims" in item and item["claims"].get("truncated")][-_ARCHIVE_KEEP_LISTED:])
    records = state.get("records", [])
    superseded = {ref for item in records for ref in item.get("supersedes", [])}
    keep_r = {item["id"] for item in records if item["id"] not in superseded or item["revision"] > state["revision"] - tail}
    runs: dict[tuple[str, str], list[str]] = {}
    for item in state.get("verification_results", []):
        key = ("check", str(item["check_id"])) if "check_id" in item else ("kind", str(item.get("kind")))
        runs.setdefault(key, []).append(item["id"])
    keep_v = {identifier for ids in runs.values() for identifier in ids[-_ARCHIVE_KEEP_RUNS:]}
    cited: set[str] = set()
    for item in observations:
        if item["id"] in keep_obs:
            cited.update(item.get("source_refs", []))
    for item in records:
        if item["id"] in keep_r:
            cited.update(item.get("source_refs", []))
    for item in state.get("artifact_refs", []):
        cited.update(item.get("source_refs", []))
    for item in state.get("verification_results", []):
        if item["id"] in keep_v:
            cited.update(item.get("source_refs", []))
    sources = {item["id"]: item for item in state.get("evidence_refs", [])}
    frontier = [ref for ref in cited if ref in sources]
    keep_s = set(frontier)
    while frontier:
        for parent in sources[frontier.pop()].get("source_refs", []):
            if parent not in keep_s and parent in sources:
                keep_s.add(parent)
                frontier.append(parent)
    return {"evidence_refs": keep_s, "records": keep_r, "verification_results": keep_v, "handoffs": keep_h,
            "observations": keep_obs, "judgments": keep_j}


# --- the eviction pass ---

def _segment_bytes(task_id: str, revision: int, items: list[dict[str, object]]) -> bytes:
    segment = {"format": ARCHIVE_SEGMENT_FORMAT, "version": ARCHIVE_SEGMENT_VERSION, "task_id": task_id,
               "revision": revision, "items": items}
    return (json.dumps(segment, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _evictable_bytes(state: dict[str, object], keep: dict[str, set[str]]) -> int:
    """Serialized bytes an eviction pass would remove (an estimate that ignores the index entry it adds)."""
    return sum(_compact_size(item) + 1 for name in _ARCHIVE_COLLECTIONS for item in _archive_collection(state, name)
               if item["id"] not in keep[name])


def _evict_settled(state: dict[str, object], keep: dict[str, set[str]] | None = None) -> tuple[dict[str, object], bytes] | None:
    """Build (state with every settled object evicted, segment bytes), or None when nothing is settled.

    Pure: nothing is written. Evicted objects (schema-10 stubs included, as they are) leave their
    hot lists; the new index entry lists their ids and positions and carries their totals, and
    evicted judgments are folded into ``settled.latest``.
    """
    archive = state.get("archive") or []
    if len(archive) >= ARCHIVE_INDEX_MAX:
        return None
    keep = _hot_keep(state) if keep is None else keep
    candidate = copy.deepcopy(state)
    index_map = _index_map(candidate)
    items: list[dict[str, object]] = []
    pairs: dict[str, list[tuple[str, int | None]]] = {}
    totals = _Totals()
    judgments: list[tuple[dict[str, object], int]] = []
    for name in _ARCHIVE_COLLECTIONS:
        values = _archive_collection(candidate, name)
        positions = _hot_positions(candidate, name, index_map) if name in _POSITIONED else [None] * len(values)
        kept: list[dict[str, object]] = []
        for item, position in zip(values, positions):
            if item["id"] in keep[name]:
                kept.append(item)
                continue
            index_name = "check_runs" if name == "verification_results" and "check_id" in item else name
            record: dict[str, object] = {"collection": index_name, "id": item["id"], "object": item}
            if position is not None:
                record["position"] = position
            items.append(record)
            pairs.setdefault(index_name, []).append((str(item["id"]), position))
            totals.add(index_name, item)
            if name == "judgments":
                judgments.append((item, int(position)))
        values[:] = kept
    if not items:
        return None
    raw = _segment_bytes(str(candidate["task_id"]), int(candidate["revision"]), items)
    entry = {"sha256": hashlib.sha256(raw).hexdigest(), "revision": candidate["revision"],
             "ids": {name: _encode_ids(values, name in _POSITIONED) for name, values in sorted(pairs.items())},
             "totals": totals.export()}
    candidate["archive"] = [*archive, entry]
    _merge_latest(candidate, judgments)
    return candidate, raw


def _compact_archive(root: Path, state: dict[str, object]) -> tuple[dict[str, object], bytes] | None:
    """Merge small eviction segments into one when the index holds many of them.

    Above ``ARCHIVE_COMPACT_ENTRIES`` eviction entries, the entries whose segment files are below
    ``ARCHIVE_COMPACT_SEGMENT_BYTES`` (up to ``ARCHIVE_COMPACT_MAX_BYTES`` in all) are read,
    verified and merged into one new segment holding exactly the objects they still claim; their
    index entries become one entry with the merged ids and the summed totals. Pure apart from
    reading segments: returns (new state, new segment bytes), or None when nothing qualifies or a
    segment cannot be read (the index then stays as it is).
    """
    archive = state.get("archive") or []
    entries = [(number, entry) for number, entry in enumerate(archive) if isinstance(entry, dict) and "ids" in entry]
    if len(entries) <= ARCHIVE_COMPACT_ENTRIES:
        return None
    task_id = str(state["task_id"])
    chosen: list[tuple[int, dict[str, object]]] = []
    total = 0
    for number, entry in entries:
        try:
            size = _archive_segment_path(root, task_id, str(entry["sha256"])).stat().st_size
        except (OSError, ValueError):
            continue
        if size < ARCHIVE_COMPACT_SEGMENT_BYTES and total + size <= ARCHIVE_COMPACT_MAX_BYTES:
            chosen.append((number, entry))
            total += size
    if len(chosen) < 2:
        return None
    items: list[dict[str, object]] = []
    pairs: dict[str, list[tuple[str, int | None]]] = {}
    totals = _Totals()
    for _, entry in chosen:
        try:
            segment = _read_archive_segment(root, task_id, str(entry["sha256"]))
        except ThalirisError:
            return None
        claimed: dict[tuple[str, str], int | None] = {}
        for name, encoded in entry["ids"].items():
            for identifier, position in _decode_ids(encoded, name in _POSITIONED):
                claimed[(name, identifier)] = position
                pairs.setdefault(name, []).append((identifier, position))
        held = [item for item in segment["items"] if isinstance(item, dict)
                and claimed.get((item.get("collection"), item.get("id")), "absent") == item.get("position")]
        if len(held) != len(claimed):
            return None
        items.extend(held)
        totals.merge(_Totals.load(entry["totals"]))
    raw = _segment_bytes(task_id, int(state["revision"]), items)
    merged = {"sha256": hashlib.sha256(raw).hexdigest(), "revision": state["revision"],
              "ids": {name: _encode_ids(sorted(values, key=lambda pair: pair[1]) if name in _POSITIONED else values, name in _POSITIONED)
                      for name, values in sorted(pairs.items())},
              "totals": totals.export()}
    numbers = {number for number, _ in chosen}
    first = min(numbers)
    candidate = {**state, "archive": [merged if number == first else entry for number, entry in enumerate(archive)
                                      if number == first or number not in numbers]}
    return candidate, raw


# --- segments ---

def _archive_segment_path(root: Path, task_id: str, sha256: str) -> Path:
    if str(uuid.UUID(task_id)) != task_id or not _is_hex64(sha256):
        raise ValueError("invalid archive segment identity")
    return _safe_without_final_symlink(root, f".context/tasks/{task_id}/archive/{sha256}.json")


def _write_archive_segment(root: Path, task_id: str, raw: bytes) -> None:
    """Write a segment atomically. An existing segment with the same name and digest is kept as is."""
    sha = hashlib.sha256(raw).hexdigest()
    target = _archive_segment_path(root, task_id, sha)
    if target.is_file():
        try:
            if _file_digest(target) == sha:
                return
        except OSError:
            pass
    # A file under this name with other bytes is not this segment (damage); the content-addressed
    # bytes replace it, which restores what every referencing state expects.
    _atomic_write(target, raw)


def _archive_unavailable(identifier: str, sha: object, reason: str, object_type: str | None = None) -> ThalirisError:
    return ThalirisError(
        _errors.TASK_ARCHIVE_UNAVAILABLE, "archived task object body is unavailable",
        recovery=("restore the segment file with its exact bytes (its sha256 is its name) from a copy; the hot "
                  "ledger and its archive index are intact, and gates, task-status and every write that does not "
                  "need this object keep working"),
        details={"id": identifier, "segment": sha if isinstance(sha, str) else None, "reason": reason,
                 **({"object_type": object_type} if object_type else {})})


def _read_archive_segment(root: Path, task_id: str, sha: str, identifier: str = "") -> dict[str, object]:
    """Read and verify one segment; TASK_ARCHIVE_UNAVAILABLE when missing, damaged or foreign."""
    try:
        target = _archive_segment_path(root, task_id, sha)
    except ValueError as exc:
        raise _archive_unavailable(identifier, sha, "invalid segment location") from exc
    if not target.is_file():
        raise _archive_unavailable(identifier, sha, "missing")
    try:
        if target.stat().st_size > ARCHIVE_SEGMENT_MAX_BYTES:
            raise _archive_unavailable(identifier, sha, "oversized")
        raw = target.read_bytes()
    except OSError as exc:
        raise _archive_unavailable(identifier, sha, "unreadable") from exc
    if hashlib.sha256(raw).hexdigest() != sha:
        raise _archive_unavailable(identifier, sha, "sha256 mismatch")
    try:
        segment = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _archive_unavailable(identifier, sha, "invalid JSON") from exc
    if (not isinstance(segment, dict) or segment.get("format") != ARCHIVE_SEGMENT_FORMAT
            or segment.get("version") not in _ARCHIVE_SEGMENT_VERSIONS or segment.get("task_id") != task_id
            or not isinstance(segment.get("items"), list)):
        raise _archive_unavailable(identifier, sha, "not a segment of this task")
    return segment


def hydrate_archived(root: Path, state: dict[str, object], collection: str, item: dict[str, object]) -> dict[str, object]:
    """The full object for a schema-10 stub (the item itself when it carries no ``archived`` marker).

    Reads the referenced version-1 segment and verifies its sha256; raises TASK_ARCHIVE_UNAVAILABLE
    when it is missing, damaged or does not hold this object. Stub fields win over segment fields (a
    handoff stub may gain usage or claims after archiving); the segment supplies only moved bodies.
    """
    sha = item.get("archived")
    if sha is None:
        return item
    identifier = str(item.get("id"))
    segment = _read_archive_segment(root, str(state["task_id"]), str(sha), identifier)
    for entry in segment["items"]:
        if isinstance(entry, dict) and entry.get("collection") == collection and entry.get("id") == item.get("id"):
            fields = entry.get("fields")
            if not isinstance(fields, dict):
                break
            full = {key: value for key, value in item.items() if key != "archived"}
            full.update(fields)
            return full
    raise _archive_unavailable(identifier, sha, "segment does not hold this object")


def _evicted_object(root: Path, state: dict[str, object], name: str, identifier: str,
                    located: tuple[int, int | None]) -> tuple[dict[str, object], str]:
    """(object exactly as it was evicted, segment sha) for an indexed id; a schema-10 stub stays a stub."""
    entry = state["archive"][located[0]]
    sha = str(entry["sha256"])
    segment = _read_archive_segment(root, str(state["task_id"]), sha, identifier)
    for item in segment["items"]:
        if (isinstance(item, dict) and item.get("collection") == name and item.get("id") == identifier
                and item.get("position") == located[1] and isinstance(item.get("object"), dict)
                and item["object"].get("id") == identifier):
            return item["object"], sha
    raise _archive_unavailable(identifier, sha, "segment does not hold this object")


def archived_object(root: Path, state: dict[str, object], identifier: str) -> tuple[str, dict[str, object], str] | None:
    """(index collection, full object, segment sha) of an evicted id, or None when it is not evicted."""
    if not _eviction_entries(state):
        return None
    index_map = _index_map(state)
    for name in _INDEX_COLLECTIONS:
        located = index_map[name].get(identifier)
        if located is not None:
            item, sha = _evicted_object(root, state, name, identifier, located)
            hot_name = "verification_results" if name == "check_runs" else name
            return name, hydrate_archived(root, state, hot_name, item), sha
    return None


def _remove_from_index(state: dict[str, object], removed: list[tuple[str, str, dict[str, object] | None]]) -> None:
    """Drop ids from their entries and subtract what those objects contributed to the entry totals.

    ``removed`` holds (index collection, id, object or None for count-only objects). An entry left
    without ids is dropped; ``settled.latest`` keeps naming a re-hydrated judgment (now hot at the
    same position), which keeps every latest/first answer unchanged.
    """
    if not removed:
        return
    index_map = _index_map(state)
    by_entry: dict[int, list[tuple[str, str, dict[str, object] | None]]] = {}
    for name, identifier, item in removed:
        by_entry.setdefault(index_map[name][identifier][0], []).append((name, identifier, item))
    archive = list(state["archive"])
    for number, members in by_entry.items():
        entry = archive[number]
        gone = {(name, identifier) for name, identifier, _ in members}
        ids: dict[str, list[object]] = {}
        for name, encoded in entry["ids"].items():
            remaining = [(identifier, position) for identifier, position in _decode_ids(encoded, name in _POSITIONED)
                         if (name, identifier) not in gone]
            if remaining:
                ids[name] = _encode_ids(remaining, name in _POSITIONED)
        totals = _Totals.load(entry["totals"])
        for name, identifier, item in members:
            if item is None:
                totals.counts[name] -= 1
            else:
                totals.add(name, item, -1)
        archive[number] = {**entry, "ids": ids, "totals": totals.export()} if ids else None
    remaining_entries = [entry for entry in archive if entry is not None]
    if remaining_entries:
        state["archive"] = remaining_entries
    else:
        state.pop("archive", None)
    if not _eviction_entries(state):
        # Every evicted object is hot again, so hot judgments alone answer every latest/first question.
        state.pop("settled", None)


def _rehydrate(root: Path, state: dict[str, object], wanted: list[tuple[str, str]]) -> None:
    """Return evicted objects to their hot lists, at their exact positions, all or nothing.

    ``wanted`` holds (index collection, id). Raises TASK_ARCHIVE_UNAVAILABLE (state unchanged) when
    a segment cannot be read.
    """
    index_map = _index_map(state)
    restored: list[tuple[str, str, dict[str, object], int | None]] = []
    seen: set[tuple[str, str]] = set()
    for name, identifier in wanted:
        if (name, identifier) in seen or identifier not in index_map[name]:
            continue
        seen.add((name, identifier))
        located = index_map[name][identifier]
        item, _ = _evicted_object(root, state, name, identifier, located)
        restored.append((name, identifier, copy.deepcopy(item), located[1]))
    if not restored:
        return
    for hot_name in {("verification_results" if name == "check_runs" else name) for name, _, _, _ in restored}:
        values = _archive_collection(state, hot_name)
        returning = [(position, item) for name, _, item, position in restored
                     if ("verification_results" if name == "check_runs" else name) == hot_name]
        if hot_name in _POSITIONED:
            merged = sorted([*zip(_hot_positions(state, hot_name, index_map), values), *returning], key=lambda pair: pair[0])
            values[:] = [item for _, item in merged]
        else:
            values.extend(item for _, item in returning)
    _remove_from_index(state, [(name, identifier, item) for name, identifier, item, _ in restored])


def _rehydrate_from_state(state: dict[str, object], wanted: list[tuple[str, str]]) -> None:
    """``_rehydrate`` for in-memory transactions: the segments are read under the root ``_load_state`` saw."""
    if not wanted:
        return
    root = _archive_roots.get().get(str(state.get("task_id")))
    if root is None:
        raise ThalirisError(_errors.TASK_ARCHIVE_UNAVAILABLE, "archived task object body is unavailable",
                            recovery="load the task through Core so its archive segments can be read; nothing was recorded",
                            details={"ids": [identifier for _, identifier in wanted][:8], "reason": "no project root is known for this task"})
    _rehydrate(root, state, wanted)


def _cited_evicted_sources(state: dict[str, object]) -> list[str]:
    """Evicted source ids that hot objects (observations, records, artifacts, results, sources) cite."""
    if not _eviction_entries(state):
        return []
    indexed = _index_map(state)["evidence_refs"]
    if not indexed:
        return []
    cited: set[str] = set()
    for item in (state.get("evidence_continuity") or {}).get("observations", []):
        cited.update(item.get("source_refs", []))
    for name in ("records", "artifact_refs", "verification_results", "evidence_refs"):
        for item in state.get(name, []):
            if isinstance(item, dict):
                cited.update(item.get("source_refs", []))
    return sorted(cited & indexed.keys())


def _rehydrate_cited_sources(root: Path, state: dict[str, object]) -> bool:
    """Best effort: bring back evicted sources that hot objects cite again; an unreadable segment
    leaves them evicted (they stay valid references). Returns whether anything came back."""
    changed = False
    unavailable: set[str] = set()
    wanted = _cited_evicted_sources(state)
    while wanted:
        try:
            _rehydrate(root, state, [("evidence_refs", identifier) for identifier in wanted])
            changed = True
        except ThalirisError as exc:
            if exc.code != _errors.TASK_ARCHIVE_UNAVAILABLE:
                raise
            for identifier in wanted:
                try:
                    _rehydrate(root, state, [("evidence_refs", identifier)])
                    changed = True
                except ThalirisError as single:
                    if single.code != _errors.TASK_ARCHIVE_UNAVAILABLE:
                        raise
                    unavailable.add(identifier)
        wanted = [identifier for identifier in _cited_evicted_sources(state) if identifier not in unavailable]
    return changed


def _forget_check_runs(state: dict[str, object], check_id: str, below: int) -> None:
    """Drop evicted results of one check with a run number below ``below`` (``record_check_run`` history)."""
    if not _eviction_entries(state):
        return
    prefix = f"{check_id}.r"
    dropped = []
    for identifier in _index_map(state)["check_runs"]:
        number = identifier[len(prefix):]
        if identifier.startswith(prefix) and number.isdigit() and str(int(number)) == number and int(number) < below:
            dropped.append(("check_runs", identifier, None))
    _remove_from_index(state, dropped)


# --- validation ---

def _validate_archive_index(state: dict[str, object]) -> dict[str, dict[str, tuple[int, int | None]]]:
    """Validate the ``archive`` index and ``settled`` table shapes; returns the evicted-id map.

    Segment contents are never read here. Cross-checks that need the hot lists (references,
    uniqueness against hot ids, totals and latest rows) run in ``_validate_archive_totals``.
    """
    index = state.get("archive")
    stubs = list(_archived_items(state))
    empty: dict[str, dict[str, tuple[int, int | None]]] = {name: {} for name in _INDEX_COLLECTIONS}
    if index is None:
        if stubs:
            raise ThalirisError(_errors.TASK_STATE_INVALID, "archived stub without an archive index",
                                details={"id": str(stubs[0][1].get("id"))})
        if "settled" in state:
            raise ThalirisError(_errors.TASK_STATE_INVALID, "settled table without an archive index")
        return empty
    if state.get("schema_version") < _ARCHIVE_SCHEMA_VERSION:
        raise ThalirisError(_errors.TASK_STATE_INVALID, "archive segments require task schema 10",
                            recovery="preserve the state and use a compatible reader")
    if not isinstance(index, list) or not 1 <= len(index) <= ARCHIVE_INDEX_MAX:
        raise ThalirisError(_errors.TASK_STATE_INVALID, "invalid archive index",
                            details={"expected": f"a list of 1 to {ARCHIVE_INDEX_MAX} segment entries"})
    legacy: dict[str, dict[str, object]] = {}
    shas: set[str] = set()
    evicting = False
    for entry in index:
        if isinstance(entry, dict) and set(entry) == _ARCHIVE_INDEX_FIELDS:
            if (not _is_hex64(entry["sha256"]) or type(entry["revision"]) is not int or not 1 <= entry["revision"] <= state["revision"]
                    or type(entry["items"]) is not int or entry["items"] < 1
                    or not isinstance(entry["collections"], dict) or not entry["collections"]
                    or set(entry["collections"]) - set(_ARCHIVE_COLLECTIONS)
                    or not all(type(count) is int and count >= 1 for count in entry["collections"].values())
                    or sum(entry["collections"].values()) != entry["items"]):
                raise ThalirisError(_errors.TASK_STATE_INVALID, "invalid archive index",
                                    details={"expected": "unique {sha256, revision, items, collections} entries"})
            legacy[entry["sha256"]] = entry
        elif isinstance(entry, dict) and set(entry) == _EVICTION_INDEX_FIELDS:
            evicting = True
            ids = entry["ids"]
            if (not _is_hex64(entry["sha256"]) or type(entry["revision"]) is not int or not 1 <= entry["revision"] <= state["revision"]
                    or not isinstance(ids, dict) or not ids or set(ids) - set(_INDEX_COLLECTIONS)):
                raise ThalirisError(_errors.TASK_STATE_INVALID, "invalid archive index",
                                    details={"expected": "unique {sha256, revision, ids, totals} entries"})
        else:
            raise ThalirisError(_errors.TASK_STATE_INVALID, "invalid archive index",
                                details={"expected": "{sha256, revision, ids, totals} or schema-10 {sha256, revision, items, collections} entries"})
        if entry["sha256"] in shas:
            raise ThalirisError(_errors.TASK_STATE_INVALID, "invalid archive index", details={"expected": "unique segment digests"})
        shas.add(entry["sha256"])
    if (evicting or "settled" in state) and state.get("schema_version") < _EVICTION_SCHEMA_VERSION:
        raise ThalirisError(_errors.TASK_STATE_INVALID, "evicted ledger objects require task schema 11",
                            recovery="preserve the state and use a compatible reader")
    if "settled" in state and not evicting:
        raise ThalirisError(_errors.TASK_STATE_INVALID, "settled table without eviction segments")
    result = empty
    if evicting:
        derived = _archive_derived(state)
        if derived["problem"] is not None:
            code, message, details = derived["problem"]  # type: ignore[misc]
            raise ThalirisError(code, message, details=dict(details))
        result = derived["map"]  # type: ignore[assignment]
    seen: dict[tuple[str, str], int] = {}
    for name, item in stubs:
        sha = item["archived"]
        if not isinstance(sha, str) or sha not in legacy:
            raise ThalirisError(_errors.TASK_STATE_INVALID, "archived stub names an unknown segment",
                                details={"id": str(item.get("id")), "collection": name})
        key = (sha, name)
        seen[key] = seen.get(key, 0) + 1
        if seen[key] > legacy[sha]["collections"].get(name, 0):
            raise ThalirisError(_errors.TASK_STATE_INVALID, "archived stubs exceed their segment entry",
                                details={"segment": sha, "collection": name})
    return result


def _validate_archive_totals(state: dict[str, object], index_map: dict[str, dict[str, tuple[int, int | None]]]) -> None:
    """Cross-check eviction totals and ``settled.latest`` against the ids and hot lists (what is checkable)."""
    entries = state.get("archive") or []
    if not _eviction_entries(state):
        return
    requirements = {item["id"] for item in (state.get("evidence_continuity") or {}).get("requirements", [])}
    for name in _POSITIONED:
        total = len(_archive_collection(state, name)) + len(index_map[name])
        evicted_positions = _archive_derived(state)["positions"][name]  # type: ignore[index]
        if evicted_positions and evicted_positions[-1] >= total:
            raise ThalirisError(_errors.TASK_STATE_INVALID, "invalid archive index ids",
                                details={"collection": name, "expected": f"positions below {total}, the list length"})
    derived = _archive_derived(state)
    counts_by_entry: dict[int, dict[str, int]] = derived["counts"]  # type: ignore[assignment]
    observations_by_entry: dict[int, set[str]] = derived["observations"]  # type: ignore[assignment]
    for number, entry in enumerate(entries):
        if "ids" not in entry:
            continue
        problem = _totals_problem(entry["totals"], counts_by_entry.get(number, {}), observations_by_entry.get(number, set()),
                                  requirements)
        if problem:
            raise ThalirisError(_errors.TASK_STATE_INVALID, "invalid archive totals",
                                details={"segment": entry["sha256"], "expected": problem})
    problem = _latest_rows_problem(state, index_map, requirements)
    if problem:
        raise ThalirisError(_errors.TASK_STATE_INVALID, "invalid settled latest judgments", details={"expected": problem})


def archive_summary(state: dict[str, object]) -> dict[str, object] | None:
    """Counts of archived objects and segments, or None for a task that never archived."""
    index = state.get("archive")
    if not index:
        return None
    by_collection: dict[str, int] = {}
    for name, _ in _archived_items(state):
        by_collection[name] = by_collection.get(name, 0) + 1
    for entry in _eviction_entries(state):
        for name, count in entry["totals"]["counts"].items():
            target = "verification_results" if name == "check_runs" else name
            by_collection[target] = by_collection.get(target, 0) + count
    by_collection = dict(sorted(by_collection.items()))
    return {"segments": len(index), "archived_items": sum(by_collection.values()), "by_collection": by_collection,
            "last_revision": index[-1]["revision"],
            "retrieval": "task-get <id> returns the full object from its segment"}


def task_state_capacity() -> dict[str, int]:
    """The task-state bounds adapters must use instead of hard-coding them.

    ``max_bytes`` bounds the hot ledger file on disk (every read and write); archive segments are
    separate files. ``list_max`` bounds the hot objects of a ledger list (requirements:
    ``archived_list_max``); evicted objects count toward no list cap.
    """
    return {"max_bytes": STATE_MAX_BYTES, "archive_high_water_bytes": STATE_ARCHIVE_HIGH_WATER_BYTES,
            "list_max": STATE_LIST_MAX, "archived_list_max": STATE_ARCHIVED_LIST_MAX,
            "requirements_max": STATE_ARCHIVED_LIST_MAX, "archive_index_max": ARCHIVE_INDEX_MAX,
            "schema_version": _STATE_SCHEMA_VERSION, "supported_schemas": list(_SUPPORTED_SCHEMAS)}


def read_state_bytes(path: Path) -> bytes:
    """Read a ledger file's exact bytes within the Core bound; TASK_STATE_INVALID when it is larger."""
    with Path(path).open("rb") as stream:
        raw = stream.read(STATE_MAX_BYTES + 1)
    if len(raw) > STATE_MAX_BYTES:
        raise ThalirisError(_errors.TASK_STATE_INVALID, "task state exceeds 512 KiB",
                            details={"limit": STATE_MAX_BYTES})
    return raw


def _load_state(root: Path, *, active: bool = False) -> dict[str, object]:
    path = _state_path(root)
    if path.is_symlink():
        raise ValueError("task state final component must not be a symlink")
    _safe_without_final_symlink(root, path.relative_to(root).as_posix())
    if not path.is_file():
        raise ThalirisError(_errors.TASK_STATE_MISSING, "no current task state",
                            recovery="select an existing task with --task-id or start one with task-start",
                            details={"task_id": selected_task(root)})
    if path.stat().st_size > STATE_MAX_BYTES:
        raise ThalirisError(_errors.TASK_STATE_INVALID, "task state exceeds 512 KiB")
    try:
        with path.open("rb") as stream:
            raw_bytes = stream.read(STATE_MAX_BYTES + 1)
        if len(raw_bytes) > STATE_MAX_BYTES:
            raise ThalirisError(_errors.TASK_STATE_INVALID, "task state exceeds 512 KiB")
        raw = json.loads(raw_bytes.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ThalirisError(_errors.TASK_STATE_INVALID, "invalid task state JSON") from exc
    except UnicodeDecodeError as exc:
        raise ThalirisError(_errors.TASK_STATE_INVALID, "invalid task state encoding") from exc
    state = _promoted_prior_state(root, raw)
    if state is None:
        incompatible = _task_state_schema_diagnostic(raw, raw_bytes)
        if incompatible is not None:
            task_id = raw.get("task_id") if isinstance(raw, dict) and isinstance(raw.get("task_id"), str) else None
            raise TaskStateSchemaIncompatible(incompatible, task_id)
        state = _validate_state(root, raw)
    if selected_task(root) is not None and state["task_id"] != selected_task(root):
        raise ThalirisError(_errors.TASK_IDENTITY_CONFLICT, "task identity conflict",
                            details={"selected_task_id": selected_task(root), "task_id": state["task_id"]})
    if active and state["status"] != "ACTIVE":
        raise ThalirisError(_errors.TASK_NOT_ACTIVE, "current task is not ACTIVE",
                            recovery="start a new task; a DONE task accepts no writes",
                            details={"task_id": state["task_id"], "status": state["status"]})
    _register_archive_root(root, state)
    return state


def _task_object_ids(state: dict[str, object]) -> set[str]:
    """Return the single task-wide identity set for addressable objects (evicted ids stay reserved)."""
    return {
        str(item["id"])
        for field in ("evidence_refs", "records", "artifact_refs", "verification_results")
        for item in state[field]
    } | {str(item["id"]) for item in state.get("checks", [])} | {
        str(item["id"]) for values in state.get("evidence_continuity", {}).values() for item in values} | _indexed_ids(state)


INPUT_ENCODINGS = ("UTF-8", "UTF-8 with BOM", "UTF-16 with BOM")


def decode_input_bytes(raw: bytes, label: str = "task input") -> str:
    """Decode JSON input bytes: UTF-8, UTF-8 with BOM or UTF-16 with BOM.

    Shells on Windows commonly write UTF-8 with a BOM or UTF-16LE with a BOM.
    Anything else (including BOM-less UTF-16 and UTF-32) is refused with a
    stable decoding error instead of a locale guess.
    """
    if not isinstance(raw, (bytes, bytearray)):
        raise TypeError("input bytes required")
    raw = bytes(raw)
    encoding = "utf-8"
    if raw.startswith((b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff")):
        encoding = None
    elif raw.startswith(b"\xef\xbb\xbf"):
        encoding = "utf-8-sig"
    elif raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        encoding = "utf-16"
    try:
        if encoding is None:
            raise UnicodeDecodeError("utf-32", raw[:4], 0, 4, "UTF-32 is not accepted")
        text = raw.decode(encoding)
        if "\x00" in text:
            # JSON text never contains a raw NUL; this is BOM-less UTF-16/32.
            encoding = "utf-16 or utf-32 without BOM"
            position = text.index("\x00")
            raise UnicodeDecodeError("utf-8", raw, position, position + 1, "NUL byte in JSON input")
        return text
    except UnicodeDecodeError as exc:
        raise ThalirisError(
            _errors.INPUT_DECODING_ERROR,
            f"{label} is not valid UTF-8, UTF-8 with BOM, or UTF-16 with BOM",
            recovery="re-encode the input as UTF-8 (a BOM is accepted) and retry",
            details={"expected_encodings": list(INPUT_ENCODINGS), "detected": encoding or "utf-32",
                     "offset": exc.start},
        ) from exc


def _read_input_text(value: str) -> str:
    if value == "-":
        buffer = getattr(sys.stdin, "buffer", None)
        if buffer is None:
            return sys.stdin.read()
        return decode_input_bytes(buffer.read())
    return decode_input_bytes(Path(value).read_bytes())


def _read_input(value: str | None) -> dict[str, object]:
    if value is None:
        return {}
    source = _read_input_text(value)
    try:
        raw = json.loads(source)
    except json.JSONDecodeError as exc:
        raise ThalirisError(
            _errors.INPUT_JSON_INVALID, str(exc),
            recovery="supply one JSON object",
            details={"line": exc.lineno, "column": exc.colno},
        ) from exc
    _check_json(raw)
    if not isinstance(raw, dict):
        raise ThalirisError(_errors.INPUT_NOT_OBJECT, "task input must be a JSON object",
                            recovery="wrap the payload in a JSON object")
    return raw


def _blank_state(root: Path, goal: str, milestone: str | None) -> dict[str, object]:
    return {
        "schema_version": _STATE_SCHEMA_VERSION,
        "revision": 1,
        "task_id": str(uuid.uuid4()),
        "status": "ACTIVE",
        "goal": goal,
        "current_milestone": milestone,
        "records": [],
        "active_work": [],
        "pending_results": [],
        "artifact_refs": [],
        "evidence_refs": [],
        "verification_results": [],
        "task_surface_baseline": _surface_snapshot(root),
        "task_base_head": _git_head(root),
    }


def _ensure_root_navigation(root: Path) -> list[str]:
    writes: dict[str, bytes] = {}
    for relative, content in _template_files().items():
        if relative not in {".agent-memory/INDEX.md", ".milestones/INDEX.md"}:
            continue
        lexical = root.joinpath(*relative.split("/"))
        if lexical.exists() or lexical.is_symlink():
            continue
        _valid_relative(root, relative)
        writes[relative] = content
    if writes:
        _apply_with_backup(root, writes, [], "task-start-navigation")
    return sorted(writes)


def _normalize_new_record(value: object, *, producer: str, revision: int, known_sources: set[str], known_records: set[str]) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("invalid task record")
    allowed = {"id", "kind", "text", "producer", "revision", "source_refs", "status", "supersedes"}
    if set(value) - allowed:
        raise ValueError("invalid task record")
    record = {
        "id": value.get("id"),
        "kind": value.get("kind"),
        "text": value.get("text"),
        "producer": value.get("producer", producer),
        "revision": value.get("revision", revision),
        "source_refs": value.get("source_refs", []),
        "status": value.get("status", "RECORDED"),
        "supersedes": value.get("supersedes", []),
    }
    _record(record, known_sources, known_records)
    return record


def _task_ack(state: dict[str, object], changed: list[str]) -> dict[str, object]:
    return {
        "ok": True,
        "task_id": state["task_id"],
        "revision": state["revision"],
        "status": state["status"],
        "changed": sorted(set(changed)),
    }


def task_write_response(state: dict[str, object], changed: list[str], *, appended: list[str] | None = None,
                        evidence_offset: int = 0, max_bytes: int | None = None) -> dict[str, object]:
    """Compact write acknowledgement for adapters: ack plus evidence summary.

    Replaces echoing the full Evidence Continuity page after each write. The
    summary keeps totals and a bounded open-item listing (see
    ``evidence_summary``).
    """
    response = _task_ack(state, changed)
    if appended is not None:
        response["appended"] = list(appended)
    budget = {} if max_bytes is None else {"max_bytes": max_bytes}
    response["evidence"] = evidence_summary(state, evidence_offset, **budget)
    return response


def task_start(root: Path, goal: str, milestone: str | None, input_file: str | None, *, actor: str = "unspecified") -> dict[str, object]:
    root = _repo_root(root)
    if _git_root(root) is not None and not _state_ignored(root):
        raise ValueError("task state is not ignored; run context init first")
    if not isinstance(goal, str) or not goal.strip() or len(goal) > 16_384:
        raise ValueError("goal must not be empty")
    partial = _read_input(input_file)
    allowed = {"records", "active_work", "pending_results", "evidence_refs"}
    if set(partial) - allowed:
        raise ValueError("task-start accepts only mechanical ledger fields")
    with _lock(root):
        _ensure_root_navigation(root)
        state = _blank_state(root, goal, milestone)
        state["active_work"] = partial.get("active_work", [])
        state["pending_results"] = partial.get("pending_results", [])
        state["evidence_refs"] = partial.get("evidence_refs", [])
        source_ids = {str(item.get("id")) for item in state["evidence_refs"] if isinstance(item, dict)}
        known: set[str] = set()
        for item in partial.get("records", []):
            record = _normalize_new_record(item, producer=actor, revision=1, known_sources=source_ids, known_records=known)
            state["records"].append(record)
            known.add(str(record["id"]))
        # Every new task gets its own ledger. The historical singleton is never
        # a vacant slot: its missing bytes may still belong to a recovery anchor.
        # New tasks have independent ledgers even when the old one is ACTIVE,
        # corrupt, or carries unresolved native dependencies.
        target = _safe_without_final_symlink(root, f".context/tasks/{state['task_id']}/state.json")
        _atomic_write(target, _state_payload(root, state))
        select_task(root, str(state["task_id"]))
    return _task_ack(state, ["task"])


def task_update(root: Path, actor: str, base_revision: int, input_file: str | None) -> dict[str, object]:
    root = _repo_root(root)
    if not isinstance(actor, str) or not actor or type(base_revision) is not int:
        raise ValueError("invalid task update identity or revision")
    partial = _read_input(input_file)
    allowed = {"records", "active_work", "pending_results", "evidence_refs", "current_milestone"}
    if not partial or set(partial) - allowed:
        raise ValueError("task-update accepts only mechanical ledger fields")
    with _lock(root):
        state = _load_state(root, active=True)
        check_revision(state, base_revision)
        changed: list[str] = []
        if "evidence_refs" in partial:
            additions = partial["evidence_refs"]
            if not isinstance(additions, list):
                raise ValueError("evidence_refs must be append-only additions")
            known_source_ids = _known_ids(state, "evidence_refs")
            for item in additions:
                _evidence_ref(item, known_source_ids)
                if any(ref not in known_source_ids for ref in item.get("source_refs", [])):
                    raise ValueError("source reference points to an unknown source")
                state["evidence_refs"].append(item)
                known_source_ids.add(str(item["id"]))
            changed.append("evidence_refs")
        if "records" in partial:
            additions = partial["records"]
            if not isinstance(additions, list) or not additions:
                raise ValueError("records must be append-only additions")
            known_sources = _known_ids(state, "evidence_refs")
            known_records = _known_ids(state, "records")
            for item in additions:
                record = _normalize_new_record(item, producer=actor, revision=base_revision + 1, known_sources=known_sources, known_records=known_records)
                state["records"].append(record)
                known_records.add(str(record["id"]))
            changed.append("records")
        for field in ("active_work", "pending_results", "current_milestone"):
            if field in partial:
                state[field] = partial[field]
                changed.append(field)
        state["revision"] = base_revision + 1
        _write_state(root, state)
    return _task_ack(state, changed)


_CONTINUITY_KINDS = ("requirements", "handoffs", "observations", "judgments")
_CONTINUITY_SCHEMAS = {
    "requirements": {"id", "workchain_ref"},
    "handoffs": {"id", "parent_handoff_id", "candidate", "producer", "requirement_refs"},
    "observations": {"id", "task_id", "producer", "candidate", "handoff_id", "requirement_refs", "source_refs", "text"},
    "judgments": {"id", "task_id", "producer", "candidate", "requirement_ref", "observation_refs", "outcome", "reasoning"},
}
# Historical handoff observations retain their exact shape. Controller-local
# facts have explicit provenance and no invented native handoff or actor.
_CONTINUITY_OPTIONAL = {
    "requirements": {"kind", "surface"},
    "handoffs": {"durable_paths", "claims", "usage", "archived"},
    "observations": {"native_actor", "submitted_by", "native_status", "native_status_conflict", "observed_state", "provenance",
                     "claim", "mechanism", "archived"},
    "judgments": {"judgment_refs", "override_reason", "overridden_checks", "archived"},
}
# Fields Core alone assigns: a model-authored register/observe payload may not carry them.
# ``override_reason`` is model-authored but enters through the judgment gate, which records
# what it overrode.
_CORE_ASSIGNED_CONTINUITY_FIELDS = {
    "requirements": set(),
    "handoffs": {"claims", "usage", "archived"},
    "observations": {"claim", "mechanism", "archived"},
    "judgments": {"override_reason", "overridden_checks", "archived"},
}
# A requirement's kind says how far declared checks can decide it. Unspecified (and every
# requirement written before Core 0.6.0) is judgment-only, which changes no behaviour.
REQUIREMENT_KINDS = ("compiled", "partial", "judgment-only")
REQUIREMENT_KIND_DEFAULT = "judgment-only"
REQUIREMENT_SURFACES = ("contract",)
# Producer label of observations Core appends itself. No model or adapter may use it.
MECHANISM_PRODUCER = "mechanism"
_JUDGMENT_OUTCOMES = ("satisfied", "unknown", "repair", "no-current-impact")
_LABEL_EXPECTATION = "1-64 characters matching [A-Za-z0-9_.:-]+"
CONTINUITY_BATCH_MAX = 64
EVIDENCE_SUMMARY_MAX_BYTES = 1536
CHANGES_SINCE_MAX_BYTES = 2048


def _continuity(state: dict[str, object]) -> dict[str, list]:
    return state.setdefault("evidence_continuity", {name: [] for name in _CONTINUITY_KINDS})


def _preview(value: object, limit: int = 120) -> str:
    text = json.dumps(value, ensure_ascii=False)
    return text if len(text) <= limit else text[:limit] + "..."


def _continuity_error(code: str, message: str, kind: str | None = None, index: int | None = None,
                      item: object = None, *, field: str | None = None, expected: str | None = None,
                      got: object = None, recovery: str | None = None,
                      extra: dict[str, object] | None = None) -> ThalirisError:
    """Name the offending collection, item, field and expected format.

    ``str(error)`` starts with the historical generic message so existing
    message checks keep matching; the location follows after ``": "``.
    """
    identifier = item.get("id") if isinstance(item, dict) and isinstance(item.get("id"), str) else None
    parts: list[str] = []
    if kind is not None:
        parts.append(f"{kind}[{index}]" + (f" ({identifier})" if identifier else ""))
    if field is not None:
        parts.append(field)
    text = message + (": " + " ".join(parts) if parts else "")
    if expected is not None:
        text += f" must be {expected}"
    if got is not None:
        text += f"; got {_preview(got)}"
    details: dict[str, object] = {"collection": kind, "index": index, "id": identifier, "field": field, "expected": expected}
    if got is not None:
        details["got"] = _preview(got)
    if extra:
        details.update(extra)
    return ThalirisError(code, text, recovery=recovery, details=details)


def _validate_continuity(state: dict[str, object],
                         index_map: dict[str, dict[str, tuple[int, int | None]]] | None = None) -> None:
    data = state.get("evidence_continuity")
    if "evidence_continuity" not in state:
        return
    if not isinstance(data, dict) or set(data) != set(_CONTINUITY_KINDS):
        raise ThalirisError(_errors.CONTINUITY_INVALID, "invalid evidence continuity",
                            details={"expected": list(_CONTINUITY_KINDS)})
    if index_map is None:
        index_map = _index_map(state)
    owners: dict[str, tuple[str, dict[str, object] | None]] = {}
    indexed_all: set[str] = _archive_derived(state)["ids"] if _eviction_entries(state) else set()  # type: ignore[assignment]
    for field in ("records", "evidence_refs", "artifact_refs", "verification_results", "checks"):
        for item in state.get(field, []):
            if isinstance(item, dict):
                owners[str(item.get("id"))] = (field, item)
    requirements, handoffs, observations = {}, {}, {}
    # Evicted handoffs, observations and judgments are present for references; their fields were
    # checked when they were appended, so checks that read a referent's fields skip evicted ones.
    evicted_handoffs, evicted_observations, evicted_judgments = (
        index_map["handoffs"], index_map["observations"], index_map["judgments"])
    sources = {item["id"] for item in state["evidence_refs"]} | set(index_map["evidence_refs"])

    def label(kind, index, item, field, text):
        value = item[field]
        if not isinstance(value, str) or not value.strip() or len(value) > 64 or not re.fullmatch(r"[A-Za-z0-9_.:-]+", value):
            raise _continuity_error(_errors.CONTINUITY_INVALID, f"invalid {text}", kind, index, item,
                                    field=field, expected=_LABEL_EXPECTATION, got=value)

    def refs(kind, index, item, field, known, expected, *, suggest=None):
        value = item.get(field, []) if field == "judgment_refs" else item[field]
        if not isinstance(value, list) or len(value) > 64 or not all(isinstance(ref, str) for ref in value):
            raise _continuity_error(_errors.CONTINUITY_REFERENCE_INVALID, "invalid continuity references", kind, index, item,
                                    field=field, expected="a list of at most 64 id strings", got=value)
        if len(set(value)) != len(value):
            duplicates = sorted({ref for ref in value if value.count(ref) > 1})
            raise _continuity_error(_errors.CONTINUITY_REFERENCE_INVALID, "invalid continuity references", kind, index, item,
                                    field=field, expected="unique ids", got=duplicates)
        unknown = [ref for ref in value if ref not in known]
        if unknown:
            extra: dict[str, object] = {"unknown_refs": unknown[:8]}
            if suggest is not None:
                suggestions = {ref: suggest(ref) for ref in unknown[:8]}
                suggestions = {ref: hits for ref, hits in suggestions.items() if hits}
                if suggestions:
                    extra["suggestions"] = suggestions
            raise _continuity_error(_errors.CONTINUITY_REFERENCE_INVALID, "invalid continuity references", kind, index, item,
                                    field=field, expected=expected, got=unknown[:8], extra=extra,
                                    recovery="use exact ids as task-get or task-status report them")

    def similar_observations(ref):
        # Adapters may store handoff-qualified ids (``<handoff>.<id>``).
        return sorted(identifier for identifier in observations
                      if identifier.endswith("." + ref) or ref.endswith("." + identifier))[:4]

    for kind in _CONTINUITY_KINDS:
        values = data[kind]
        fields = _CONTINUITY_SCHEMAS[kind]
        optional = _CONTINUITY_OPTIONAL[kind]
        if not isinstance(values, list):
            raise ThalirisError(_errors.CONTINUITY_INVALID, "invalid continuity collection",
                                details={"collection": kind, "expected": "a JSON list"})
        for index, item in enumerate(values):
            if not isinstance(item, dict) or set(item) - optional != fields:
                present = set(item) if isinstance(item, dict) else set()
                missing = sorted(fields - present)
                unexpected = sorted(present - fields - optional)
                raise _continuity_error(
                    _errors.CONTINUITY_INVALID, "invalid continuity object", kind, index, item,
                    expected=f"an object with fields {sorted(fields)} and optional {sorted(optional)}",
                    extra={"missing_fields": missing, "unexpected_fields": unexpected},
                    got={"missing": missing, "unexpected": unexpected} if isinstance(item, dict) else item)
            label(kind, index, item, "id", "continuity id")
            identifier = item["id"]
            if identifier in owners or identifier in indexed_all:
                owner_kind, owner = owners.get(identifier) or (
                    next(name for name, bucket in index_map.items() if identifier in bucket), None)
                extra = {"existing_collection": owner_kind}
                recovery = "choose an id that is unused in this task; nothing was recorded"
                if kind == "observations" and owner_kind == "observations" and owner is not None:
                    extra["existing_handoff_id"] = owner.get("handoff_id")
                    extra["handoff_id"] = item.get("handoff_id")
                    qualified = f"{item.get('handoff_id')}.{identifier}"
                    if (isinstance(item.get("handoff_id"), str) and not identifier.startswith(f"{item['handoff_id']}.")
                            and len(qualified) <= 64 and re.fullmatch(r"[A-Za-z0-9_.:-]+", qualified)):
                        extra["suggested_id"] = qualified
                        recovery = f"resubmit with the handoff-qualified id {qualified!r}; nothing was recorded"
                raise _continuity_error(_errors.CONTINUITY_ID_COLLISION, "task object id collision", kind, index, item,
                                        field="id", expected="unique among all task objects", extra=extra, recovery=recovery)
            owners[identifier] = (kind, item)
            if ((_SCHEMA9_CONTINUITY_FIELDS[kind] & item.keys() or (kind == "observations" and item.get("provenance") == MECHANISM_PRODUCER))
                    and state.get("schema_version") < _VERIFICATION_SCHEMA_VERSION):
                raise _continuity_error(_errors.CONTINUITY_INVALID, "verification-first continuity fields require task schema 9", kind, index, item,
                                        expected="schema 9; preserve the state and use a compatible reader",
                                        got=sorted(_SCHEMA9_CONTINUITY_FIELDS[kind] & item.keys()))
            for field in sorted(fields - {"id", "parent_handoff_id", "requirement_refs", "source_refs", "observation_refs", "text", "reasoning"}
                                - ({"handoff_id"} if kind == "observations" and item.get("provenance") in {"controller-local", MECHANISM_PRODUCER} else set())):
                label(kind, index, item, field, field)
            if kind == "requirements":
                if "kind" in item and item["kind"] not in REQUIREMENT_KINDS:
                    raise _continuity_error(_errors.CONTINUITY_INVALID, "invalid requirement kind", kind, index, item,
                                            field="kind", expected="one of " + ", ".join(REQUIREMENT_KINDS) + " or omitted", got=item["kind"])
                if "surface" in item and item["surface"] not in REQUIREMENT_SURFACES:
                    raise _continuity_error(_errors.CONTINUITY_INVALID, "invalid requirement surface", kind, index, item,
                                            field="surface", expected="one of " + ", ".join(REQUIREMENT_SURFACES) + " or omitted", got=item["surface"])
                requirements[identifier] = item
            elif kind == "handoffs":
                for field, validator in (("claims", _claims_marker_problem), ("usage", _usage_problem)):
                    if field in item:
                        problem = validator(item[field])
                        if problem:
                            raise _continuity_error(_errors.CONTINUITY_INVALID, f"invalid handoff {field}", kind, index, item,
                                                    field=field, expected=problem)
                if "durable_paths" in item and (not isinstance(item["durable_paths"], list) or not all(isinstance(path, str) for path in item["durable_paths"])):
                    raise _continuity_error(_errors.CONTINUITY_INVALID, "invalid handoff durable paths", kind, index, item,
                                            field="durable_paths", expected="a list of strings", got=item["durable_paths"])
                refs(kind, index, item, "requirement_refs", requirements, "requirement ids registered in this task")
                if not item["requirement_refs"] and item["parent_handoff_id"] is None:
                    raise _continuity_error(_errors.CONTINUITY_REFERENCE_INVALID, "handoff requires requirement refs", kind, index, item,
                                            field="requirement_refs", expected="non-empty for a root handoff (parent_handoff_id null)")
                parent = item["parent_handoff_id"]
                if parent is not None and not (isinstance(parent, str) and parent in evicted_handoffs and parent not in handoffs):
                    if not isinstance(parent, str) or parent not in handoffs:
                        raise _continuity_error(_errors.CONTINUITY_PROVENANCE_CONFLICT, "invalid parent handoff provenance", kind, index, item,
                                                field="parent_handoff_id", expected="null or the id of an earlier registered handoff", got=parent)
                    widened = sorted(set(item["requirement_refs"]) - set(handoffs[parent]["requirement_refs"]))
                    if widened:
                        raise _continuity_error(_errors.CONTINUITY_PROVENANCE_CONFLICT, "invalid parent handoff provenance", kind, index, item,
                                                field="requirement_refs", expected=f"a subset of parent handoff {parent}'s requirement_refs",
                                                got=widened)
                handoffs[identifier] = item
            elif kind == "observations":
                for field, text in (("native_actor", "native actor"), ("submitted_by", "observation submitter"), ("native_status", "observed native status"), ("observed_state", "observed local state")):
                    if field in item:
                        label(kind, index, item, field, text)
                if "native_status_conflict" in item and type(item["native_status_conflict"]) is not bool:
                    raise _continuity_error(_errors.CONTINUITY_INVALID, "invalid observed native status conflict", kind, index, item,
                                            field="native_status_conflict", expected="a boolean", got=item["native_status_conflict"])
                local = item.get("provenance") == "controller-local"
                mechanical = item.get("provenance") == MECHANISM_PRODUCER
                if local and state.get("schema_version") < _CONTROLLER_LOCAL_SCHEMA_VERSION:
                    raise _continuity_error(_errors.CONTINUITY_PROVENANCE_CONFLICT, "Controller local provenance requires task schema 8", kind, index, item,
                                            expected="schema 8; preserve the state and use a compatible reader")
                if "provenance" in item and not (local or mechanical):
                    raise _continuity_error(_errors.CONTINUITY_PROVENANCE_CONFLICT, "invalid observation provenance", kind, index, item,
                                            field="provenance", expected="controller-local or omitted")
                if local and (item["producer"] != "controller" or item["handoff_id"] is not None
                              or {"native_actor", "submitted_by", "native_status", "native_status_conflict"} & item.keys()):
                    raise _continuity_error(_errors.CONTINUITY_PROVENANCE_CONFLICT, "Controller local observation provenance conflict", kind, index, item,
                                            expected="Controller producer, null handoff_id and no native execution or import fields")
                if mechanical != ("mechanism" in item) or (mechanical and (
                        item["producer"] != MECHANISM_PRODUCER or item["handoff_id"] is not None or "claim" in item
                        or _mechanism_problem(item["mechanism"])
                        or {"native_actor", "submitted_by", "native_status", "native_status_conflict", "observed_state"} & item.keys())):
                    raise _continuity_error(_errors.CONTINUITY_PROVENANCE_CONFLICT, "mechanical observation provenance conflict", kind, index, item,
                                            expected="producer and provenance `mechanism` together, null handoff_id and one valid mechanism record")
                if "claim" in item:
                    problem = _claim_record_problem(item["claim"])
                    if problem:
                        raise _continuity_error(_errors.CONTINUITY_INVALID, "invalid typed claim record", kind, index, item,
                                                field="claim", expected=problem)
                local = local or mechanical  # both are detached from any native handoff
                handoff = handoffs.get(item["handoff_id"]) if not local else None
                if handoff is None and not local and item["handoff_id"] in evicted_handoffs:
                    # The handoff was evicted after this observation was checked against it (a new
                    # observation re-hydrates its handoff first, see ``_append_continuity_items``):
                    # only the registered-requirement and source checks below can run.
                    refs(kind, index, item, "requirement_refs", requirements, "registered task requirement ids")
                elif handoff is None and not local:
                    raise _continuity_error(_errors.CONTINUITY_PROVENANCE_CONFLICT, "observation handoff provenance conflict", kind, index, item,
                                            field="handoff_id", expected="the id of a registered handoff", got=item["handoff_id"])
                for field in (() if local or handoff is None else ("producer", "candidate")):
                    if item[field] != handoff[field]:
                        raise _continuity_error(_errors.CONTINUITY_PROVENANCE_CONFLICT, "observation handoff provenance conflict", kind, index, item,
                                                field=field, expected=f"{handoff[field]!r} as registered on handoff {handoff['id']}", got=item[field])
                if local or handoff is not None:
                    selected_refs = requirements if local else handoff["requirement_refs"]
                    refs(kind, index, item, "requirement_refs", selected_refs,
                         "registered task requirement ids" if local else f"a subset of handoff {handoff['id']}'s requirement_refs {handoff['requirement_refs']}")
                if (local or handoff is not None) and not item["requirement_refs"] and (local or handoff["requirement_refs"]) and "claim" not in item:
                    raise _continuity_error(_errors.CONTINUITY_REFERENCE_INVALID, "observation requires requirement refs", kind, index, item,
                                            field="requirement_refs", expected="non-empty registered requirement ids" if local else f"non-empty; handoff {handoff['id']} carries {handoff['requirement_refs']}")
                source_refs = item["source_refs"]
                expected = "1-64 unique ids of sources registered in evidence_refs or embedded in this observation's `sources`"
                if not isinstance(source_refs, list) or not source_refs or len(source_refs) > 64 or not all(isinstance(ref, str) for ref in source_refs) or len(source_refs) != len(set(source_refs)):
                    raise _continuity_error(_errors.CONTINUITY_REFERENCE_INVALID, "invalid observation source refs", kind, index, item,
                                            field="source_refs", expected=expected, got=source_refs)
                unknown = [ref for ref in source_refs if ref not in sources]
                if unknown:
                    raise _continuity_error(_errors.CONTINUITY_REFERENCE_INVALID, "invalid observation source refs", kind, index, item,
                                            field="source_refs", expected=expected, got=unknown[:8], extra={"unknown_refs": unknown[:8]})
                observations[identifier] = item
            else:
                if not item["observation_refs"]:
                    raise _continuity_error(_errors.CONTINUITY_REFERENCE_INVALID, "judgment requires exact observation refs", kind, index, item,
                                            field="observation_refs", expected="a non-empty list of registered observation ids")
                if item["requirement_ref"] not in requirements:
                    raise _continuity_error(_errors.CONTINUITY_REFERENCE_INVALID, "invalid requirement judgment", kind, index, item,
                                            field="requirement_ref", expected="the id of a registered requirement", got=item["requirement_ref"])
                if item["outcome"] not in _JUDGMENT_OUTCOMES:
                    raise _continuity_error(_errors.CONTINUITY_INVALID, "invalid requirement judgment", kind, index, item,
                                            field="outcome", expected="one of " + ", ".join(_JUDGMENT_OUTCOMES), got=item["outcome"])
                if {"override_reason", "overridden_checks"} & item.keys():
                    problem = _override_problem(item.get("override_reason"), item.get("overridden_checks"))
                    if problem or item["outcome"] != "satisfied":
                        raise _continuity_error(_errors.CONTINUITY_INVALID, "invalid judgment override", kind, index, item,
                                                field="override_reason", expected=problem or "an override only on a satisfied judgment")
                refs(kind, index, item, "observation_refs", observations.keys() | evicted_observations.keys() if evicted_observations else observations,
                     "exact ids of observations registered in this task (as stored, e.g. adapter handoff-qualified ids)",
                     suggest=similar_observations)
                prior = {j["id"]: j for j in data["judgments"][:index]}
                refs(kind, index, item, "judgment_refs", prior.keys() | evicted_judgments.keys() if evicted_judgments else prior,
                     "ids of judgments that precede this one in list order (earlier items of the same batch count)")
                # An evicted judgment's requirement was checked when the citing judgment was appended
                # (a new judgment re-hydrates the judgments it addresses first).
                foreign = [ref for ref in item.get("judgment_refs", []) if ref in prior and prior[ref]["requirement_ref"] != item["requirement_ref"]]
                if foreign:
                    raise _continuity_error(_errors.CONTINUITY_REFERENCE_INVALID, "judgment continuity requirement conflict", kind, index, item,
                                            field="judgment_refs", expected=f"judgments about the same requirement {item['requirement_ref']}",
                                            got=foreign)
                # Applicability to the selected candidate and requirement is a model
                # judgment. Observations retain their original provenance unchanged.
            if kind in {"observations", "judgments"}:
                if item["task_id"] != state["task_id"]:
                    raise _continuity_error(_errors.CONTINUITY_PROVENANCE_CONFLICT, "continuity task identity conflict", kind, index, item,
                                            field="task_id", expected=f"the current task id {state['task_id']}", got=item["task_id"])
                body_field = "text" if kind == "observations" else "reasoning"
                body = item[body_field]
                if not isinstance(body, str) or not body.strip() or len(body) > 16_384:
                    raise _continuity_error(_errors.CONTINUITY_INVALID, "invalid continuity reasoning or text", kind, index, item,
                                            field=body_field, expected="non-empty text of at most 16384 characters")


def _continuity_open(state: dict[str, object], *, latest: bool = True) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    """Return (unincorporated, unresolved judgments, latest judgments) in ledger order.

    Open evidence is never evicted, and every judgment that cites a hot observation or resolves a
    hot judgment stays hot (``_hot_keep``), so the first two come from the hot lists alone. Latest
    judgments combine hot judgments with ``settled.latest`` (``_judgment_keys``); ``latest=False``
    skips them.
    """
    data = state.get("evidence_continuity", {})
    judgments = data.get("judgments", [])
    incorporated = {(j["requirement_ref"], ref) for j in judgments for ref in j["observation_refs"]}
    pending = [{"requirement_ref": ref, "observation_id": observation["id"], "candidate": observation["candidate"], "handoff_id": observation["handoff_id"]}
               for observation in data.get("observations", []) for ref in observation["requirement_refs"] if (ref, observation["id"]) not in incorporated]
    cited = {ref for j in judgments for ref in j["observation_refs"]}
    pending.extend({"requirement_ref": None, "observation_id": o["id"], "candidate": o["candidate"], "handoff_id": o["handoff_id"]}
                   for o in data.get("observations", []) if not o["requirement_refs"] and o["id"] not in cited)
    # Explicit model-authored continuity edges address a prior decision basis.
    # Legacy exact recitation of its complete observation basis also suffices.
    addressed = {ref for j in judgments for ref in j.get("judgment_refs", [])}
    unresolved = []
    for index, j in enumerate(judgments):
        if j["outcome"] not in {"repair", "unknown"} or j["id"] in addressed:
            continue
        if any(later["requirement_ref"] == j["requirement_ref"] and set(j["observation_refs"]) <= set(later["observation_refs"])
               for later in judgments[index + 1:]):
            continue
        unresolved.append({key: j[key] for key in ("id", "candidate", "requirement_ref", "outcome")})
    latest_items = [{"id": row[2], "candidate": candidate, "requirement_ref": requirement,
                     "outcome": _JUDGMENT_OUTCOMES[row[3] % 4], "observation_ref_count": row[4]}
                    for (requirement, candidate), row in _judgment_keys(state)] if latest else []
    return pending, unresolved, latest_items


def _continuity_status(state: dict[str, object], offset: int = 0) -> dict[str, object]:
    if type(offset) is not int or offset < 0:
        raise ValueError("invalid evidence offset")
    pending, unresolved, judgments = _continuity_open(state)
    entries = [("unincorporated", item) for item in pending] + [("unresolved_judgments", item) for item in unresolved] + [("latest_judgments", item) for item in judgments]
    response = {"unincorporated": [], "unresolved_judgments": [], "latest_judgments": [], "unincorporated_total": len(pending), "unresolved_judgments_total": len(unresolved), "latest_judgments_total": len(judgments), "offset": offset, "next_offset": None}
    for index in range(offset, len(entries)):
        kind, item = entries[index]
        response[kind].append(item)
        response["next_offset"] = index + 1 if index + 1 < len(entries) else None
        if len(json.dumps(response, ensure_ascii=False).encode("utf-8")) > 4096:
            response[kind].pop()
            response["next_offset"] = index
            break
    return response


def _compact_size(value: object) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def evidence_summary(state: dict[str, object], offset: int = 0, *, max_bytes: int = EVIDENCE_SUMMARY_MAX_BYTES) -> dict[str, object]:
    """Compact open-evidence summary for write responses and compact status.

    Totals are always present. Open items (unincorporated observation edges,
    then unresolved repair/unknown judgments) are listed one compact entry
    each, in ledger order, within ``max_bytes`` of compact JSON; ``next_offset``
    pages the rest so open evidence is never dropped from re-presentation.
    Latest judgments are counted, not listed (see the full status view).
    """
    if type(offset) is not int or offset < 0:
        raise ValueError("invalid evidence offset")
    if type(max_bytes) is not int or max_bytes < 256:
        raise ValueError("invalid evidence summary budget")
    pending, unresolved, latest = _continuity_open(state)
    entries = [("unincorporated", {"observation_id": item["observation_id"], "requirement_ref": item["requirement_ref"],
                                   "handoff_id": item["handoff_id"], "candidate": item["candidate"]}) for item in pending]
    entries += [("unresolved_judgments", item) for item in unresolved]
    response: dict[str, object] = {
        "unincorporated_total": len(pending),
        "unresolved_judgments_total": len(unresolved),
        "latest_judgments_total": len(latest),
        "unincorporated": [],
        "unresolved_judgments": [],
        "offset": offset,
        "next_offset": None,
    }
    for index in range(offset, len(entries)):
        kind, item = entries[index]
        response[kind].append(item)
        response["next_offset"] = index + 1 if index + 1 < len(entries) else None
        # Always keep the first item of a page so paging makes progress.
        if index > offset and _compact_size(response) > max_bytes:
            response[kind].pop()
            response["next_offset"] = index
            break
    return response


CHANGES_SINCE_RECENT_MAX = 16


def _change_entry(kind: str, item: dict[str, object]) -> object:
    if kind == "observations":
        return {"id": item["id"], "handoff_id": item["handoff_id"], "requirement_refs": item["requirement_refs"]}
    if kind == "judgments":
        return {"id": item["id"], "requirement_ref": item["requirement_ref"], "outcome": item["outcome"]}
    return item["id"]


def changes_since(state: dict[str, object], base_revision: int, *, max_bytes: int = CHANGES_SINCE_MAX_BYTES,
                  recent_max: int = CHANGES_SINCE_RECENT_MAX) -> dict[str, object]:
    """Bounded review hint for what may have changed after ``base_revision``.

    This is deliberately NOT an exact delta. Continuity objects carry no
    per-item revision (adding one would make the state unreadable to Core
    0.5.0), so Core cannot say which of them were appended after the base.
    The hint is: ``revision_gap``; ``records`` whose stored revision is above
    the base; ``recent`` = the last k handoffs/observations/judgments with
    k = min(revision_gap, 16), which may include items older than the base;
    and ``evidence`` = the open-evidence summary (unincorporated observations
    and unresolved judgments: totals plus bounded items, paged by next_offset),
    which is what a caller must review before retrying. ``exact`` is always false.
    Replaced fields (Active Work, Pending Results, milestone, status) and
    sources are not tracked here.
    """
    if type(base_revision) is not int or base_revision < 0:
        raise ThalirisError(_errors.REVISION_DELTA_INVALID, "invalid since revision",
                            details={"expected": "a non-negative integer revision", "got": _preview(base_revision)})
    current = state["revision"]
    gap = max(current - base_revision, 0)
    k = min(gap, recent_max)
    continuity = state.get("evidence_continuity", {})
    recent = {kind: [_change_entry(kind, item) for item in continuity.get(kind, [])[-k:]] if k else []
              for kind in ("handoffs", "observations", "judgments")}
    result: dict[str, object] = {
        "base_revision": base_revision, "current_revision": current, "revision_gap": gap, "exact": False,
        "records": [item["id"] for item in state["records"] if type(item.get("revision")) is int and item["revision"] > base_revision],
        "recent": recent,
    }
    if base_revision > current:
        result["reason"] = "base revision is newer than the current revision"
    result["truncated"] = False
    # Bound the hint itself; open evidence is bounded and paged separately so
    # it is never silently dropped (evidence.next_offset pages the rest).
    while _compact_size(result) > max_bytes:
        lists = [values for values in (recent["observations"], recent["judgments"], recent["handoffs"], result["records"]) if values]
        if not lists:
            break
        max(lists, key=len).pop(0)
        result["truncated"] = True
    result["evidence"] = evidence_summary(state)
    return result


def revision_conflict(state: dict[str, object], base_revision: object) -> ThalirisError:
    """Build the structured strict-CAS refusal. Nothing is rebased or merged."""
    current = state["revision"]
    details: dict[str, object] = {"task_id": state["task_id"], "base_revision": base_revision if type(base_revision) is int else None,
                                  "current_revision": current, "changes_since": None}
    if type(base_revision) is int and base_revision >= 0:
        details["changes_since"] = changes_since(state, base_revision)
    return ThalirisError(
        _errors.TASK_REVISION_CONFLICT, "task revision conflict",
        recovery=f"review details.changes_since, then re-run with --base-revision {current} if the write still applies",
        details=details,
    )


def check_revision(state: dict[str, object], base_revision: object) -> None:
    """Strict compare-and-set: raise TASK_REVISION_CONFLICT unless exact."""
    if type(base_revision) is not int or state["revision"] != base_revision:
        raise revision_conflict(state, base_revision)


def _append_continuity(
    root: Path,
    actor: str,
    base_revision: int | None,
    input_file: str | None,
    kind: str,
    *,
    parsed_payload: dict[str, object] | None = None,
    compact_evidence: bool = False,
    override_reason: str | None = None,
) -> dict[str, object]:
    root = _repo_root(root)
    _bounded_label(actor, "continuity actor")
    if parsed_payload is not None:
        if kind != "observations" or input_file is not None or not isinstance(parsed_payload, dict):
            raise ValueError("inline continuity payload is only supported for observations")
        _check_json(parsed_payload)
        payload = dict(parsed_payload)
    else:
        payload = _read_input(input_file)
    if override_reason is not None:
        payload = _with_override_reason(payload, kind, override_reason)
    with _lock(root):
        state = _load_state(root, active=True)
        if base_revision is not None:
            check_revision(state, base_revision)
        observed = len(state.get("evidence_continuity", {}).get("observations", []))
        appended = _append_continuity_state(state, actor, payload, kind, root=root)
        _write_state(root, state)
    response = (task_write_response(state, ["evidence_continuity"], appended=appended) if compact_evidence
                else _task_ack(state, ["evidence_continuity"]))
    if kind == "judgments":
        mechanical = [item["id"] for item in state["evidence_continuity"]["observations"][observed:]]
        if mechanical:
            response["mechanical_observations"] = mechanical
    return response


def _append_continuity_state(state: dict[str, object], actor: str,
                             payload: dict[str, object], kind: str, *, root: Path | None = None) -> list[str]:
    """Apply the shared append contract to an adapter-owned locked transaction.

    The caller loads and writes state under the normal task lock. This pure
    mutation has no Host, authority, relevance or acceptance policy. It is
    all-or-nothing: on any validation error ``state`` is left unchanged.
    ``observations``/``judgments`` accept one object or a batch
    ``{"observations": [...]}`` / ``{"judgments": [...]}`` that commits in list
    order with one revision bump. Returns the appended continuity ids.

    Judgments pass the withholding gate (see ``_append_judgments``). ``root``
    lets the gate read the current tree and check files; without it a task
    with declared checks has an UNKNOWN tree, which never counts as fresh.
    """
    _bounded_label(actor, "continuity actor")
    _refuse_reserved_actor(actor)
    _check_json(payload)
    if not isinstance(payload, dict):
        raise ValueError("continuity payload must be a JSON object")
    if kind == "register":
        if not payload or set(payload) - {"requirements", "handoffs"}:
            raise ValueError("invalid evidence registration")
        additions = []
        for field, values in payload.items():
            if not isinstance(values, list) or not values:
                raise ValueError("registration requires append-only additions")
            additions.extend((field, None, value) for value in values)
        return _append_continuity_items(state, additions)
    if kind not in {"observations", "judgments"}:
        raise ValueError("invalid continuity kind")
    if set(payload) == {kind}:
        values = payload[kind]
        if not isinstance(values, list) or not 1 <= len(values) <= CONTINUITY_BATCH_MAX:
            raise ThalirisError(_errors.CONTINUITY_INVALID, f"invalid {kind} batch",
                                details={"collection": kind, "expected": f"a list of 1 to {CONTINUITY_BATCH_MAX} objects"})
    else:
        values = [payload]
    if kind == "judgments":
        return _append_judgments(state, actor, values, root)
    return _append_continuity_items(state, [(kind, actor, value) for value in values])


def append_observations(state: dict[str, object], entries: list[tuple[str, dict[str, object]]]) -> list[str]:
    """Append several observations with per-item producers in one revision.

    For adapter-owned locked transactions importing results from several
    handoffs: ``entries`` is ``[(producer, observation_payload), ...]``. Same
    per-item validation and all-or-nothing semantics as a single observe.
    """
    if not isinstance(entries, list) or not 1 <= len(entries) <= CONTINUITY_BATCH_MAX:
        raise ThalirisError(_errors.CONTINUITY_INVALID, "invalid observations batch",
                            details={"collection": "observations", "expected": f"a list of 1 to {CONTINUITY_BATCH_MAX} entries"})
    for actor, payload in entries:
        _bounded_label(actor, "continuity actor")
        _refuse_reserved_actor(actor)
        _check_json(payload)
    return _append_continuity_items(state, [("observations", actor, payload) for actor, payload in entries])


def _continuity_referents(state: dict[str, object], additions: list[tuple[str, str | None, object]]) -> list[tuple[str, str]]:
    """Evicted objects whose fields new continuity additions are checked against: the handoff of a new
    observation, the parent of a new handoff and the judgments a new judgment addresses."""
    if not _eviction_entries(state):
        return []
    index_map = _index_map(state)
    wanted: list[tuple[str, str]] = []
    for kind, _, value in additions:
        if not isinstance(value, dict):
            continue
        if kind == "observations" and isinstance(value.get("handoff_id"), str) and value["handoff_id"] in index_map["handoffs"]:
            wanted.append(("handoffs", value["handoff_id"]))
        elif kind == "handoffs" and isinstance(value.get("parent_handoff_id"), str) and value["parent_handoff_id"] in index_map["handoffs"]:
            wanted.append(("handoffs", value["parent_handoff_id"]))
        elif kind == "judgments" and isinstance(value.get("judgment_refs"), list):
            wanted.extend(("judgments", ref) for ref in value["judgment_refs"] if isinstance(ref, str) and ref in index_map["judgments"])
    return wanted


def _append_continuity_items(state: dict[str, object], additions: list[tuple[str, str | None, object]],
                             *, bump: bool = True, trusted: bool = False) -> list[str]:
    """Validate and commit continuity additions atomically in memory.

    ``trusted`` marks additions built by Core itself (gate overrides, mechanical
    observations, ingested typed claims); only those may carry Core-assigned fields.
    Evicted objects the additions are checked against are re-hydrated first (see
    ``_continuity_referents``); on any error ``state`` is left unchanged.
    """
    wanted = _continuity_referents(state, additions)
    if not wanted:
        return _append_continuity_hot(state, additions, bump=bump, trusted=trusted)
    snapshot = copy.deepcopy(state)
    try:
        _rehydrate_from_state(state, wanted)
        return _append_continuity_hot(state, additions, bump=bump, trusted=trusted)
    except BaseException:
        state.clear()
        state.update(snapshot)
        raise


def _append_continuity_hot(state: dict[str, object], additions: list[tuple[str, str | None, object]],
                           *, bump: bool = True, trusted: bool = False) -> list[str]:
    stamp = state["revision"] + 1
    evidence_refs = copy.deepcopy(state["evidence_refs"])
    data = copy.deepcopy(state["evidence_continuity"]) if "evidence_continuity" in state else {name: [] for name in _CONTINUITY_KINDS}
    known_sources = {item["id"] for item in evidence_refs} | _known_ids(state, "evidence_refs")
    appended: list[str] = []
    for batch_index, (kind, actor, value) in enumerate(additions):
        index = len(data[kind])
        if not isinstance(value, dict):
            raise _continuity_error(_errors.CONTINUITY_INVALID, "invalid continuity object", kind, index, value,
                                    expected="a JSON object", extra={"batch_index": batch_index})
        item = dict(value)
        if "revision" in item:
            raise _continuity_error(_errors.CONTINUITY_INVALID, "continuity objects carry no revision field", kind, index, item,
                                    field="revision", expected="omitted", extra={"batch_index": batch_index})
        assigned = sorted(_CORE_ASSIGNED_CONTINUITY_FIELDS[kind] & item.keys())
        if kind == "observations" and item.get("provenance") == MECHANISM_PRODUCER:
            assigned.append("provenance")
        if assigned and not trusted:
            raise _continuity_error(_errors.CONTINUITY_INVALID, "continuity field is assigned by Core", kind, index, item,
                                    field=assigned[0], expected="omitted", extra={"batch_index": batch_index, "fields": assigned})
        if kind in {"observations", "judgments"}:
            if kind == "observations" and "sources" in item:
                sources = item.pop("sources")
                if not isinstance(sources, list):
                    raise ValueError("invalid observation sources")
                for source in sources:
                    _evidence_ref(source, known_sources)
                    evidence_refs.append(source)
                    known_sources.add(source["id"])
            if {"task_id", "producer"} & set(item):
                raise ValueError("continuity producer and task are assigned by Core")
            item = {**item, "task_id": state["task_id"], "producer": actor}
        data[kind].append(item)
        appended.append(item.get("id"))
    candidate = {**state, "evidence_refs": evidence_refs, "evidence_continuity": data}
    schema = max(state["schema_version"], _feature_schema(candidate))
    _validate_continuity({**candidate, "schema_version": schema})
    state["schema_version"] = schema
    state["evidence_refs"] = evidence_refs
    state["evidence_continuity"] = data
    if bump:
        state["revision"] = stamp
    return appended


def task_evidence_register(root: Path, actor: str, base_revision: int, input_file: str | None,
                           *, compact_evidence: bool = False) -> dict[str, object]:
    return _append_continuity(root, actor, base_revision, input_file, "register", compact_evidence=compact_evidence)


def _register_evidence_handoff(state: dict[str, object], record: dict[str, object]) -> None:
    """Append to an already locked adapter transaction; caller writes the state.

    The caller bumps the revision once after this call.
    """
    _append_continuity_items(state, [("handoffs", None, record)], bump=False)


def task_observe(root: Path, actor: str, input_file: str | dict[str, object] | None,
                 *, compact_evidence: bool = False) -> dict[str, object]:
    if isinstance(input_file, dict):
        return _append_continuity(root, actor, None, None, "observations", parsed_payload=input_file, compact_evidence=compact_evidence)
    if input_file is not None and not isinstance(input_file, str):
        raise ValueError("invalid observation input")
    return _append_continuity(root, actor, None, input_file, "observations", compact_evidence=compact_evidence)


def task_judge(root: Path, actor: str, base_revision: int, input_file: str | None,
               *, compact_evidence: bool = False, override_reason: str | None = None) -> dict[str, object]:
    """Append one judgment or a batch. ``override_reason`` applies to every judgment that carries none."""
    return _append_continuity(root, actor, base_revision, input_file, "judgments", compact_evidence=compact_evidence,
                              override_reason=override_reason)


def task_show(root: Path) -> dict[str, object]:
    root = _repo_root(root)
    state = _load_state(root)
    return {"ok": True, "state": state, "task_surface_delta": _surface_delta(root, state["task_surface_baseline"])}


def task_get(root: Path, object_id: str) -> dict[str, object]:
    """Retrieve exactly one current-task ledger object by its task-wide ID."""
    root = _repo_root(root)
    identifier = _bounded_label(object_id, "task object id")
    state = _load_state(root)
    collections = (
        ("source", state["evidence_refs"]),
        ("record", state["records"]),
        ("artifact", state["artifact_refs"]),
        ("verification", state["verification_results"]),
        ("check", state.get("checks", [])),
    ) + tuple((kind, values) for kind, values in state.get("evidence_continuity", {}).items())
    matches = [(kind, item) for kind, values in collections for item in values if item.get("id") == identifier]
    if not matches and _eviction_entries(state):
        located = next(((name, bucket[identifier]) for name, bucket in _index_map(state).items() if identifier in bucket), None)
        if located is not None:
            # Evicted: the full object comes from its verified segment (a schema-10 stub inside it is
            # completed from its own version-1 segment).
            name, position = located
            kind = _OBJECT_TYPES.get(name, name)
            try:
                item, sha = _evicted_object(root, state, name, identifier, position)
                item = hydrate_archived(root, state, "verification_results" if name == "check_runs" else name, item)
            except ThalirisError as exc:
                if exc.details is not None:
                    exc.details["object_type"] = kind
                raise
            return {"ok": True, "task_id": state["task_id"], "revision": state["revision"], "object_type": kind,
                    "object": item, "archived": {"segment": sha, "evicted": True}}
    if len(matches) != 1:
        recovery = None
        if identifier == state["task_id"]:
            recovery = (
                "task-get requires an exact object ID, not the selected Task ID; "
                "use task-status for the selected task or task-show for diagnostics, "
                "then retry with a current object ID"
            )
        raise ThalirisError(_errors.TASK_OBJECT_NOT_FOUND, "task object not found",
                            recovery=recovery,
                            details={"id": identifier, "matches": len(matches)})
    kind, item = matches[0]
    response = {"ok": True, "task_id": state["task_id"], "revision": state["revision"], "object_type": kind, "object": item}
    if isinstance(item, dict) and "archived" in item:
        # The hot ledger holds a stub; the full object comes from its verified segment.
        collection = _TASK_GET_COLLECTIONS.get(kind, kind)
        try:
            response["object"] = hydrate_archived(root, state, collection, item)
        except ThalirisError as exc:
            if exc.details is not None:
                exc.details["object_type"] = kind
            raise
        response["archived"] = {"segment": item["archived"]}
    return response


_TASK_GET_COLLECTIONS = {"source": "evidence_refs", "record": "records", "verification": "verification_results"}


def artifact_get(root: Path, artifact_id: str) -> dict[str, object]:
    """Explicitly retrieve one bounded task Artifact body and its descriptor."""
    root = _repo_root(root)
    found = task_get(root, artifact_id)
    if found["object_type"] != "artifact":
        raise ValueError("task object is not an artifact")
    artifact = found["object"]
    try:
        target = _safe_without_final_symlink(root, str(artifact["path"]))
    except ValueError as exc:
        raise ValueError("artifact body not found") from exc
    if not target.is_file():
        raise ValueError("artifact body not found")
    if target.stat().st_size > EXPLICIT_DOCUMENT_MAX_BYTES:
        raise ValueError(f"artifact body exceeds {EXPLICIT_DOCUMENT_MAX_BYTES} bytes")
    body = target.read_bytes()
    if len(body) > EXPLICIT_DOCUMENT_MAX_BYTES:
        raise ValueError(f"artifact body exceeds {EXPLICIT_DOCUMENT_MAX_BYTES} bytes")
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("artifact body is not UTF-8 text") from exc
    return {**found, "body": text, "current_sha256": _file_digest(target), "freshness": _artifact_freshness(root, artifact)}


STATUS_VIEWS = ("full", "compact")
COMPACT_GOAL_PREVIEW_CHARS = 240


def _task_status_packet(state: dict[str, object], evidence_offset: int = 0, *, view: str = "full",
                        since_revision: int | None = None, root: Path | None = None,
                        contract: dict[str, object] | None = None) -> dict[str, object]:
    """Return current routing mechanics without replaying the durable ledger.

    ``view="full"`` is the historical packet (Evidence Continuity page).
    ``view="compact"`` keeps the routing header and replaces the page with the
    compact evidence summary. ``since_revision`` adds a bounded
    ``Changes Since`` delta to either view. Either view gains ``Verification``,
    ``Claims``, ``Usage`` and ``Advisories`` only when the task uses those
    features (see ``_feature_sections``); a task that uses none keeps its packet.
    """
    if view not in STATUS_VIEWS:
        raise ValueError("invalid status view")
    goal = str(state["goal"])
    artifact_ids = [str(item["id"]) for item in state["artifact_refs"]]
    # Counts include evicted objects (hot plus archive index totals).
    totals = _collection_totals(state)
    if view == "compact":
        continuity = state.get("evidence_continuity", {})
        packet: dict[str, object] = {
            "ok": True,
            "schema_version": state["schema_version"],
            "view": "compact",
            "Task": {
                "id": state["task_id"],
                "goal_preview": goal[:COMPACT_GOAL_PREVIEW_CHARS],
                "goal_truncated": len(goal) > COMPACT_GOAL_PREVIEW_CHARS,
                "status": state["status"],
                "revision": state["revision"],
                "milestone": state["current_milestone"],
            },
            "Active Work": state["active_work"],
            "Pending Results": state["pending_results"],
            "Counts": {
                "records": totals["records"],
                "sources": totals["evidence_refs"],
                "artifacts": len(state["artifact_refs"]),
                "verification_observations": totals["verification_results"],
                **{kind: totals.get(kind, len(continuity.get(kind, []))) for kind in _CONTINUITY_KINDS},
            },
            "Recent Artifact IDs": artifact_ids[-8:],
            "Evidence": evidence_summary(state, evidence_offset),
        }
    else:
        packet = {
            "ok": True,
            "schema_version": state["schema_version"],
            "Task": {
                "id": state["task_id"],
                "goal_preview": goal[:1024],
                "goal_truncated": len(goal) > 1024,
                "status": state["status"],
                "revision": state["revision"],
                "milestone": state["current_milestone"],
            },
            "Active Work": state["active_work"],
            "Pending Results": state["pending_results"],
            "Counts": {
                "records": totals["records"],
                "sources": totals["evidence_refs"],
                "artifacts": len(state["artifact_refs"]),
                "verification_observations": totals["verification_results"],
            },
            "Recent Artifact IDs": artifact_ids[-8:],
            "Active Artifact Count": len(_artifact_activity(state["artifact_refs"])),
            "Evidence Continuity": _continuity_status(state, evidence_offset),
        }
    packet.update(_feature_sections(root, state, contract))
    if since_revision is not None:
        packet["Changes Since"] = changes_since(state, since_revision)
    return packet


def task_status_packet(state: dict[str, object], evidence_offset: int = 0, *, view: str = "full",
                       since_revision: int | None = None, root: Path | None = None,
                       contract: dict[str, object] | None = None) -> dict[str, object]:
    """Public packet builder for adapters that already hold a loaded state.

    ``root`` lets the packet read the current tree and check files (without it
    declared checks show an UNKNOWN tree). ``contract`` is the authority
    contract; lane advisories are computed only for ``execution_mode: adaptive``.
    """
    return _task_status_packet(state, evidence_offset, view=view, since_revision=since_revision, root=root, contract=contract)


def task_status(root: Path, evidence_offset: int = 0, *, view: str = "full",
                since_revision: int | None = None, contract: dict[str, object] | None = None,
                record_tamper: bool = False) -> dict[str, object]:
    """Read the bounded status packet.

    The read never writes by default: changed check files are surfaced under
    ``Verification.tamper`` with ``recorded: false``. ``record_tamper=True``
    makes this call a locked write that appends the pending mechanical
    observations (one revision) before building the packet, so the caller must
    treat it as a ledger mutation (authority checkpoint included).
    """
    root = _repo_root(root)
    recorded: list[str] = []
    if record_tamper:
        with _lock(root):
            state = _load_state(root)
            if state["status"] == "ACTIVE" and state.get("checks"):
                recorded = record_check_tamper(root, state)
                if recorded:
                    _write_state(root, state)
    else:
        state = _load_state(root)
    packet = _task_status_packet(state, evidence_offset, view=view, since_revision=since_revision, root=root, contract=contract)
    if recorded:
        packet["Verification"]["tamper_recorded_now"] = recorded
    return packet


def task_artifact(root: Path, base_revision: int, artifact_id: str, path: str, summary: str, *, producer: str | None = None, registered_by: str = "unspecified", scope: str | None = None, evidence_refs: list[str] | None = None, supersedes: list[str] | None = None) -> dict[str, object]:
    root = _repo_root(root)
    if not isinstance(registered_by, str) or not registered_by:
        raise ValueError("invalid artifact registrar")
    draft: dict[str, object] = {"id": artifact_id, "path": path, "summary": summary}
    _artifact_ref(root, draft, require_target=True)
    with _lock(root):
        state = _load_state(root, active=True)
        check_revision(state, base_revision)
        if artifact_id in _task_object_ids(state):
            raise ValueError("task object id already exists")
        known_sources = _known_ids(state, "evidence_refs")
        refs = evidence_refs or []
        if any(ref not in known_sources for ref in refs):
            raise ValueError("artifact source reference is unknown")
        superseded = supersedes or []
        known_artifacts = {str(item["id"]) for item in state["artifact_refs"]}
        if any(item not in known_artifacts for item in superseded):
            raise ValueError("artifact supersession target is not registered")
        target = _safe_without_final_symlink(root, path)
        artifact: dict[str, object] = {
            "id": artifact_id,
            "path": path,
            "summary": summary,
            "producer": producer or "unspecified",
            "registered_by": registered_by,
            "source_refs": refs,
            "supersedes": superseded,
            "task_id": state["task_id"],
            "revision": base_revision + 1,
            "content_sha256": _file_digest(target),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        if scope is not None:
            artifact["scope"] = scope
        _artifact_ref(root, artifact, require_target=True)
        state["artifact_refs"].append(artifact)
        _artifact_activity(state["artifact_refs"])
        state["revision"] = base_revision + 1
        _write_state(root, state)
    return _task_ack(state, ["artifact_refs"])


def task_candidate_observation(root: Path) -> dict[str, object]:
    """Return candidate identity facts without deciding what testing is sufficient."""
    root = _repo_root(root)
    state = _load_state(root, active=True)
    delta = _surface_delta(root, state["task_surface_baseline"])
    candidate = {
        "task_id": state["task_id"],
        "revision": state["revision"],
        "head": _git_head(root),
        "surface": delta["after"],
    }
    return {
        "task_id": state["task_id"],
        "revision": state["revision"],
        "candidate_identity": hashlib.sha256(json.dumps(candidate, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest(),
        "paths": delta["paths"],
    }


def task_record_verification(root: Path, base_revision: int, result_id: str, kind: str, outcome: str, summary: str, source_refs: list[str] | None = None, *, observed_by: str, source_paths: list[str] | None = None) -> dict[str, object]:
    """Append a mechanical execution observation; it grants no close authority."""
    root = _repo_root(root)
    with _lock(root):
        state = _load_state(root, active=True)
        check_revision(state, base_revision)
        if result_id in _task_object_ids(state):
            raise ValueError("task object id already exists")
        if source_refs is not None and source_paths is not None:
            raise ValueError("provide source refs or source paths, not both")
        known_sources = _known_ids(state, "evidence_refs")
        refs = source_refs or []
        if not all(isinstance(ref, str) for ref in refs) or len(set(refs)) != len(refs) or any(ref not in known_sources for ref in refs):
            raise ValueError("verification source reference is unknown")
        paths = source_paths or []
        for path in paths:
            _valid_relative(root, path)
        observed_files = [_surface_identity(root, path, "OBSERVED") for path in sorted(set(paths))]
        candidate = task_candidate_observation(root)
        material = {
            "id": result_id,
            "kind": kind,
            "outcome": outcome,
            "summary": summary,
            "source_refs": refs,
            "observed_by": observed_by,
            "candidate_identity": candidate["candidate_identity"],
            "observed_files": observed_files,
        }
        observation = {
            **material,
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "observed_at_revision": base_revision,
            "result_hash": hashlib.sha256(json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest(),
        }
        _verification_result(observation)
        state["verification_results"].append(observation)
        state["revision"] = base_revision + 1
        _write_state(root, state)
    return _task_ack(state, ["verification_results"])


def task_close(root: Path, base_revision: int, *, expected_task_id: str | None = None,
               override_reason: str | None = None, actor: str | None = None) -> dict[str, object]:
    """Record mechanical closure through the close gate (see ``close_state``).

    The response always carries ``surfaced``: every judgment-only and partial
    requirement with its latest judgment. DONE is not product acceptance.
    """
    root = _repo_root(root)
    with _lock(root):
        state = _load_state(root, active=True)
        if expected_task_id is not None and state["task_id"] != expected_task_id:
            raise ThalirisError(_errors.TASK_IDENTITY_CONFLICT, "task revision conflict",
                                details={"expected_task_id": expected_task_id, "task_id": state["task_id"]})
        check_revision(state, base_revision)
        extras = close_state(root, state, override_reason=override_reason, actor=actor)
        _write_state(root, state)
    return {**_task_ack(state, ["status", *extras.pop("changed")]), **extras}


# --- Verification-first ledger (schema 9) ---------------------------------------------------------
#
# Mechanism may withhold; only a model may grant. Everything below may block,
# pause, cap and surface. Nothing below marks a requirement satisfied, dismisses
# evidence, picks relevance or closes a task. Each gate is a pure function of
# ledger facts plus data a model or human declared, and the Controller can
# override it with a recorded reason.

CHECK_ID_MAX = 40
CHECKS_MAX = 64
CHECK_BATCH_MAX = 16
CHECK_FILES_MAX = 64
CHECK_COMMAND_ARGS_MAX = 64
CHECK_COMMAND_MAX_BYTES = 8 * 1024
CHECK_TIMEOUT_DEFAULT_S = 600
CHECK_TIMEOUT_MAX_S = 7200
CHECK_OUTPUT_TAIL_CHARS = 4096
CHECK_RESULT_HISTORY = 4
CHECK_DECLARATION_HISTORY = 8
CHECK_OUTCOMES = ("PASS", "FAIL", "ERROR", "TIMEOUT")
CHECK_STATUSES = ("green", "red", "stale", "unrun")
TREE_UNKNOWN = "UNKNOWN"
OVERRIDE_REASON_MAX = 4096
SURFACED_MAX = 128
STATUS_CHECKS_MAX = 16
USAGE_FIELDS = ("model", "effort", "input_tokens", "output_tokens", "total_tokens", "cost_usd", "duration_ms",
                "tool_uses", "outcome")
USAGE_OUTCOMES = ("completed", "failed", "disposed", "unknown")
ADVISORY_DEFAULTS = {"max_files": 3, "max_changed_lines": 150, "controller_tool_output_tokens": 30_000}
ADVISORY_LINE_COUNT_MAX_PATHS = 64
ADVISORY_LINE_COUNT_MAX_FILE_BYTES = 1024 * 1024
LANE_COUNTER_MAX = 10 ** 12
_CHECK_FIELDS = {"id", "requirement_refs", "command", "cwd", "timeout_s", "files", "command_sha256", "files_digest",
                 "declared_by", "declared_at", "declared_at_revision", "declaration", "history"}
_CHECK_INPUT_FIELDS = {"id", "requirement_refs", "command", "cwd", "timeout_s", "files"}
_CHECK_HISTORY_FIELDS = {"declaration", "command_sha256", "files_digest", "declared_at_revision", "declared_by"}
_CHECK_RESULT_FIELDS = {"check_id", "run", "command_sha256", "files_digest", "files_changed_during_run", "exit_code",
                        "duration_ms", "output_tail", "output_tail_sha256", "output_bytes", "tree_identity",
                        "tree_identity_before"}
_CHECK_ID = re.compile(r"[A-Za-z0-9_-]{1,%d}" % CHECK_ID_MAX)
_HEX64 = re.compile(r"[0-9a-f]{64}")
_TREE_IDENTITY = re.compile(r"git:[0-9a-f]{40,64}")
_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
_GATE_ENTRY_FIELDS = {"id", "status", "reason", "outcome", "result_id", "requirement_ref"}


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _is_hex64(value: object) -> bool:
    return isinstance(value, str) and _HEX64.fullmatch(value) is not None


def _is_tree_identity(value: object) -> bool:
    return value == TREE_UNKNOWN or (isinstance(value, str) and _TREE_IDENTITY.fullmatch(value) is not None)


def _relative_spelling(value: object) -> bool:
    """Normalized POSIX repo-relative spelling outside private control data; no filesystem access."""
    if not isinstance(value, str) or not value or "\\" in value or value.startswith("/") or len(value) > 1024:
        return False
    parts = value.split("/")
    return not any(part in {"", ".", ".."} for part in parts) and parts[0] not in {".git", ".context"} and ":" not in parts[0]


def _command_sha256(command: list[str], cwd: str) -> str:
    return _canonical_sha256({"command": command, "cwd": cwd})


def _files_digest(files: list[dict[str, object]]) -> str:
    """One digest for a set of ``{"path", "sha256"}``; a non-file state marker stands in for a missing hash."""
    return _canonical_sha256(sorted([str(item["path"]), str(item["sha256"])] for item in files))


def _feature_schema(state: dict[str, object]) -> int:
    """The lowest schema version able to hold this state's content."""
    if _SCHEMA9_STATE_FIELDS & state.keys():
        return _VERIFICATION_SCHEMA_VERSION
    results = state.get("verification_results")
    if isinstance(results, list) and any(isinstance(item, dict) and "check_id" in item for item in results):
        return _VERIFICATION_SCHEMA_VERSION
    data = state.get("evidence_continuity")
    local = False
    if isinstance(data, dict):
        for kind, fields in _SCHEMA9_CONTINUITY_FIELDS.items():
            values = data.get(kind)
            for item in values if isinstance(values, list) else []:
                if not isinstance(item, dict):
                    continue
                if fields & item.keys() or (kind == "observations" and item.get("provenance") == MECHANISM_PRODUCER):
                    return _VERIFICATION_SCHEMA_VERSION
                local = local or (kind == "observations" and item.get("provenance") == "controller-local")
    return _CONTROLLER_LOCAL_SCHEMA_VERSION if local else _BASE_SCHEMA_VERSION


def _refuse_reserved_actor(actor: str) -> None:
    if actor == MECHANISM_PRODUCER:
        raise ThalirisError(_errors.CONTINUITY_PROVENANCE_CONFLICT, "continuity actor `mechanism` is reserved for Core",
                            recovery="use the actor label of the model or adapter that authored the write",
                            details={"actor": actor})


# --- stored-shape validators (return a problem description, or None) ---

def _check_run_fields(value: dict[str, object]) -> None:
    check_id = value.get("check_id")
    ok = (
        isinstance(check_id, str) and _CHECK_ID.fullmatch(check_id) is not None
        and value.get("kind") == "check" and value.get("outcome") in CHECK_OUTCOMES
        and type(value.get("run")) is int and value["run"] >= 1
        and _is_hex64(value.get("command_sha256")) and _is_hex64(value.get("files_digest"))
        and type(value.get("files_changed_during_run")) is bool
        and (value.get("exit_code") is None or type(value["exit_code"]) is int)
        and type(value.get("duration_ms")) is int and value["duration_ms"] >= 0
        and type(value.get("output_bytes")) is int and value["output_bytes"] >= 0
        and (value.get("output_tail") is None or (isinstance(value["output_tail"], str) and len(value["output_tail"]) <= CHECK_OUTPUT_TAIL_CHARS))
        and _is_hex64(value.get("output_tail_sha256"))
        and _is_tree_identity(value.get("tree_identity")) and _is_tree_identity(value.get("tree_identity_before"))
    )
    if not ok:
        raise ValueError("invalid check verification result")


def _gate_entries_problem(value: object) -> str | None:
    if not isinstance(value, list) or not 1 <= len(value) <= CHECKS_MAX:
        return f"1 to {CHECKS_MAX} overridden check entries"
    for item in value:
        if (not isinstance(item, dict) or set(item) - _GATE_ENTRY_FIELDS or not {"id", "status"} <= set(item)
                or not isinstance(item["id"], str) or _CHECK_ID.fullmatch(item["id"]) is None
                or item["status"] not in ("red", "stale", "unrun")
                or not all(isinstance(item[key], str) and 0 < len(item[key]) <= 64 for key in set(item) - {"id", "status"})):
            return "check entries {id, status: red|stale|unrun, reason?, outcome?, result_id?}"
    return None


def _override_problem(reason: object, checks: object) -> str | None:
    if not isinstance(reason, str) or not reason.strip() or len(reason) > OVERRIDE_REASON_MAX:
        return f"override_reason of 1 to {OVERRIDE_REASON_MAX} characters together with overridden_checks"
    return _gate_entries_problem(checks)


def _closure_problem(value: object) -> str | None:
    if not isinstance(value, dict) or value.get("gate") not in ("clear", "overridden") or not _is_tree_identity(value.get("tree_identity")):
        return "a closure record {gate: clear|overridden, tree_identity, ...}"
    allowed = {"gate", "tree_identity", "by"} | ({"override_reason", "overridden_checks"} if value["gate"] == "overridden" else set())
    if set(value) - allowed:
        return "no fields beyond gate, tree_identity, by and, when overridden, override_reason and overridden_checks"
    if "by" in value and (not isinstance(value["by"], str) or re.fullmatch(r"[A-Za-z0-9_.:-]{1,64}", value["by"]) is None):
        return "a bounded actor label in `by`"
    if value["gate"] == "overridden":
        return _override_problem(value.get("override_reason"), value.get("overridden_checks"))
    return None


def _mechanism_problem(value: object) -> str | None:
    if not isinstance(value, dict) or set(value) != {"kind", "check_id", "declaration", "files_digest", "files"}:
        return "a mechanism record {kind, check_id, declaration, files_digest, files}"
    files = value["files"]
    if (value["kind"] != "check-tamper" or not isinstance(value["check_id"], str) or _CHECK_ID.fullmatch(value["check_id"]) is None
            or type(value["declaration"]) is not int or value["declaration"] < 1 or not _is_hex64(value["files_digest"])
            or not isinstance(files, list) or not 1 <= len(files) <= CHECK_FILES_MAX):
        return "a check-tamper record for one declared check"
    for item in files:
        if (not isinstance(item, dict) or set(item) != {"path", "declared_sha256", "current"} or not _relative_spelling(item["path"])
                or not _is_hex64(item["declared_sha256"]) or not isinstance(item["current"], str) or not 0 < len(item["current"]) <= 64):
            return "changed files {path, declared_sha256, current}"
    return None


def _claim_record_problem(value: object) -> str | None:
    if (not isinstance(value, dict) or set(value) - {"requirement", "polarity", "basis", "evidence", "text_truncated", "normalized"}
            or not {"requirement", "polarity", "basis", "evidence"} <= set(value)):
        return "a claim record {requirement, polarity, basis, evidence, text_truncated?, normalized?}"
    if (value["polarity"] not in CLAIM_POLARITIES or value["basis"] not in CLAIM_BASES
            or not isinstance(value["requirement"], str) or len(value["requirement"]) > 64
            or not isinstance(value["evidence"], str) or not 0 < len(value["evidence"]) <= 300
            or value.get("text_truncated", True) is not True
            or not isinstance(value.get("normalized", []), list) or not all(isinstance(item, str) for item in value.get("normalized", []))):
        return "polarity supports|contradicts|unknown, basis check|read|inference and bounded requirement/evidence text"
    return None


def _claims_marker_problem(value: object) -> str | None:
    if not isinstance(value, dict) or value.get("status") not in ("present", "missing", "malformed"):
        return "a claims marker {status: present|missing|malformed, ...}"
    if value["status"] == "missing":
        return None if set(value) == {"status"} else "only `status` on a missing marker"
    if value["status"] == "malformed":
        if set(value) - {"status", "error"} or not isinstance(value.get("error", ""), str) or len(value.get("error", "")) > 200:
            return "only `status` and a bounded `error` on a malformed marker"
        return None
    if set(value) != {"status", "total", "truncated", "invalid", "duplicates", "supports", "observations"}:
        return "a present marker {status, total, truncated, invalid, duplicates, supports, observations}"
    supports, observations = value["supports"], value["observations"]
    if (any(type(value[key]) is not int or value[key] < 0 for key in ("total", "invalid", "duplicates")) or type(value["truncated"]) is not bool
            or not isinstance(supports, list) or len(supports) > CLAIMS_MAX or not isinstance(observations, list) or len(observations) > CLAIMS_MAX
            or not all(isinstance(item, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,64}", item) for item in observations)):
        return "bounded counts, at most %d supports and at most %d observation ids" % (CLAIMS_MAX, CLAIMS_MAX)
    for item in supports:
        if (not isinstance(item, dict) or set(item) != {"requirement", "evidence", "basis"} or item["basis"] not in CLAIM_BASES
                or not isinstance(item["requirement"], str) or not 0 < len(item["requirement"]) <= 64
                or not isinstance(item["evidence"], str) or not 0 < len(item["evidence"]) <= 300):
            return "supports {requirement, evidence, basis}"
    return None


def _usage_problem(value: object) -> str | None:
    if not isinstance(value, dict) or set(value) != set(USAGE_FIELDS):
        return "a usage record with exactly the fields " + ", ".join(USAGE_FIELDS) + " (unknown values are null)"
    for key in ("model", "effort"):
        if value[key] is not None and (not isinstance(value[key], str) or not value[key].strip() or len(value[key]) > 128):
            return f"`{key}` a non-empty string of at most 128 characters, or null"
    for key in ("input_tokens", "output_tokens", "total_tokens", "duration_ms", "tool_uses"):
        if value[key] is not None and (type(value[key]) is not int or not 0 <= value[key] <= LANE_COUNTER_MAX):
            return f"`{key}` a non-negative integer, or null"
    cost = value["cost_usd"]
    if cost is not None and (type(cost) not in (int, float) or not math.isfinite(cost) or not 0 <= cost <= 1e9):
        return "`cost_usd` a non-negative finite number, or null"
    if value["outcome"] is not None and value["outcome"] not in USAGE_OUTCOMES:
        return "`outcome` one of " + ", ".join(USAGE_OUTCOMES) + ", or null"
    return None


def _check_declaration_problem(item: object) -> str | None:
    if not isinstance(item, dict) or set(item) != _CHECK_FIELDS:
        return "a stored check declaration"
    command, files, refs, history = item["command"], item["files"], item["requirement_refs"], item["history"]
    if not isinstance(item["id"], str) or _CHECK_ID.fullmatch(item["id"]) is None:
        return "a check id matching [A-Za-z0-9_-]{1,%d}" % CHECK_ID_MAX
    if (not isinstance(refs, list) or not 1 <= len(refs) <= 64 or len(set(map(str, refs))) != len(refs)
            or not all(isinstance(ref, str) for ref in refs)):
        return "1 to 64 unique requirement refs"
    if (not isinstance(command, list) or not 1 <= len(command) <= CHECK_COMMAND_ARGS_MAX or not all(isinstance(arg, str) for arg in command)
            or not command[0].strip() or _compact_size(command) > CHECK_COMMAND_MAX_BYTES):
        return "a command argv list of 1 to %d strings" % CHECK_COMMAND_ARGS_MAX
    if item["cwd"] != "." and not _relative_spelling(item["cwd"]):
        return "cwd `.` or a normalized repo-relative directory"
    if type(item["timeout_s"]) is not int or not 1 <= item["timeout_s"] <= CHECK_TIMEOUT_MAX_S:
        return "timeout_s between 1 and %d" % CHECK_TIMEOUT_MAX_S
    if not isinstance(files, list) or len(files) > CHECK_FILES_MAX:
        return "at most %d check files" % CHECK_FILES_MAX
    for entry in files:
        if not isinstance(entry, dict) or set(entry) != {"path", "sha256"} or not _relative_spelling(entry["path"]) or not _is_hex64(entry["sha256"]):
            return "check files {path, sha256}"
    if len({entry["path"] for entry in files}) != len(files):
        return "unique check file paths"
    if item["command_sha256"] != _command_sha256(command, item["cwd"]) or item["files_digest"] != _files_digest(files):
        return "command_sha256 and files_digest that match the declaration"
    if (not isinstance(item["declared_by"], str) or re.fullmatch(r"[A-Za-z0-9_.:-]{1,64}", item["declared_by"]) is None
            or not isinstance(item["declared_at"], str) or type(item["declared_at_revision"]) is not int
            or type(item["declaration"]) is not int or item["declaration"] < 1):
        return "declaration provenance"
    if not isinstance(history, list) or len(history) > CHECK_DECLARATION_HISTORY or not all(
            isinstance(entry, dict) and set(entry) == _CHECK_HISTORY_FIELDS for entry in history):
        return "at most %d prior declaration summaries" % CHECK_DECLARATION_HISTORY
    return None


def _validate_checks(root: Path, state: dict[str, object]) -> set[str]:
    """Shape-check the declared checks; returns their ids for the task-wide identity check."""
    if "checks" not in state:
        return set()
    checks = state["checks"]
    if isinstance(checks, list) and len(checks) > CHECKS_MAX:
        raise _capacity_error("checks", CHECKS_MAX, len(checks))
    if not isinstance(checks, list) or not checks:
        raise ValueError("invalid declared checks")
    ids: set[str] = set()
    for item in checks:
        problem = _check_declaration_problem(item)
        if problem:
            raise ThalirisError(_errors.CHECK_INVALID, "invalid check declaration", details={"expected": problem})
        if item["id"] in ids:
            raise ValueError("duplicate check id")
        ids.add(str(item["id"]))
    return ids


def _validate_verification_state(state: dict[str, object]) -> None:
    """Cross-object rules for schema-9 content; runs after continuity validation."""
    results = state["verification_results"]
    uses = bool(_SCHEMA9_STATE_FIELDS & state.keys()) or any("check_id" in item for item in results)
    if uses and state["schema_version"] < _VERIFICATION_SCHEMA_VERSION:
        raise ThalirisError(_errors.TASK_STATE_INVALID, "verification-first records require task schema 9",
                            recovery="preserve the state and use a compatible reader")
    checks = state.get("checks", [])
    requirements = {item["id"] for item in state.get("evidence_continuity", {}).get("requirements", [])}
    for check in checks:
        unknown = [ref for ref in check["requirement_refs"] if ref not in requirements]
        if unknown:
            raise ThalirisError(_errors.CHECK_INVALID, "check requirement reference is unknown",
                                details={"id": check["id"], "unknown_refs": unknown[:8]})
    check_ids = {check["id"] for check in checks}
    if any("check_id" in item and item["check_id"] not in check_ids for item in results):
        raise ValueError("verification result names an undeclared check")
    if "closure" in state:
        problem = _closure_problem(state["closure"])
        if problem or state["status"] != "DONE" or not (checks or state["closure"].get("gate") == "overridden"):
            raise ThalirisError(_errors.TASK_STATE_INVALID, "invalid closure record",
                                details={"expected": problem or "a closure record only on a DONE task with declared checks or an override"})
    elif checks and state["status"] == "DONE":
        raise ThalirisError(_errors.TASK_STATE_INVALID, "a task with declared checks closes only through the close gate",
                            recovery="close with task-close (core.task_close or core.close_state); the state is unchanged",
                            details={"checks": len(checks)})


# --- tree identity and check files ---

def tree_identity(root: Path) -> str:
    """A deterministic content identity of the working tree: ``git:<tree id>`` or ``UNKNOWN``.

    Covers tracked plus untracked non-ignored files and excludes ``.context/``.
    It is computed in a scratch index and a scratch object directory, so neither
    the user's index nor the repository's object store is written. Any failure,
    and every non-Git directory, is ``UNKNOWN``, which never counts as fresh.
    """
    try:
        if _git_root(root) is None:
            return TREE_UNKNOWN
    except (ValueError, OSError):
        return TREE_UNKNOWN
    options = ["-c", "core.splitIndex=false", "-c", "core.fsmonitor=false", "-c", "core.untrackedCache=false",
               "-c", "advice.addEmbeddedRepo=false"]

    def git(arguments: list[str], env: dict[str, str] | None = None) -> str | None:
        try:
            proc = subprocess.run(["git", *options, *arguments], cwd=root, env=env, capture_output=True, text=True,
                                  encoding="utf-8", errors="surrogateescape", check=False, stdin=subprocess.DEVNULL,
                                  timeout=GIT_TIMEOUT_SECONDS)
        except (OSError, subprocess.SubprocessError):
            return None
        return proc.stdout if proc.returncode == 0 else None

    located = git(["rev-parse", "--git-path", "index", "--git-path", "objects"])
    paths = located.splitlines() if located else []
    if len(paths) != 2 or not all(paths):
        return TREE_UNKNOWN
    real_index, real_objects = ((root / item).resolve() for item in paths)
    try:
        scratch = tempfile.mkdtemp(prefix="thaliris-tree-")
    except OSError:
        return TREE_UNKNOWN
    try:
        index = Path(scratch) / "index"
        objects = Path(scratch) / "objects"
        objects.mkdir()
        if real_index.is_file():
            shutil.copyfile(real_index, index)
        alternates = [str(real_objects)] + [item for item in os.environ.get("GIT_ALTERNATE_OBJECT_DIRECTORIES", "").split(os.pathsep) if item]
        if any(os.pathsep in item or item.startswith('"') for item in alternates[:1]):
            return TREE_UNKNOWN
        env = {**os.environ, "GIT_INDEX_FILE": str(index), "GIT_OBJECT_DIRECTORY": str(objects),
               "GIT_ALTERNATE_OBJECT_DIRECTORIES": os.pathsep.join(alternates)}
        if git(["add", "-A", "--", ".", ":(exclude).context"], env) is None:
            return TREE_UNKNOWN
        if git(["rm", "-r", "-q", "--cached", "--ignore-unmatch", "--", ".context"], env) is None:
            return TREE_UNKNOWN
        tree = (git(["write-tree", "--missing-ok"], env) or "").strip().lower()
    except OSError:
        return TREE_UNKNOWN
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    identity = "git:" + tree
    return identity if _TREE_IDENTITY.fullmatch(identity) else TREE_UNKNOWN


def _check_files_now(root: Path, files: list[dict[str, object]]) -> tuple[str, list[dict[str, object]], list[dict[str, object]]]:
    """Current state of declared check files: (digest, [{path, sha256-or-state}], surface identities)."""
    current: list[dict[str, object]] = []
    identities: list[dict[str, object]] = []
    for entry in files:
        path = str(entry["path"])
        try:
            _valid_relative(root, path)
            identity = _surface_identity(root, path, "OBSERVED")
        except (ValueError, OSError):
            identity = {"path": path, "state": "UNSAFE", "identity": None, "mode": None, "git_status": "OBSERVED"}
        identities.append(identity)
        current.append({"path": path, "sha256": identity["identity"] if identity["state"] == "FILE" else identity["state"]})
    return _files_digest(current), current, identities


def _latest_check_results(state: dict[str, object]) -> dict[str, list[dict[str, object]]]:
    """Check-run results per check id, oldest first."""
    grouped: dict[str, list[dict[str, object]]] = {}
    for item in state["verification_results"]:
        if "check_id" in item:
            grouped.setdefault(str(item["check_id"]), []).append(item)
    return grouped


def verification_view(root: Path | None, state: dict[str, object], *, tree: str | None = None) -> dict[str, object]:
    """The current standing of every declared check; reads only, never writes.

    A check is ``unrun`` (no result), ``green`` (fresh PASS), ``red`` (fresh
    FAIL/ERROR/TIMEOUT) or ``stale`` with a ``reason``: ``check_files_changed``
    (a declared file no longer matches its declared hash), ``declaration_changed``
    (the latest result ran another command or other check-file content, or the
    check files changed during the run), ``tree_unknown`` or ``tree_changed``.
    A result is fresh only when its tree identity equals the current one and the
    check files match the declared hashes. The tree identity is computed at most
    once and only when a result could still be fresh; ``tree`` supplies a value
    the caller has just computed. Without ``root`` nothing can be read, so the
    tree is UNKNOWN.
    """
    results = _latest_check_results(state)
    known: dict[str, str | None] = {"tree": tree}

    def current_tree() -> str:
        if known["tree"] is None:
            known["tree"] = tree_identity(root) if root is not None else TREE_UNKNOWN
        return str(known["tree"])

    entries: list[dict[str, object]] = []
    for declaration in state.get("checks", []):
        entry: dict[str, object] = {"id": declaration["id"], "requirement_refs": declaration["requirement_refs"],
                                    "declaration": declaration["declaration"], "tampered": False}
        if root is not None:
            digest, current, _ = _check_files_now(root, declaration["files"])
            if digest != declaration["files_digest"]:
                declared = {item["path"]: item["sha256"] for item in declaration["files"]}
                entry["tampered"] = True
                entry["files_digest"] = digest
                entry["changed_files"] = [{"path": item["path"], "declared_sha256": declared[item["path"]], "current": item["sha256"]}
                                          for item in current if declared[item["path"]] != item["sha256"]]
        runs = results.get(str(declaration["id"]), [])
        latest = runs[-1] if runs else None
        if latest is not None:
            entry.update(result_id=latest["id"], outcome=latest["outcome"], run=latest["run"])
        if latest is None:
            entry["status"] = "unrun"
        elif entry["tampered"]:
            entry.update(status="stale", reason="check_files_changed")
        elif (latest["command_sha256"] != declaration["command_sha256"] or latest["files_digest"] != declaration["files_digest"]
              or latest["files_changed_during_run"]):
            entry.update(status="stale", reason="declaration_changed")
        elif latest["tree_identity"] == TREE_UNKNOWN or current_tree() == TREE_UNKNOWN:
            entry.update(status="stale", reason="tree_unknown")
        elif latest["tree_identity"] != current_tree():
            entry.update(status="stale", reason="tree_changed")
        else:
            entry["status"] = "green" if latest["outcome"] == "PASS" else "red"
        entries.append(entry)
    return {"tree_identity": known["tree"], "checks": entries}


def _gate_entry(entry: dict[str, object]) -> dict[str, object]:
    return {key: entry[key] for key in ("id", "status", "reason", "outcome", "result_id") if key in entry}


def _withheld(operation: str, view: dict[str, object], details: dict[str, object]) -> ThalirisError:
    return ThalirisError(
        _errors.VERIFICATION_WITHHELD,
        f"verification withheld: {operation} needs every declared check green on the current tree",
        recovery=("run task-verify for each listed check on the current tree and retry; a check whose declared files "
                  "changed needs task-check --supersede first; or retry with an override reason, which is recorded"),
        details={"operation": operation, "tree_identity": view["tree_identity"] or "NOT_COMPUTED", **details},
    )


def _unchecked_compiled(state: dict[str, object]) -> set[str]:
    """Ids of ``compiled`` requirements that no declared check covers."""
    covered = {ref for check in state.get("checks", []) for ref in check["requirement_refs"]}
    return {str(item["id"]) for item in state.get("evidence_continuity", {}).get("requirements", [])
            if item.get("kind") == "compiled" and item["id"] not in covered}


def _no_check_entry(requirement: str) -> dict[str, object]:
    return {"id": "no-check", "status": "unrun", "reason": "no-declared-check", "requirement_ref": requirement}


def _override_text(reason: object) -> str:
    if not isinstance(reason, str) or not reason.strip() or len(reason) > OVERRIDE_REASON_MAX:
        raise ThalirisError(_errors.VERIFICATION_OVERRIDE_INVALID, "invalid override reason",
                            recovery="supply the reason as non-empty text; nothing was recorded",
                            details={"expected": f"1 to {OVERRIDE_REASON_MAX} characters"})
    return reason


def _with_override_reason(payload: dict[str, object], kind: str, reason: str) -> dict[str, object]:
    """Give every judgment that carries no override reason the operation-level one."""
    if kind != "judgments":
        raise ValueError("an override reason applies only to judgments")
    _override_text(reason)
    if set(payload) == {"judgments"} and isinstance(payload["judgments"], list):
        return {"judgments": [{**item, "override_reason": reason} if isinstance(item, dict) and "override_reason" not in item else item
                              for item in payload["judgments"]]}
    return payload if "override_reason" in payload else {**payload, "override_reason": reason}


def _mechanical_tamper(state: dict[str, object], view: dict[str, object]) -> list[dict[str, object]]:
    """Observations still owed for changed check files: one per (check, new files digest)."""
    recorded = {(item["mechanism"]["check_id"], item["mechanism"]["files_digest"])
                for item in state.get("evidence_continuity", {}).get("observations", []) if "mechanism" in item}
    if _eviction_entries(state):
        recorded |= _archive_totals(state).mechanism.keys()
    taken = _task_object_ids(state)
    pending: list[dict[str, object]] = []
    for entry in view["checks"]:
        if not entry["tampered"] or (entry["id"], entry["files_digest"]) in recorded:
            continue
        identifier = f"{entry['id']}.tamper.{str(entry['files_digest'])[:10]}"
        while identifier in taken:
            identifier += "x"
        taken.add(identifier)
        changed = entry["changed_files"]
        sources = [{"id": f"{identifier}.s{index}", "kind": "check-file", "locator": item["path"],
                    "summary": f"declared sha256 {item['declared_sha256']}; current {item['current']}"}
                   for index, item in enumerate(changed[:8], 1)]
        names = ", ".join(str(item["path"]) for item in changed[:4]) + (f" and {len(changed) - 4} more" if len(changed) > 4 else "")
        pending.append({
            "id": identifier, "candidate": MECHANISM_PRODUCER, "handoff_id": None, "provenance": MECHANISM_PRODUCER,
            "requirement_refs": list(entry["requirement_refs"]), "source_refs": [source["id"] for source in sources], "sources": sources,
            "text": (f"Declared check {entry['id']} no longer matches its declaration {entry['declaration']}: {names} changed after "
                     "the Controller declared it. Its results are not fresh until the Controller supersedes the check with the "
                     "current content or the declared content is restored."),
            "mechanism": {"kind": "check-tamper", "check_id": entry["id"], "declaration": entry["declaration"],
                          "files_digest": entry["files_digest"], "files": changed},
        })
    return pending


def record_check_tamper(root: Path, state: dict[str, object], *, view: dict[str, object] | None = None,
                        bump: bool = True) -> list[str]:
    """Append the mechanical observations owed for changed check files to a locked state.

    One adverse observation per (check, new files digest), producer
    ``mechanism``, linked to the check's requirements; it stays open until a
    judgment cites it. Returns the appended ids (empty when nothing is owed, and
    then the state is untouched). The caller writes the state.
    """
    if not state.get("checks"):
        return []
    pending = _mechanical_tamper(state, view if view is not None else verification_view(root, state))
    if not pending:
        return []
    return _append_continuity_items(state, [("observations", MECHANISM_PRODUCER, item) for item in pending], bump=bump, trusted=True)


def _append_judgments(state: dict[str, object], actor: str, values: list[object], root: Path | None) -> list[str]:
    """Append judgments through the withholding gate.

    A ``satisfied`` judgment on a requirement with at least one declared check
    is refused as ``VERIFICATION_WITHHELD`` while any of those checks is red,
    unrun or stale, unless the judgment carries ``override_reason``. The reason
    is stored with the checks it overrode; a reason that overrides nothing is not
    stored. The gate never grants: a green check adds no judgment. Check files
    that changed are recorded as mechanical observations in the same revision.
    """
    prepared: list[object] = []
    mechanical: list[dict[str, object]] = []
    view = verification_view(root, state) if state.get("checks") else None
    unchecked = _unchecked_compiled(state)
    withheld: list[dict[str, object]] = []
    for index, value in enumerate(values):
        if not isinstance(value, dict):
            prepared.append(value)
            continue
        item = dict(value)
        if "overridden_checks" in item:
            raise _continuity_error(_errors.CONTINUITY_INVALID, "continuity field is assigned by Core", "judgments", index, item,
                                    field="overridden_checks", expected="omitted", extra={"batch_index": index})
        reason = item.pop("override_reason", None)
        blocking = ([_gate_entry(entry) for entry in view["checks"]
                     if item.get("requirement_ref") in entry["requirement_refs"] and entry["status"] != "green"]
                    if view is not None and item.get("outcome") == "satisfied" else [])
        if item.get("outcome") == "satisfied" and item.get("requirement_ref") in unchecked:
            blocking.append(_no_check_entry(str(item["requirement_ref"])))
        if blocking and reason is None:
            withheld.append({"batch_index": index, "judgment_id": item.get("id") if isinstance(item.get("id"), str) else None,
                             "requirement_ref": item.get("requirement_ref"), "checks": blocking[:STATUS_CHECKS_MAX],
                             "checks_total": len(blocking)})
        elif blocking:
            item["override_reason"] = _override_text(reason)
            item["overridden_checks"] = blocking
        prepared.append(item)
    if withheld:
        raise _withheld("judge", view or {"tree_identity": None}, {"withheld": withheld[:STATUS_CHECKS_MAX], "withheld_total": len(withheld)})
    if view is not None:
        mechanical = _mechanical_tamper(state, view)
    additions = [("observations", MECHANISM_PRODUCER, item) for item in mechanical] + [("judgments", actor, item) for item in prepared]
    return _append_continuity_items(state, additions, trusted=True)[len(mechanical):]


# --- declared checks ---

def _check_error(message: str, index: int, value: object, field: str | None, expected: str, **extra: object) -> ThalirisError:
    identifier = value.get("id") if isinstance(value, dict) and isinstance(value.get("id"), str) else None
    return ThalirisError(_errors.CHECK_INVALID, f"invalid check declaration: {message}",
                         recovery="correct the named field and retry; nothing was declared",
                         details={"index": index, "id": identifier, "field": field, "expected": expected, **extra})


def _new_check(root: Path, value: object, requirements: set[str], actor: str, revision: int, index: int) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) - _CHECK_INPUT_FIELDS or not {"id", "requirement_refs", "command"} <= set(value):
        present = set(value) if isinstance(value, dict) else set()
        raise _check_error("unexpected shape", index, value, None,
                           "an object {id, requirement_refs, command, cwd?, timeout_s?, files?}",
                           missing_fields=sorted({"id", "requirement_refs", "command"} - present),
                           unexpected_fields=sorted(present - _CHECK_INPUT_FIELDS))
    identifier = value["id"]
    if not isinstance(identifier, str) or _CHECK_ID.fullmatch(identifier) is None:
        raise _check_error("id", index, value, "id", "1-%d characters matching [A-Za-z0-9_-]+" % CHECK_ID_MAX)
    refs = value["requirement_refs"]
    if not isinstance(refs, list) or not 1 <= len(refs) <= 64 or not all(isinstance(ref, str) for ref in refs) or len(set(refs)) != len(refs):
        raise _check_error("requirement_refs", index, value, "requirement_refs", "1 to 64 unique registered requirement ids")
    unknown = [ref for ref in refs if ref not in requirements]
    if unknown:
        raise _check_error("requirement_refs", index, value, "requirement_refs", "requirement ids registered in this task",
                           unknown_refs=unknown[:8])
    command = value["command"]
    if (not isinstance(command, list) or not 1 <= len(command) <= CHECK_COMMAND_ARGS_MAX or not all(isinstance(arg, str) for arg in command)
            or not command[0].strip() or _compact_size(command) > CHECK_COMMAND_MAX_BYTES):
        raise _check_error("command", index, value, "command",
                           "an argv list of 1 to %d strings (no shell), at most %d bytes" % (CHECK_COMMAND_ARGS_MAX, CHECK_COMMAND_MAX_BYTES))
    cwd = value.get("cwd", ".")
    if cwd != ".":
        try:
            if not _relative_spelling(cwd) or not _safe_without_final_symlink(root, cwd).is_dir():
                raise ValueError("not a directory")
        except ValueError as exc:
            raise _check_error("cwd", index, value, "cwd", "`.` or an existing repo-relative directory outside .git and .context") from exc
    timeout = value.get("timeout_s", CHECK_TIMEOUT_DEFAULT_S)
    if type(timeout) is not int or not 1 <= timeout <= CHECK_TIMEOUT_MAX_S:
        raise _check_error("timeout_s", index, value, "timeout_s", "an integer from 1 to %d" % CHECK_TIMEOUT_MAX_S)
    paths = value.get("files", [])
    if not isinstance(paths, list) or len(paths) > CHECK_FILES_MAX or not all(isinstance(path, str) for path in paths) or len(set(paths)) != len(paths):
        raise _check_error("files", index, value, "files", "at most %d unique repo-relative file paths" % CHECK_FILES_MAX)
    files: list[dict[str, object]] = []
    for path in paths:
        try:
            if not _relative_spelling(path):
                raise ValueError("spelling")
            target = _safe_without_final_symlink(root, path)
            if not target.is_file():
                raise ValueError("not a file")
        except ValueError as exc:
            raise _check_error("files", index, value, "files",
                               "existing regular files, repo-relative, outside .git and .context, not symlinks", path=_preview(path)) from exc
        files.append({"path": path, "sha256": _file_digest(target)})
    return {
        "id": identifier, "requirement_refs": list(refs), "command": list(command), "cwd": cwd, "timeout_s": timeout, "files": files,
        "command_sha256": _command_sha256(command, cwd), "files_digest": _files_digest(files),
        "declared_by": actor, "declared_at": datetime.now(timezone.utc).isoformat(), "declared_at_revision": revision,
        "declaration": 1, "history": [],
    }


def declare_checks(root: Path, state: dict[str, object], actor: str, payload: dict[str, object], *, supersede: bool = False) -> list[str]:
    """Declare or supersede checks in an adapter-owned locked transaction.

    ``payload`` is one check ``{id, requirement_refs, command, cwd?, timeout_s?,
    files?}`` or ``{"checks": [...]}`` (all-or-nothing, one revision). Core
    records the content hash of every declared file now. Declaring an existing
    id is refused unless ``supersede`` is true; superseding keeps the id, bumps
    its ``declaration`` and is how the Controller accepts changed check
    content. A supersede that changes nothing is a no-op. Returns the ids
    written; the caller writes the state. Who may declare is the adapter's rule.
    """
    _bounded_label(actor, "check actor")
    _refuse_reserved_actor(actor)
    _check_json(payload)
    if not isinstance(payload, dict):
        raise ValueError("check payload must be a JSON object")
    values = payload["checks"] if set(payload) == {"checks"} else [payload]
    if not isinstance(values, list) or not 1 <= len(values) <= CHECK_BATCH_MAX:
        raise ThalirisError(_errors.CHECK_INVALID, "invalid checks batch",
                            details={"expected": f"a list of 1 to {CHECK_BATCH_MAX} check objects"})
    requirements = {str(item["id"]) for item in state.get("evidence_continuity", {}).get("requirements", [])}
    checks = copy.deepcopy(state.get("checks", []))
    positions = {str(item["id"]): position for position, item in enumerate(checks)}
    foreign = _task_object_ids(state) - set(positions)
    revision = state["revision"] + 1
    written: list[str] = []
    seen: set[str] = set()
    for index, value in enumerate(values):
        declaration = _new_check(root, value, requirements, actor, revision, index)
        identifier = str(declaration["id"])
        if identifier in seen or identifier in foreign:
            raise ThalirisError(_errors.TASK_OBJECT_ID_COLLISION, "task object id collision", details={"ids": [identifier]})
        seen.add(identifier)
        if identifier in positions:
            prior = checks[positions[identifier]]
            if not supersede:
                raise ThalirisError(
                    _errors.CHECK_ALREADY_DECLARED, "check is already declared",
                    recovery="re-declare with supersede (task-check --supersede) to accept the current content; nothing was declared",
                    details={"id": identifier, "declaration": prior["declaration"],
                             "content_changed": prior["files_digest"] != declaration["files_digest"],
                             "command_changed": prior["command_sha256"] != declaration["command_sha256"]})
            if all(prior[key] == declaration[key] for key in ("requirement_refs", "command_sha256", "files_digest", "timeout_s")):
                continue
            declaration["declaration"] = prior["declaration"] + 1
            declaration["history"] = (prior["history"] + [{key: prior[key] for key in _CHECK_HISTORY_FIELDS}])[-CHECK_DECLARATION_HISTORY:]
            checks[positions[identifier]] = declaration
        else:
            positions[identifier] = len(checks)
            checks.append(declaration)
        written.append(identifier)
    if len(checks) > CHECKS_MAX:
        raise _capacity_error("checks", CHECKS_MAX, len(checks))
    if written:
        state["checks"] = checks
        state["schema_version"] = max(state["schema_version"], _VERIFICATION_SCHEMA_VERSION)
        state["revision"] = revision
    return written


def task_check(root: Path, actor: str, base_revision: int, input_file: str | dict[str, object] | None,
               *, supersede: bool = False) -> dict[str, object]:
    """Declare or supersede checks under strict revision CAS (see ``declare_checks``)."""
    root = _repo_root(root)
    payload = dict(input_file) if isinstance(input_file, dict) else _read_input(input_file)
    with _lock(root):
        state = _load_state(root, active=True)
        check_revision(state, base_revision)
        written = declare_checks(root, state, actor, payload, supersede=supersede)
        if written:
            _write_state(root, state)
    declared = {str(item["id"]): item for item in state.get("checks", [])}
    return {**_task_ack(state, ["checks"] if written else []), "declared": written,
            "checks": [{"id": identifier, "declaration": declared[identifier]["declaration"],
                        "requirement_refs": declared[identifier]["requirement_refs"],
                        "files": len(declared[identifier]["files"]), "files_digest": declared[identifier]["files_digest"]}
                       for identifier in written]}


def _declared_check(state: dict[str, object], check_id: object) -> dict[str, object]:
    for item in state.get("checks", []):
        if item["id"] == check_id:
            return item
    raise ThalirisError(_errors.CHECK_NOT_FOUND, "check is not declared",
                        recovery="use a check id that task-status lists; only the Controller declares checks",
                        details={"id": _preview(check_id), "declared": [item["id"] for item in state.get("checks", [])][:STATUS_CHECKS_MAX]})


# --- verify ---

def _kill_process_tree(process: subprocess.Popen) -> None:
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)], capture_output=True, check=False,
                           stdin=subprocess.DEVNULL, timeout=30)
        else:
            os.killpg(process.pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        process.kill()
    except OSError:
        pass
    try:
        process.wait(timeout=30)
    except (OSError, subprocess.SubprocessError):
        pass


def _output_tail(stream) -> tuple[str, int]:
    """The last ``CHECK_OUTPUT_TAIL_CHARS`` characters of captured output as ledger-safe text, and its byte size."""
    stream.flush()
    size = stream.seek(0, os.SEEK_END)
    stream.seek(max(size - 4 * CHECK_OUTPUT_TAIL_CHARS, 0))
    text = stream.read().decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
    text = _ANSI.sub("", text)
    text = "".join(char if char in "\n\t" or (ord(char) >= 32 and ord(char) != 0x7F) else " " for char in text)
    return text[-CHECK_OUTPUT_TAIL_CHARS:], size


def _run_declared_check(root: Path, declaration: dict[str, object]) -> dict[str, object]:
    """Run one declared command (argv, no shell) outside the task lock and collect mechanical facts."""
    cwd = root if declaration["cwd"] == "." else _safe(root, str(declaration["cwd"]))
    files_before, _, _ = _check_files_now(root, declaration["files"])
    tree_before = tree_identity(root)
    spawn: dict[str, object] = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt"
                                else {"start_new_session": True})
    outcome, exit_code, failure = "ERROR", None, None
    started = time.monotonic()
    with tempfile.TemporaryFile() as sink:
        try:
            process = subprocess.Popen(list(declaration["command"]), cwd=cwd, stdin=subprocess.DEVNULL, stdout=sink,
                                       stderr=subprocess.STDOUT, shell=False, **spawn)
        except (OSError, ValueError) as exc:
            failure = f"could not start the declared command: {type(exc).__name__}: {exc}"
        else:
            try:
                exit_code = process.wait(timeout=int(declaration["timeout_s"]))
                outcome = "PASS" if exit_code == 0 else "FAIL"
            except subprocess.TimeoutExpired:
                _kill_process_tree(process)
                outcome, exit_code = "TIMEOUT", None
        duration_ms = int((time.monotonic() - started) * 1000)
        tail, size = _output_tail(sink)
    if failure is not None:
        tail = "".join(char if char in "\n\t" or ord(char) >= 32 else " " for char in failure)[-CHECK_OUTPUT_TAIL_CHARS:]
    files_after, _, identities = _check_files_now(root, declaration["files"])
    return {
        "check_id": declaration["id"], "command_sha256": declaration["command_sha256"], "outcome": outcome, "exit_code": exit_code,
        "duration_ms": duration_ms, "output_tail": tail, "output_bytes": size, "tree_identity_before": tree_before,
        "tree_identity": tree_identity(root), "files_digest": files_after, "files_changed_during_run": files_before != files_after,
        "observed_files": identities,
    }


def record_check_run(root: Path, state: dict[str, object], actor: str, run: dict[str, object]) -> tuple[dict[str, object], list[str]]:
    """Append one check-run result (and any owed tamper observations) to a locked state.

    Keeps the latest ``CHECK_RESULT_HISTORY`` results per check; only the latest
    keeps its output tail (earlier ones keep the tail hash). One revision. The
    caller writes the state. Returns (result, mechanical observation ids).
    """
    _bounded_label(actor, "verification actor")
    declaration = _declared_check(state, run["check_id"])
    earlier = _latest_check_results(state).get(str(declaration["id"]), [])
    number = (int(earlier[-1]["run"]) if earlier else 0) + 1
    identifier = f"{declaration['id']}.r{number}"
    if identifier in _task_object_ids(state):
        raise ThalirisError(_errors.TASK_OBJECT_ID_COLLISION, "task object id collision", details={"ids": [identifier]})
    seconds = int(run["duration_ms"]) / 1000
    exit_text = "no exit code" if run["exit_code"] is None else f"exit {run['exit_code']}"
    material = {
        "id": identifier, "kind": "check", "outcome": run["outcome"],
        "summary": f"{run['outcome']}: {exit_text} in {seconds:.1f}s",
        "source_refs": [], "observed_by": actor,
        "candidate_identity": _canonical_sha256({"task_id": state["task_id"], "tree_identity": run["tree_identity"],
                                                 "files_digest": run["files_digest"]}),
        "observed_files": run["observed_files"],
        "check_id": declaration["id"], "run": number, "command_sha256": run["command_sha256"], "files_digest": run["files_digest"],
        "files_changed_during_run": run["files_changed_during_run"], "exit_code": run["exit_code"], "duration_ms": run["duration_ms"],
        "output_tail_sha256": hashlib.sha256(str(run["output_tail"]).encode("utf-8")).hexdigest(), "output_bytes": run["output_bytes"],
        "tree_identity": run["tree_identity"], "tree_identity_before": run["tree_identity_before"],
    }
    result = {**material, "output_tail": run["output_tail"], "observed_at": datetime.now(timezone.utc).isoformat(),
              "observed_at_revision": state["revision"], "result_hash": _canonical_sha256(material)}
    _verification_result(result)
    drop = {str(item["id"]) for item in earlier[:-(CHECK_RESULT_HISTORY - 1)]} if len(earlier) >= CHECK_RESULT_HISTORY else set()
    kept = [({**item, "output_tail": None} if item.get("check_id") == declaration["id"] else item)
            for item in state["verification_results"] if str(item["id"]) not in drop]
    snapshot = copy.deepcopy(state)
    try:
        # Evicted results of this check older than the kept history are dropped as hot ones are.
        _forget_check_runs(state, str(declaration["id"]), number - (CHECK_RESULT_HISTORY - 1))
        state["verification_results"] = kept + [result]
        state["schema_version"] = max(state["schema_version"], _VERIFICATION_SCHEMA_VERSION)
        view = verification_view(root, state, tree=str(run["tree_identity"]))
        mechanical = record_check_tamper(root, state, view=view, bump=False)
        state["revision"] += 1
    except BaseException:
        state.clear()
        state.update(snapshot)
        raise
    return result, mechanical


def task_verify(root: Path, actor: str, check_id: str, *, base_revision: int | None = None,
                compact_evidence: bool = False) -> dict[str, object]:
    """Run one declared check and record its result. Any task actor may call it.

    Core runs the declared argv itself (no shell, declared cwd and timeout)
    outside the task lock, then appends the result under the lock. Like
    ``task-observe`` the append needs no revision; a supplied
    ``base_revision`` is enforced strictly before the run and again at the
    append. A PASS grants nothing: it only stops the gate withholding while it
    stays fresh.
    """
    root = _repo_root(root)
    _bounded_label(actor, "verification actor")
    _refuse_reserved_actor(actor)
    with _lock(root):
        state = _load_state(root, active=True)
        if base_revision is not None:
            check_revision(state, base_revision)
        declaration = copy.deepcopy(_declared_check(state, check_id))
    run = _run_declared_check(root, declaration)
    with _lock(root):
        state = _load_state(root, active=True)
        if base_revision is not None:
            check_revision(state, base_revision)
        result, mechanical = record_check_run(root, state, actor, run)
        _write_state(root, state)
        standing = next(entry for entry in verification_view(root, state, tree=str(run["tree_identity"]))["checks"]
                        if entry["id"] == declaration["id"])
    changed = ["verification_results"] + (["evidence_continuity"] if mechanical else [])
    response = task_write_response(state, changed) if compact_evidence else _task_ack(state, changed)
    response["result"] = {
        **{key: result[key] for key in ("id", "check_id", "run", "outcome", "exit_code", "duration_ms", "tree_identity",
                                        "files_changed_during_run", "output_tail", "output_bytes")},
        "tree_changed_during_run": result["tree_identity"] != result["tree_identity_before"],
        "status": standing["status"], "fresh": standing["status"] in ("green", "red"),
    }
    if "reason" in standing:
        response["result"]["reason"] = standing["reason"]
    if mechanical:
        response["mechanical_observations"] = mechanical
    return response


# --- close gate ---

def _latest_requirement_judgments(state: dict[str, object]) -> dict[str, dict[str, object]]:
    """Per requirement (in order of its first judgment), its latest judgment over hot and evicted judgments:
    ``{id, requirement_ref, candidate, outcome, overridden}`` (what the close gate and surfacing read)."""
    latest: dict[str, tuple[int, dict[str, object]]] = {}
    for (requirement, candidate), (_, last, identifier, code, _) in _judgment_keys(state):
        current = latest.get(requirement)
        if current is None or last > current[0]:
            latest[requirement] = (last, {"id": identifier, "requirement_ref": requirement, "candidate": candidate,
                                          "outcome": _JUDGMENT_OUTCOMES[code % 4], "overridden": code >= 4})
    return {requirement: item for requirement, (_, item) in latest.items()}


def surfaced_requirements(state: dict[str, object]) -> dict[str, object]:
    """Every requirement no declared check fully decides, with its latest judgment.

    Lists each ``judgment-only`` and ``partial`` requirement, plus any
    ``compiled`` requirement that has no declared check (``reason:
    no-declared-check``). ``latest_judgment`` is null when none exists.
    """
    covered = {ref for check in state.get("checks", []) for ref in check["requirement_refs"]}
    latest = _latest_requirement_judgments(state)
    entries: list[dict[str, object]] = []
    for requirement in state.get("evidence_continuity", {}).get("requirements", []):
        kind = requirement.get("kind", REQUIREMENT_KIND_DEFAULT)
        uncovered = kind != REQUIREMENT_KIND_DEFAULT and requirement["id"] not in covered
        if kind == "compiled" and not uncovered:
            continue
        judgment = latest.get(str(requirement["id"]))
        entry: dict[str, object] = {"requirement": requirement["id"], "kind": kind, "latest_judgment": None if judgment is None else {
            "id": judgment["id"], "outcome": judgment["outcome"], "candidate": judgment["candidate"],
            "overridden": judgment["overridden"]}}
        if uncovered:
            entry["reason"] = "no-declared-check"
        entries.append(entry)
    return {"surfaced": entries[:SURFACED_MAX], "surfaced_total": len(entries), "surfaced_truncated": len(entries) > SURFACED_MAX}


def close_state(root: Path | None, state: dict[str, object], *, override_reason: str | None = None,
                actor: str | None = None) -> dict[str, object]:
    """Close a loaded ACTIVE state through the close gate, in an adapter-owned locked transaction.

    Refused as ``VERIFICATION_WITHHELD`` while any declared check is red, unrun
    or stale for the current tree, unless ``override_reason`` is given; the
    reason and the checks it overrode are stored in ``closure``. A task with
    declared checks cannot reach DONE any other way (state validation refuses a
    DONE state with checks and no closure record). Sets DONE, bumps the
    revision once and returns ``{"changed", "surfaced", "surfaced_total",
    "surfaced_truncated", "closure"?, "mechanical_observations"?}``. The caller
    has checked the revision and writes the state. A refusal leaves ``state``
    unchanged.
    """
    if state["status"] != "ACTIVE":
        raise ThalirisError(_errors.TASK_NOT_ACTIVE, "current task is not ACTIVE",
                            details={"task_id": state["task_id"], "status": state["status"]})
    if actor is not None:
        _bounded_label(actor, "close actor")
    extras: dict[str, object] = {"changed": []}
    snapshot = copy.deepcopy(state)
    try:
        satisfied = {ref for ref, item in _latest_requirement_judgments(state).items() if item["outcome"] == "satisfied"}
        unchecked = [_no_check_entry(ref) for ref in sorted(_unchecked_compiled(state) & satisfied)]
        if state.get("checks") or unchecked:
            view = verification_view(root, state) if state.get("checks") else {"tree_identity": None, "checks": []}
            blocking = [_gate_entry(entry) for entry in view["checks"] if entry["status"] != "green"] + unchecked
            if blocking and override_reason is None:
                raise _withheld("close", view, {"checks": blocking[:STATUS_CHECKS_MAX], "checks_total": len(blocking)})
            mechanical = record_check_tamper(root, state, view=view, bump=False) if root is not None and state.get("checks") else []
            closure: dict[str, object] = {"gate": "overridden" if blocking else "clear", "tree_identity": (
                view["tree_identity"] or (tree_identity(root) if root is not None else TREE_UNKNOWN))}
            if blocking:
                closure["override_reason"] = _override_text(override_reason)
                closure["overridden_checks"] = blocking
            if actor is not None:
                closure["by"] = actor
            state["closure"] = closure
            state["schema_version"] = max(state["schema_version"], _VERIFICATION_SCHEMA_VERSION)
            extras["closure"] = closure
            extras["changed"] = ["closure"] + (["evidence_continuity"] if mechanical else [])
            if mechanical:
                extras["mechanical_observations"] = mechanical
        state["status"] = "DONE"
        state["revision"] += 1
    except BaseException:
        state.clear()
        state.update(snapshot)
        raise
    extras.update(surfaced_requirements(state))
    return extras


# --- typed claims and handoff usage ---

def _handoff(state: dict[str, object], handoff_id: object) -> dict[str, object]:
    """The hot handoff with this id; an evicted handoff is re-hydrated first (it is about to change)."""
    for item in state.get("evidence_continuity", {}).get("handoffs", []):
        if item["id"] == handoff_id:
            return item
    if isinstance(handoff_id, str) and _eviction_entries(state) and handoff_id in _index_map(state)["handoffs"]:
        _rehydrate_from_state(state, [("handoffs", handoff_id)])
        return _handoff(state, handoff_id)
    raise ThalirisError(_errors.HANDOFF_NOT_FOUND, "handoff is not registered",
                        recovery="use the id of a handoff registered in this task; nothing was recorded",
                        details={"handoff_id": _preview(handoff_id)})


def _claim_observation_ids(handoff_id: str, taken: set[str], count: int) -> list[str]:
    stem = handoff_id if len(handoff_id) <= 54 else "claim-" + hashlib.sha256(handoff_id.encode("utf-8")).hexdigest()[:16]
    ids: list[str] = []
    number = 0
    while len(ids) < count:
        number += 1
        identifier = f"{stem}.c{number}"
        if identifier not in taken and identifier + ".s" not in taken:
            ids.append(identifier)
            taken.update({identifier, identifier + ".s"})
    return ids


def ingest_claims(state: dict[str, object], handoff_id: str, text: object) -> dict[str, object]:
    """Ingest the typed claim block of one handoff's final message into a locked state.

    ``contradicts`` and ``unknown`` claims become ordinary observations (open
    obligations) carrying the handoff's producer and candidate, the claimed
    requirement, a source built from the claim's ``evidence`` and a ``claim``
    record ``{requirement, polarity, basis, evidence}``. ``supports`` claims
    become support entries on the handoff (counted per requirement), not
    obligations. A claim whose requirement is not among the handoff's refs
    becomes an unassigned observation whatever its polarity. Duplicates are
    merged, never dropped silently: an adverse claim equal in (requirement,
    evidence, polarity) to a still-open claim observation of the same candidate,
    or a support equal in (requirement, evidence) to one already counted for the
    candidate, only raises ``duplicates``. A missing or malformed block records
    one non-obligation marker. A handoff whose block was already ingested is
    left as it is (``already_ingested``); a missing/malformed marker may be
    replaced once by a later readable block. One revision when anything is
    written; the caller writes the state.
    """
    handoff = _handoff(state, handoff_id)
    parsed = parse_claim_block(text)
    prior = handoff.get("claims")
    if prior is not None and (prior["status"] == "present" or parsed["status"] != "present"):
        return {"handoff_id": handoff["id"], "status": prior["status"], "already_ingested": True, "changed": False,
                "observations": [], "unassigned": [], "supports": _support_counts(prior.get("supports", [])), "duplicates": 0,
                "total": prior.get("total", 0), "truncated": prior.get("truncated", False), "invalid": prior.get("invalid", 0)}
    snapshot = copy.deepcopy(state)
    response: dict[str, object] = {"handoff_id": handoff["id"], "status": parsed["status"], "already_ingested": False, "changed": True,
                                   "observations": [], "unassigned": [], "supports": {}, "duplicates": 0,
                                   "total": parsed["total"], "truncated": parsed["truncated"], "invalid": parsed["invalid"]}
    try:
        additions: list[tuple[str, str | None, object]] = []
        if parsed["status"] != "present":
            marker: dict[str, object] = {"status": parsed["status"]}
            if parsed["status"] == "malformed" and parsed["error"]:
                marker["error"] = str(parsed["error"])[:200]
        else:
            data = state["evidence_continuity"]
            judgments = data["judgments"]
            incorporated = {(judgment["requirement_ref"], ref) for judgment in judgments for ref in judgment["observation_refs"]}
            cited = {ref for judgment in judgments for ref in judgment["observation_refs"]}
            adverse = {}
            for observation in data["observations"]:
                if "claim" not in observation or observation["candidate"] != handoff["candidate"]:
                    continue
                refs = observation["requirement_refs"]
                still_open = any((ref, observation["id"]) not in incorporated for ref in refs) if refs else observation["id"] not in cited
                if still_open:
                    claim = observation["claim"]
                    adverse[(claim["requirement"], claim["evidence"], claim["polarity"], bool(refs))] = observation["id"]
            counted = {(support["requirement"], support["evidence"]) for other in data["handoffs"]
                       if other["candidate"] == handoff["candidate"] and other.get("claims", {}).get("status") == "present"
                       for support in other["claims"]["supports"]}
            # Supports already counted on evicted handoffs of this candidate (dedupe keys in the index).
            evicted_keys = _archive_totals(state).support_keys.get(str(handoff["candidate"]), set()) if _eviction_entries(state) else set()
            declared = {str(check["id"]) for check in state.get("checks", [])}
            supports: list[dict[str, object]] = []
            pending: list[dict[str, object]] = []
            duplicates = 0
            for claim in parsed["claims"]:
                assigned = claim["requirement"] in handoff["requirement_refs"]
                if assigned and claim["polarity"] == "supports":
                    key = (claim["requirement"], claim["evidence"])
                    if key in counted or (evicted_keys and _support_key(handoff["candidate"], claim["requirement"], claim["evidence"]) in evicted_keys):
                        duplicates += 1
                    else:
                        counted.add(key)
                        supports.append({"requirement": claim["requirement"], "evidence": claim["evidence"], "basis": claim["basis"]})
                    continue
                key = (claim["requirement"], claim["evidence"], claim["polarity"], assigned)
                if key in adverse:
                    duplicates += 1
                    continue
                adverse[key] = None
                pending.append({**claim, "assigned": assigned})
            ids = _claim_observation_ids(str(handoff["id"]), _task_object_ids(state), len(pending))
            for identifier, claim in zip(ids, pending):
                record = {key: claim[key] for key in ("requirement", "polarity", "basis", "evidence", "text_truncated", "normalized") if key in claim}
                additions.append(("observations", str(handoff["producer"]), {
                    "id": identifier, "candidate": handoff["candidate"], "handoff_id": handoff["id"],
                    "requirement_refs": [claim["requirement"]] if claim["assigned"] else [],
                    "source_refs": [identifier + ".s"], "text": claim["text"], "claim": record,
                    "sources": [{"id": identifier + ".s", "kind": "check" if claim["evidence"] in declared else "claim-evidence",
                                 "locator": claim["evidence"], "summary": f"{claim['basis']} evidence cited by a typed {claim['polarity']} claim"}],
                }))
                if not claim["assigned"]:
                    response["unassigned"].append(identifier)
            marker = {"status": "present", "total": parsed["total"], "truncated": parsed["truncated"], "invalid": parsed["invalid"],
                      "duplicates": duplicates, "supports": supports, "observations": ids}
            response.update(observations=ids, supports=_support_counts(supports), duplicates=duplicates)
        handoff["claims"] = marker
        state["schema_version"] = max(state["schema_version"], _VERIFICATION_SCHEMA_VERSION)
        if additions:
            _append_continuity_items(state, additions, bump=False, trusted=True)
        else:
            _validate_continuity(state)
        state["revision"] += 1
    except BaseException:
        state.clear()
        state.update(snapshot)
        raise
    return response


def _support_counts(supports: list[dict[str, object]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for support in supports:
        counts[str(support["requirement"])] = counts.get(str(support["requirement"]), 0) + 1
    return counts


def task_ingest_claims(root: Path, handoff_id: str, text: str | None = None, *, input_file: str | None = None,
                       base_revision: int | None = None, compact_evidence: bool = False) -> dict[str, object]:
    """Adapter-called: ingest one handoff's final message (``text``, or the raw text file ``input_file``, ``-`` for stdin).

    See ``ingest_claims``. A supplied ``base_revision`` is enforced strictly;
    without one the append is serialized by the task lock like ``task-observe``.
    """
    root = _repo_root(root)
    if (text is None) == (input_file is None):
        raise ValueError("task-ingest-claims takes exactly one of the message text or a message file")
    message = text if text is not None else _read_input_text(input_file)
    with _lock(root):
        state = _load_state(root, active=True)
        if base_revision is not None:
            check_revision(state, base_revision)
        claims = ingest_claims(state, handoff_id, message)
        if claims["changed"]:
            _write_state(root, state)
    changed = ["evidence_continuity"] if claims["changed"] else []
    response = task_write_response(state, changed, appended=list(claims["observations"])) if compact_evidence else _task_ack(state, changed)
    response["claims"] = {key: value for key, value in claims.items() if key != "changed"}
    return response


def set_handoff_usage(state: dict[str, object], handoff_id: str, usage: object) -> dict[str, object]:
    """Record adapter-reported dispatch usage on one handoff of a locked state.

    ``usage`` holds any of ``model, effort, input_tokens, output_tokens,
    total_tokens, cost_usd, duration_ms, tool_uses, outcome``; every field is
    optional and an unreported field stays null. A later report merges: a
    non-null value replaces the stored one, null or absent keeps it. One
    revision; the caller writes the state. Returns the stored usage.
    """
    handoff = _handoff(state, handoff_id)
    if not isinstance(usage, dict) or not usage or set(usage) - set(USAGE_FIELDS):
        unknown = sorted(set(usage) - set(USAGE_FIELDS))[:8] if isinstance(usage, dict) else []
        raise ThalirisError(_errors.HANDOFF_USAGE_INVALID, "invalid handoff usage",
                            recovery="report only the listed fields; nothing was recorded",
                            details={"expected": "a non-empty object with any of " + ", ".join(USAGE_FIELDS), "unknown_fields": unknown})
    prior = handoff.get("usage") or {}
    merged = {field: usage[field] if usage.get(field) is not None else prior.get(field) for field in USAGE_FIELDS}
    problem = _usage_problem(merged)
    if problem:
        raise ThalirisError(_errors.HANDOFF_USAGE_INVALID, "invalid handoff usage",
                            recovery="correct the named field; nothing was recorded", details={"expected": problem})
    handoff["usage"] = merged
    state["schema_version"] = max(state["schema_version"], _VERIFICATION_SCHEMA_VERSION)
    state["revision"] += 1
    return merged


def task_handoff_usage(root: Path, handoff_id: str, input_file: str | dict[str, object] | None,
                       *, base_revision: int | None = None) -> dict[str, object]:
    """Adapter-called: record dispatch usage on a handoff (see ``set_handoff_usage``)."""
    root = _repo_root(root)
    usage = dict(input_file) if isinstance(input_file, dict) else _read_input(input_file)
    with _lock(root):
        state = _load_state(root, active=True)
        if base_revision is not None:
            check_revision(state, base_revision)
        stored = set_handoff_usage(state, handoff_id, usage)
        _write_state(root, state)
    return {**_task_ack(state, ["evidence_continuity"]), "handoff_id": handoff_id, "usage": stored}


# --- lane counter and advisories ---

def _lane_path(root: Path, task_id: str) -> Path:
    if str(uuid.UUID(task_id)) != task_id:
        raise ValueError("invalid task id")
    return _safe_without_final_symlink(root, f".context/tasks/{task_id}/lane.json")


def lane_counters(root: Path, task_id: str) -> dict[str, int]:
    """Adapter-reported lane counters for a task; an absent or unreadable sidecar reads as zero."""
    try:
        raw = json.loads(_lane_path(root, task_id).read_text(encoding="utf-8"))
        value = raw.get("controller_tool_output_tokens") if isinstance(raw, dict) and raw.get("task_id") == task_id else None
    except (OSError, ValueError):
        value = None
    return {"controller_tool_output_tokens": value if type(value) is int and 0 <= value <= LANE_COUNTER_MAX else 0}


def task_lane_counter(root: Path, *, add: int | None = None, set_to: int | None = None) -> dict[str, object]:
    """Adapter-called: update the Controller tool-output token counter of the selected ACTIVE task.

    Exactly one of ``add`` (a delta) or ``set_to`` (an absolute value). The
    counter feeds a lane advisory only, so it lives in the task-local sidecar
    ``.context/tasks/<task id>/lane.json`` rather than the ledger: updating it
    changes neither the task revision nor the bytes an authority anchor pins.
    """
    root = _repo_root(root)
    value = add if add is not None else set_to
    if (add is None) == (set_to is None) or type(value) is not int or not 0 <= value <= LANE_COUNTER_MAX:
        raise ThalirisError(_errors.LANE_COUNTER_INVALID, "invalid lane counter update",
                            recovery="supply exactly one of add or set as a non-negative integer",
                            details={"expected": f"exactly one of add or set, an integer from 0 to {LANE_COUNTER_MAX}"})
    with _lock(root):
        state = _load_state(root, active=True)
        task_id = str(state["task_id"])
        total = min(lane_counters(root, task_id)["controller_tool_output_tokens"] + value if add is not None else value, LANE_COUNTER_MAX)
        record = {"version": 1, "task_id": task_id, "controller_tool_output_tokens": total,
                  "updated_at": datetime.now(timezone.utc).isoformat()}
        _atomic_write(_lane_path(root, task_id), (json.dumps(record, sort_keys=True, indent=2) + "\n").encode("utf-8"))
    return {"ok": True, "task_id": task_id, "revision": state["revision"], "controller_tool_output_tokens": total}


def advisory_thresholds(root: Path | None) -> dict[str, int]:
    """Lane advisory thresholds: the defaults, overridden by ``advisories`` in ``.context/config.json``."""
    thresholds = dict(ADVISORY_DEFAULTS)
    if root is None:
        return thresholds
    try:
        raw = json.loads(_safe_without_final_symlink(root, ".context/config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return thresholds
    overrides = raw.get("advisories") if isinstance(raw, dict) else None
    if isinstance(overrides, dict):
        for key in thresholds:
            if type(overrides.get(key)) is int and overrides[key] >= 0:
                thresholds[key] = overrides[key]
    return thresholds


def _glob_covers(pattern: str, path: str) -> bool:
    """POSIX glob with ``**``; a pattern that names a directory covers everything below it."""
    pattern = pattern.strip().replace("\\", "/")
    while pattern.startswith("./"):
        pattern = pattern[2:]
    pattern = pattern.strip("/")
    if not pattern:
        return False
    parts: list[str] = []
    index = 0
    while index < len(pattern):
        if pattern.startswith("**/", index):
            parts.append("(?:.*/)?")
            index += 3
        elif pattern.startswith("**", index):
            parts.append(".*")
            index += 2
        elif pattern[index] == "*":
            parts.append("[^/]*")
            index += 1
        elif pattern[index] == "?":
            parts.append("[^/]")
            index += 1
        else:
            parts.append(re.escape(pattern[index]))
            index += 1
    return re.fullmatch("".join(parts) + "(?:/.*)?", path) is not None


def _changed_lines(root: Path, state: dict[str, object], paths: list[str]) -> tuple[int | None, bool]:
    """Approximate changed-line count of the task-surface delta: (lines or None, exact)."""
    if len(paths) > ADVISORY_LINE_COUNT_MAX_PATHS:
        return None, False
    baseline = state["task_surface_baseline"]
    exact = not ({str(item["path"]) for item in baseline} & set(paths)) if isinstance(baseline, list) else False
    counted: dict[str, int] = {}
    base = state.get("task_base_head")
    if base:
        try:
            proc = subprocess.run(["git", "diff", "--numstat", "--no-renames", "-z", str(base), "--", *paths], cwd=root,
                                  capture_output=True, check=False, stdin=subprocess.DEVNULL, timeout=GIT_TIMEOUT_SECONDS)
        except (OSError, subprocess.SubprocessError):
            return None, False
        if proc.returncode:
            return None, False
        for record in proc.stdout.decode("utf-8", errors="surrogateescape").split("\0"):
            fields = record.split("\t", 2)
            if len(fields) != 3:
                continue
            if fields[0].isdigit() and fields[1].isdigit():
                counted[fields[2].replace("\\", "/")] = int(fields[0]) + int(fields[1])
            else:
                counted[fields[2].replace("\\", "/")] = 0
                exact = False
    total = 0
    for path in paths:
        if path in counted:
            total += counted[path]
            continue
        target = root.joinpath(*path.split("/"))
        try:
            if target.is_symlink() or not target.is_file():
                exact = False
                continue
            if target.stat().st_size > ADVISORY_LINE_COUNT_MAX_FILE_BYTES:
                return None, False
            data = target.read_bytes()
        except OSError:
            exact = False
            continue
        total += data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)
    return total, exact


def lane_advisories(root: Path | None, state: dict[str, object], contract: dict[str, object],
                    *, view: dict[str, object] | None = None) -> dict[str, object]:
    """Lane advisories for an adaptive-mode task. They are surfaced and never block.

    ``contract`` is the authority contract (``execution_mode``, optional
    ``write_surface`` globs). Items, each with a stable ``code``:

    - ``CHECK_FAILED_TWICE``: a check whose last two results are FAIL on two
      distinct known tree identities.
    - ``WRITE_SURFACE_EXCEEDED``: task-surface delta paths outside ``write_surface``.
    - ``CHANGE_SIZE_EXCEEDED``: the delta has more than ``max_files`` files or
      more than ``max_changed_lines`` changed lines.
    - ``JUDGMENT_ONLY_REQUIREMENT``: requirements whose kind is judgment-only.
    - ``CONTRACT_SURFACE``: requirements flagged ``surface: contract``.
    - ``CONTROLLER_TOOL_OUTPUT``: the adapter-reported Controller tool-output
      token counter is above its threshold.
    """
    thresholds = advisory_thresholds(root)
    items: list[dict[str, object]] = []
    unavailable: list[str] = []
    for check_id, runs in _latest_check_results(state).items():
        if len(runs) >= 2 and all(run["outcome"] == "FAIL" and run["tree_identity"] != TREE_UNKNOWN for run in runs[-2:]) \
                and runs[-1]["tree_identity"] != runs[-2]["tree_identity"]:
            items.append({"code": "CHECK_FAILED_TWICE", "check_id": check_id, "result_ids": [run["id"] for run in runs[-2:]],
                          "tree_identities": [run["tree_identity"] for run in runs[-2:]]})
    try:
        delta = _surface_delta(root, state["task_surface_baseline"]) if root is not None else {"status": "UNAVAILABLE"}
    except (ValueError, OSError):
        delta = {"status": "UNAVAILABLE"}
    if delta["status"] != "AVAILABLE":
        unavailable.append("task_surface")
    else:
        paths = [path for path in delta["paths"] if path != ".context" and not path.startswith(".context/")]
        surface = contract.get("write_surface")
        if isinstance(surface, list) and surface:
            outside = [path for path in paths if not any(isinstance(glob, str) and _glob_covers(glob, path) for glob in surface)]
            if outside:
                items.append({"code": "WRITE_SURFACE_EXCEEDED", "paths": outside[:8], "paths_total": len(outside)})
        lines, exact = _changed_lines(root, state, paths) if paths else (0, True)
        if len(paths) > thresholds["max_files"] or (lines is not None and lines > thresholds["max_changed_lines"]):
            items.append({"code": "CHANGE_SIZE_EXCEEDED", "files": len(paths), "changed_lines": lines, "changed_lines_exact": exact,
                          "max_files": thresholds["max_files"], "max_changed_lines": thresholds["max_changed_lines"]})
    requirements = state.get("evidence_continuity", {}).get("requirements", [])
    judgment_only = [item["id"] for item in requirements if item.get("kind", REQUIREMENT_KIND_DEFAULT) == REQUIREMENT_KIND_DEFAULT]
    if judgment_only:
        items.append({"code": "JUDGMENT_ONLY_REQUIREMENT", "requirements": judgment_only[:16], "requirements_total": len(judgment_only)})
    contract_surface = [item["id"] for item in requirements if item.get("surface") == "contract"]
    if contract_surface:
        items.append({"code": "CONTRACT_SURFACE", "requirements": contract_surface[:16], "requirements_total": len(contract_surface)})
    tokens = lane_counters(root, str(state["task_id"]))["controller_tool_output_tokens"] if root is not None else 0
    if tokens > thresholds["controller_tool_output_tokens"]:
        items.append({"code": "CONTROLLER_TOOL_OUTPUT", "tokens": tokens, "threshold": thresholds["controller_tool_output_tokens"]})
    result: dict[str, object] = {"blocking": False, "items": items}
    unspecified = sorted(key for key in ("boundary", "invariants") if contract.get(key) == "unspecified")
    if unspecified:
        result["contract_unspecified"] = unspecified
    if unavailable:
        result["unavailable"] = unavailable
    return result


# --- status sections ---

def _verification_section(state: dict[str, object], view: dict[str, object] | None, live: bool) -> dict[str, object] | None:
    continuity = state.get("evidence_continuity", {})
    overrides = [item for item in continuity.get("judgments", []) if "override_reason" in item]
    archived = _archive_totals(state) if _eviction_entries(state) else _Totals()
    override_total = len(overrides) + archived.overrides
    requirements = continuity.get("requirements", [])
    kinds = any({"kind", "surface"} & item.keys() for item in requirements)
    if view is None and not override_total and not kinds:
        return None
    section: dict[str, object] = {}
    if view is not None:
        entries = view["checks"]
        tallies = {status: sum(entry["status"] == status for entry in entries) for status in CHECK_STATUSES}
        ordered = sorted(entries, key=lambda entry: entry["status"] == "green")
        recorded = dict(archived.mechanism)
        recorded.update({(item["mechanism"]["check_id"], item["mechanism"]["files_digest"]): item["id"]
                         for item in continuity.get("observations", []) if "mechanism" in item})
        section.update({
            "live": live, "tree_identity": view["tree_identity"] or ("NOT_COMPUTED" if live else TREE_UNKNOWN),
            "checks_total": len(entries), **tallies,
            "checks": [{key: entry[key] for key in ("id", "status", "reason", "outcome", "result_id", "requirement_refs") if key in entry}
                       for entry in ordered[:STATUS_CHECKS_MAX]],
            "checks_truncated": len(entries) > STATUS_CHECKS_MAX,
            "withheld_requirements": sorted({ref for entry in entries if entry["status"] != "green" for ref in entry["requirement_refs"]})[:32],
        })
        tamper = [{"check_id": entry["id"], "paths": [item["path"] for item in entry["changed_files"][:4]],
                   "recorded": (entry["id"], entry["files_digest"]) in recorded,
                   **({"observation_id": recorded[(entry["id"], entry["files_digest"])]} if (entry["id"], entry["files_digest"]) in recorded else {})}
                  for entry in entries if entry["tampered"]]
        if tamper:
            section["tamper"] = tamper[:STATUS_CHECKS_MAX]
    if kinds or view is not None:
        covered = {ref for check in state.get("checks", []) for ref in check["requirement_refs"]}
        section["requirement_kinds"] = {kind: sum(item.get("kind", REQUIREMENT_KIND_DEFAULT) == kind for item in requirements)
                                        for kind in REQUIREMENT_KINDS}
        uncovered = [item["id"] for item in requirements
                     if item.get("kind", REQUIREMENT_KIND_DEFAULT) != REQUIREMENT_KIND_DEFAULT and item["id"] not in covered]
        if uncovered:
            section["uncovered_requirements"] = uncovered[:32]
    if override_total or "closure" in state:
        # The last 8 overridden judgments always stay hot (``_hot_keep``).
        listed = [{"judgment_id": item["id"], "requirement_ref": item["requirement_ref"],
                   "override_reason": item["override_reason"][:160], "overridden_checks": [check["id"] for check in item["overridden_checks"]][:8]}
                  for item in overrides[-8:]]
        section["overrides"] = {"total": override_total, "judgments": listed}
        closure = state.get("closure")
        if closure is not None and closure["gate"] == "overridden":
            section["overrides"]["close"] = {"override_reason": closure["override_reason"][:160],
                                             "overridden_checks": [check["id"] for check in closure["overridden_checks"]][:8]}
    return section


def _claims_section(state: dict[str, object]) -> dict[str, object] | None:
    """Claims totals over hot and evicted handoffs; the listed ids come from hot handoffs (the last 8
    of each list always stay hot, see ``_hot_keep``)."""
    handoffs = [item for item in state.get("evidence_continuity", {}).get("handoffs", []) if "claims" in item]
    archived = _archive_totals(state) if _eviction_entries(state) else _Totals()
    if not handoffs and not archived.claims["ingested"]:
        return None
    without = [item["id"] for item in handoffs if item["claims"]["status"] != "present"]
    supports: dict[str, int] = dict(archived.supports)
    for item in handoffs:
        for requirement, count in _support_counts(item["claims"].get("supports", [])).items():
            supports[requirement] = supports.get(requirement, 0) + count
    truncated = [item["id"] for item in handoffs if item["claims"].get("truncated")]
    truncated_total = len(truncated) + archived.claims["truncated"]
    section: dict[str, object] = {
        "handoffs_ingested": len(handoffs) + archived.claims["ingested"],
        "handoffs_without_typed_claims": {
            "total": len(without) + archived.claims["missing"] + archived.claims["malformed"], "ids": without[-8:],
            "missing": sum(item["claims"]["status"] == "missing" for item in handoffs) + archived.claims["missing"],
            "malformed": sum(item["claims"]["status"] == "malformed" for item in handoffs) + archived.claims["malformed"]},
        "supports": dict(sorted(supports.items())[:32]),
    }
    if truncated_total:
        section["handoffs_with_truncated_claims"] = {"total": truncated_total, "ids": truncated[-8:]}
    return section


def _usage_totals(records: list[dict[str, object]]) -> dict[str, object]:
    """Totals of usage records; cost is summed exactly and rounded once (see ``_UsageSum``)."""
    totals = _UsageSum()
    for record in records:
        totals.add(record)
    return totals.view()


def _usage_groups(groups: dict[str, _UsageSum]) -> dict[str, object]:
    ranked = sorted(((name, total) for name, total in groups.items() if total.handoffs), key=lambda pair: (-pair[1].handoffs, pair[0]))
    result = {name: total.view() for name, total in ranked[:8]}
    if len(ranked) > 8:
        rest = _UsageSum(_USAGE_GROUP_FIELDS)
        for _, total in ranked[8:]:
            rest.merge(total)
        result["(other)"] = rest.view()
    return result


def usage_summary(state: dict[str, object]) -> dict[str, object] | None:
    """Small aggregate of adapter-reported dispatch usage: totals, by role (handoff producer) and by model.

    Hot handoffs and the usage totals of evicted handoffs combine exactly. ``outcomes`` lists
    outcomes in order of first appearance, evicted handoffs (oldest segment first) before hot ones.
    """
    totals = _archive_totals(state) if _eviction_entries(state) else _Totals()
    for item in state.get("evidence_continuity", {}).get("handoffs", []):
        if "usage" in item:
            totals.add("handoffs", {"producer": item["producer"], "usage": item["usage"]})
    if not totals.usage.handoffs:
        return None
    return {"totals": totals.usage.view(), "by_role": _usage_groups(totals.by_role),
            "by_model": _usage_groups(totals.by_model), "outcomes": {key: count for key, count in totals.outcomes.items() if count}}


def _feature_sections(root: Path | None, state: dict[str, object], contract: dict[str, object] | None) -> dict[str, object]:
    """Status sections that exist only when the task uses the matching feature."""
    if contract is not None and not isinstance(contract, dict):
        raise ValueError("status contract must be a JSON object")
    sections: dict[str, object] = {}
    view = verification_view(root, state) if state.get("checks") else None
    verification = _verification_section(state, view, root is not None)
    if verification is not None:
        sections["Verification"] = verification
    claims = _claims_section(state)
    if claims is not None:
        sections["Claims"] = claims
    usage = usage_summary(state)
    if usage is not None:
        sections["Usage"] = usage
    archive = archive_summary(state)
    if archive is not None:
        sections["Archive"] = archive
    if contract is not None and contract.get("execution_mode") == "adaptive":
        sections["Advisories"] = lane_advisories(root, state, contract, view=view)
    return sections



def task_promote(root: Path, actor: str, base_revision: int, input_file: str | None) -> dict[str, object]:
    """Persist exactly the model-selected records without epistemic adjudication."""
    root = _repo_root(root)
    if not isinstance(actor, str) or not actor:
        raise ValueError("invalid promotion identity")
    payload = _read_input(input_file)
    if set(payload) - {"records", "index_update"} or "records" not in payload or not isinstance(payload["records"], list) or not payload["records"]:
        raise ValueError("task-promote requires a non-empty records list")
    with _lock(root):
        state = _load_state(root, active=True)
        check_revision(state, base_revision)
        sources = {str(item["id"]): item for item in state["evidence_refs"]}
        artifacts = {str(item["id"]): item for item in state["artifact_refs"]}
        evicted_sources = _index_map(state)["evidence_refs"] if _eviction_entries(state) else {}
        known_refs = set(sources) | set(artifacts) | set(evicted_sources)
        writes: dict[str, bytes] = {}
        promoted: list[str] = []
        promotion_ids: set[str] = set()
        promotion_paths: set[str] = set()
        task_object_ids = _task_object_ids(state)
        for value in payload["records"]:
            if not isinstance(value, dict):
                raise ValueError("invalid promotion record")
            # Legacy promotion inputs may carry durable Markdown Status.  It
            # is opaque compatibility data and is deliberately not rendered
            # or validated for new documents.
            allowed = {"id", "path", "title", "text", "source_refs", "status"}
            if set(value) - allowed or "path" not in value:
                raise ValueError("invalid promotion record")
            identifier = _bounded_label(value.get("id"), "promotion id")
            if identifier in promotion_ids:
                raise ValueError("duplicate promotion id")
            if identifier in task_object_ids:
                raise ValueError("promotion id conflicts with task object")
            promotion_ids.add(identifier)
            title = value.get("title", identifier)
            text = value.get("text")
            if not isinstance(title, str) or not title.strip() or len(title) > 300 or "\n" in title or "\r" in title or not isinstance(text, str) or not text.strip() or len(text) > 16_384:
                raise ValueError("invalid promotion record")
            refs = value.get("source_refs", [])
            if not isinstance(refs, list) or len(refs) > 64 or len(set(refs)) != len(refs) or any(not isinstance(ref, str) or ref not in known_refs for ref in refs):
                raise ValueError("promotion source reference is unknown")
            descriptors: list[dict[str, object]] = []
            described: set[tuple[str, str]] = set()

            def append_source_descriptor(source_id: str) -> None:
                key = ("source", source_id)
                if key in described:
                    return
                source = sources.get(source_id)
                if source is None and source_id in evicted_sources:
                    source, _ = _evicted_object(root, state, "evidence_refs", source_id, evicted_sources[source_id])
                if source is None:
                    raise ValueError("artifact provenance source reference is unknown")
                # Durable provenance needs the full locator and summary, never an archive preview.
                source = hydrate_archived(root, state, "evidence_refs", source)
                described.add(key)
                descriptor = {
                    "type": "source",
                    "source_id": source["id"],
                    "kind": source["kind"],
                    "locator": source["locator"],
                    "summary": source["summary"],
                    "source_refs": source.get("source_refs", []),
                }
                descriptors.append(descriptor)
                for parent_ref in source.get("source_refs", []):
                    append_source_descriptor(str(parent_ref))

            for ref in refs:
                if ref in sources and ref in artifacts:
                    raise ValueError("promotion source reference is ambiguous")
                if ref in artifacts:
                    artifact = artifacts[ref]
                    key = ("artifact", ref)
                    if key not in described:
                        descriptors.append({
                            "type": "artifact",
                            "artifact_id": artifact["id"],
                            "path": artifact["path"],
                            "content_sha256": artifact["content_sha256"],
                            "producer": artifact["producer"],
                            "task_id": artifact["task_id"],
                            "revision": artifact["revision"],
                            "source_refs": artifact.get("source_refs", []),
                        })
                        described.add(key)
                    for source_ref in artifact.get("source_refs", []):
                        append_source_descriptor(str(source_ref))
                else:
                    append_source_descriptor(ref)
            relative = _valid_relative(root, value.get("path"))
            if not relative.startswith(".agent-memory/") or not relative.endswith(".md") or relative.endswith("/INDEX.md"):
                raise ValueError("promotion path must name a non-INDEX Markdown document under .agent-memory")
            if relative in promotion_paths:
                raise ValueError("duplicate promotion path")
            promotion_paths.add(relative)
            target = _safe_without_final_symlink(root, relative)
            if target.exists():
                raise ValueError("promotion refuses to overwrite an existing durable target")
            durable_body = text
            if descriptors:
                durable_body += "\n\n## Durable Source Descriptors\n\n```json\n" + json.dumps(descriptors, ensure_ascii=False, sort_keys=True, indent=2) + "\n```"
            rendered = _entry(
                title,
                durable_body,
                evidence="DURABLE_SOURCE_DESCRIPTORS" if descriptors else "NONE",
            )
            # Build the same item and response that document-get will return.
            # A file-size check alone misses metadata, freshness, and expanded
            # durable provenance in the JSON envelope.
            entry = parse_text(rendered.decode("utf-8"), Path(relative))
            if len(rendered) > EXPLICIT_DOCUMENT_MAX_BYTES:
                raise ValueError(f"promotion record exceeds {EXPLICIT_DOCUMENT_MAX_BYTES} bytes")
            preflight_item = _document_get_item(root, relative, rendered, entry)
            # A fresh document has no detail today, but source churn may add
            # the fixed diagnostic budget tomorrow. Reserve the longest later
            # freshness label too (MISSING and CHANGED are two bytes longer
            # than FRESH) in this same public item/response construction so
            # retrieval remains available at the boundary.
            preflight_item["freshness"] = "MISSING"
            preflight_item["freshness_detail"] = freshness_detail_budget_placeholder()
            if _document_response_size({"ok": True, "documents": [preflight_item]}) > EXPLICIT_DOCUMENT_MAX_BYTES:
                raise ValueError(f"document-get response exceeds {EXPLICIT_DOCUMENT_MAX_BYTES} bytes")
            writes[relative] = rendered
            promoted.append(relative)
        index_updated: str | None = None
        if "index_update" in payload:
            update = payload["index_update"]
            if not isinstance(update, dict) or set(update) != {"path", "base_sha256", "content"}:
                raise ValueError("invalid INDEX update")
            index_updated = _valid_relative(root, update["path"])
            if (
                index_updated not in {".agent-memory/INDEX.md", ".milestones/INDEX.md"}
                and not index_updated.startswith((".agent-memory/", ".milestones/"))
            ) or not index_updated.endswith("/INDEX.md"):
                raise ValueError("INDEX update path must name INDEX.md under a durable namespace")
            if index_updated in writes:
                raise ValueError("INDEX update conflicts with promotion document")
            base_sha256 = update["base_sha256"]
            content = update["content"]
            if not isinstance(base_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", base_sha256):
                raise ValueError("invalid INDEX base_sha256")
            if not isinstance(content, str):
                raise ValueError("invalid INDEX content")
            encoded = content.encode("utf-8")
            if len(encoded) > DURABLE_INDEX_HARD_MAX_BYTES:
                raise ValueError("INDEX_OVERSIZED")
            try:
                index_target = _safe_without_final_symlink(root, index_updated)
            except ValueError as exc:
                raise ValueError("INDEX update target does not exist") from exc
            if not index_target.is_file():
                raise ValueError("INDEX update target does not exist")
            if _digest(index_target.read_bytes()) != base_sha256:
                raise ValueError("INDEX revision conflict")
            parsed_index = parse_text(content, index_target)
            reference_errors = _index_reference_errors(root, index_target, parsed_index.body, planned_paths=set(writes))
            if reference_errors:
                raise ValueError("invalid INDEX references: " + "; ".join(reference_errors))
            writes[index_updated] = encoded
        backup = _apply_with_backup(root, writes, [], "task-promote")
    return {"ok": True, "task_id": state["task_id"], "state_revision": state["revision"], "promoted": promoted, "index_updated": index_updated, "backup": backup}


def document_maintain(root: Path, actor: str, base_revision: int, input_file: str | None) -> dict[str, object]:
    """Apply exact model-selected durable edits with digest CAS and recovery."""
    root = _repo_root(root)
    _bounded_label(actor, "maintenance actor")
    payload = _read_input(input_file)
    if not payload or set(payload) - {"writes", "deletes", "index_update"}:
        raise ValueError("invalid durable maintenance transaction")
    with _lock(root):
        state = _load_state(root, active=True)
        check_revision(state, base_revision)
        writes, deletes, selected = {}, [], set()
        inputs = []
        for kind in ("writes", "deletes"):
            values = payload.get(kind, [])
            if not isinstance(values, list):
                raise ValueError("invalid durable maintenance entries")
            inputs.extend((kind, value) for value in values)
        if "index_update" in payload:
            inputs.append(("index_update", payload["index_update"]))
        if not inputs:
            raise ValueError("empty durable maintenance transaction")
        for kind, value in inputs:
            fields = {"path", "base_sha256"} | ({"content"} if kind != "deletes" else set())
            if not isinstance(value, dict) or set(value) != fields:
                raise ValueError("invalid durable maintenance entry")
            relative = _valid_relative(root, value["path"])
            relative, target = _durable_relative_path(root, relative)
            if not relative.endswith(".md") or relative in selected:
                raise ValueError("maintenance requires unique Markdown paths")
            if (kind == "index_update") != relative.endswith("/INDEX.md"):
                raise ValueError("INDEX must use index_update")
            selected.add(relative)
            old = target.read_bytes() if target.is_file() else None
            base = value["base_sha256"]
            if base is not None and (not isinstance(base, str) or not re.fullmatch(r"[0-9a-f]{64}", base)):
                raise ValueError("invalid durable base_sha256")
            if base != _digest(old) or (kind in {"deletes", "index_update"} and old is None):
                raise ValueError("durable revision conflict")
            if kind == "deletes":
                deletes.append(relative)
            else:
                content = value["content"]
                if not isinstance(content, str):
                    raise ValueError("invalid durable content")
                encoded = content.encode("utf-8")
                limit = DURABLE_INDEX_HARD_MAX_BYTES if kind == "index_update" else EXPLICIT_DOCUMENT_MAX_BYTES
                if len(encoded) > limit:
                    raise ValueError("durable content exceeds retrieval limit")
                entry = parse_text(content, Path(relative))
                if kind != "index_update":
                    item = _document_get_item(root, relative, encoded, entry)
                    item["freshness"] = "MISSING"
                    item["freshness_detail"] = freshness_detail_budget_placeholder()
                    if _document_response_size({"ok": True, "documents": [item]}) > EXPLICIT_DOCUMENT_MAX_BYTES:
                        raise ValueError("durable content exceeds retrieval limit")
                writes[relative] = encoded
        for relative, encoded in writes.items():
            errors = _index_reference_errors(root, root / relative, parse_text(encoded.decode("utf-8"), Path(relative)).body,
                                            planned_paths=set(writes), deleted_paths=set(deletes))
            if errors:
                raise ValueError("invalid durable references: " + "; ".join(errors))
        backup = _apply_with_backup(root, writes, deletes, "document-maintain")
    return {"ok": True, "task_id": state["task_id"], "state_revision": state["revision"], "written": sorted(writes), "deleted": sorted(deletes), "backup": backup}


def _durable_relative_path(root: Path, path: str) -> tuple[str, Path]:
    relative = path.rstrip("/")
    _valid_relative(root, relative)
    if relative not in {".agent-memory", ".milestones"} and not relative.startswith((".agent-memory/", ".milestones/")):
        raise ValueError("durable path must be under .agent-memory or .milestones")
    return relative, _safe_without_final_symlink(root, relative)


def _index_reference_errors(root: Path, index: Path, body: str, *, planned_paths: set[str] | None = None, deleted_paths: set[str] | None = None) -> list[str]:
    """Validate explicit Markdown links without deriving a filesystem catalog."""
    errors: list[str] = []
    for target in re.findall(r"\[[^]]+\]\(([^)]+)\)", body):
        target = target.strip().strip("<>")
        if not target or target.startswith(("#", "http://", "https://", "mailto:")):
            continue
        relative_link = target.split("#", 1)[0]
        lexical = index.parent / relative_link
        final_symlink = lexical.is_symlink()
        candidate = lexical.resolve(strict=False)
        try:
            relative = candidate.relative_to(root.resolve(strict=True)).as_posix()
            _durable_relative_path(root, relative)
        except (OSError, ValueError):
            errors.append(f"{index.relative_to(root).as_posix()}: invalid link {target}")
            continue
        if relative in (deleted_paths or set()) or (relative not in (planned_paths or set()) and (final_symlink or not candidate.exists())):
            errors.append(f"{index.relative_to(root).as_posix()}: missing link target {relative}")
    return errors


def _catalog_index(root: Path, relative: str) -> tuple[dict[str, object], list[str]]:
    normalized = _valid_relative(root, relative.rstrip("/"))
    lexical_target = root.joinpath(*normalized.split("/"))
    index_relative = normalized if lexical_target.name == "INDEX.md" else f"{normalized}/INDEX.md"
    try:
        index = _safe_without_final_symlink(root, index_relative)
    except ValueError:
        index = root.joinpath(*index_relative.split("/"))
        return {"path": index_relative, "state": "MISSING"}, [f"{normalized}: missing INDEX.md"]
    if not index.is_file():
        return {"path": index_relative, "state": "MISSING"}, [f"{normalized}: missing INDEX.md"]
    size = index.stat().st_size
    if size > DURABLE_INDEX_HARD_MAX_BYTES:
        return {
            "path": index_relative,
            "state": "INDEX_OVERSIZED",
            "size_bytes": size,
            "hard_limit_bytes": DURABLE_INDEX_HARD_MAX_BYTES,
        }, [f"INDEX_OVERSIZED: {normalized}/INDEX.md exceeds {DURABLE_INDEX_HARD_MAX_BYTES} bytes"]
    try:
        parsed = parse(index)
    except (OSError, ValueError) as exc:
        return {"path": index.relative_to(root).as_posix(), "state": "INVALID"}, [str(exc)]
    errors = _index_reference_errors(root, index, parsed.body)
    heading = re.search(r"(?m)^#\s+(.+?)\s*$", parsed.body)
    return {
        "path": index_relative,
        "title": heading.group(1) if heading else index.parent.name,
        "metadata": {key: parsed.meta[key] for key in ("Status", "Revision") if key in parsed.meta},
        "map": parsed.body,
        "link_count": len(re.findall(r"\[[^]]+\]\(([^)]+)\)", parsed.body)),
        "state": "VALID" if not errors else "BROKEN_REFERENCES",
    }, errors


def catalog(root: Path, path: str | None = None) -> dict[str, object]:
    """Read canonical INDEX maps without recursively reconstructing the tree."""
    root = _repo_root(root)
    requested = path.rstrip("/") if isinstance(path, str) and path else None
    paths = [requested] if requested else [".agent-memory", ".milestones"]
    indexes: list[dict[str, object]] = []
    errors: list[str] = []
    for relative in paths:
        assert relative is not None
        item, item_errors = _catalog_index(root, relative)
        indexes.append(item)
        errors.extend(item_errors)
    result: dict[str, object] = {
        "ok": not errors,
        "path": requested,
        "discovery_only": True,
        "canonical_source": "INDEX.md",
        "recommended_index_bytes": DURABLE_INDEX_RECOMMENDED_BYTES,
        "hard_index_bytes": DURABLE_INDEX_HARD_MAX_BYTES,
        "indexes": indexes,
        "errors": errors[:8],
        "truncated": len(errors) > 8,
    }
    return result


def durable_index_check(root: Path, roots: list[str] | None = None) -> dict[str, object]:
    """Follow only explicit durable INDEX links for an on-demand integrity check."""
    root = _repo_root(root)
    pending = list(roots or [".agent-memory/INDEX.md", ".milestones/INDEX.md"])
    visited: set[str] = set()
    checked: list[str] = []
    errors: list[str] = []
    while pending:
        relative = pending.pop()
        try:
            normalized = _valid_relative(root, relative.rstrip("/"))
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if not normalized.endswith("/INDEX.md") and normalized != "INDEX.md":
            errors.append(f"{normalized}: durable integrity root is not INDEX.md")
            continue
        try:
            index = _safe_without_final_symlink(root, normalized)
        except ValueError as exc:
            errors.append(f"{normalized}: {exc}")
            continue
        if not index.is_file():
            errors.append(f"{normalized}: missing INDEX.md")
            continue
        canonical = normalized
        if canonical in visited:
            continue
        visited.add(canonical)
        checked.append(canonical)
        item, item_errors = _catalog_index(root, canonical)
        errors.extend(item_errors)
        if item.get("state") not in {"VALID", "BROKEN_REFERENCES"}:
            continue
        try:
            body = parse(index).body
        except (OSError, ValueError):
            continue
        for link in re.findall(r"\[[^]]+\]\(([^)]+)\)", body):
            link = link.strip().strip("<>")
            if not link or link.startswith(("#", "http://", "https://", "mailto:")):
                continue
            lexical = index.parent / link.split("#", 1)[0]
            if lexical.is_symlink():
                continue
            candidate = lexical.resolve(strict=False)
            try:
                child = candidate.relative_to(root.resolve(strict=True)).as_posix()
                _durable_relative_path(root, child)
            except (OSError, ValueError):
                continue
            if candidate.name == "INDEX.md" and candidate.is_file() and not candidate.is_symlink():
                pending.append(child)
            elif candidate.is_dir():
                directory_index = candidate / "INDEX.md"
                if directory_index.is_file() and not directory_index.is_symlink():
                    pending.append(directory_index.relative_to(root.resolve(strict=True)).as_posix())
    return {"ok": not errors, "checked": checked, "errors": errors}


def _document_get_item(root: Path, relative: str, raw: bytes, entry: object) -> dict[str, object]:
    """Build the exact public document-get item from parsed durable content."""
    freshness, detail = evidence_status(entry, root)
    provenance: object = entry.meta.get("Evidence")
    if entry.meta.get("Evidence") == "DURABLE_SOURCE_DESCRIPTORS":
        provenance = durable_descriptors(entry)
    return {
        "path": relative,
        "content_sha256": _digest(raw),
        "metadata": entry.meta,
        "body": entry.body,
        "freshness": freshness,
        "freshness_detail": detail,
        "provenance": provenance,
    }


def _document_response_size(response: dict[str, object]) -> int:
    """Size the exact JSON serialization returned by document-get."""
    return len(json.dumps(response, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def document_get(root: Path, paths: str | list[str]) -> dict[str, object]:
    """Retrieve only explicitly named durable documents in one bounded batch."""
    root = _repo_root(root)
    selected = [paths] if isinstance(paths, str) else paths
    if not isinstance(selected, list) or not 1 <= len(selected) <= 8 or len(set(selected)) != len(selected) or not all(isinstance(path, str) for path in selected):
        raise ValueError("document-get requires 1 to 8 unique paths")
    documents: list[dict[str, object]] = []
    for path in selected:
        relative = path.rstrip("/")
        _valid_relative(root, relative)
        if relative not in {".agent-memory", ".milestones"} and not relative.startswith((".agent-memory/", ".milestones/")):
            raise ValueError("durable path must be under .agent-memory or .milestones")
        try:
            target = _safe_without_final_symlink(root, relative)
        except ValueError as exc:
            raise ValueError("durable document not found") from exc
        if not target.is_file() or target.suffix.lower() != ".md":
            raise ValueError("durable document not found")
        if target.stat().st_size > EXPLICIT_DOCUMENT_MAX_BYTES:
            raise ValueError(f"durable document exceeds {EXPLICIT_DOCUMENT_MAX_BYTES} bytes")
        raw = target.read_bytes()
        try:
            entry = parse_text(raw.decode("utf-8"), target)
        except (UnicodeDecodeError, ValueError) as exc:
            raise ValueError("durable document is invalid") from exc
        documents.append(_document_get_item(root, relative, raw, entry))
        response = {"ok": True, "documents": documents}
        if _document_response_size(response) > EXPLICIT_DOCUMENT_MAX_BYTES:
            raise ValueError(f"document-get response exceeds {EXPLICIT_DOCUMENT_MAX_BYTES} bytes")
    return {"ok": True, "documents": documents}


def milestone_check(root: Path) -> dict[str, object]:
    return durable_index_check(root, [".milestones/INDEX.md"])
