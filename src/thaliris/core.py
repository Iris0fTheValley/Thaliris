"""Git-native Markdown operations; adapters never decide correctness."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import uuid

from .markdown import Entry, durable_descriptors, evidence_status, freshness_detail_budget_placeholder, parse, parse_text
from .models import ContextConfig

IGNORE_START = "# thaliris:begin"
IGNORE_END = "# thaliris:end"
IGNORE_RULES = (".context/backups/", ".context/state.json", ".context/context.lock")

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


def _repo_root(root: Path) -> Path:
    proc = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=root, capture_output=True, text=True, check=False)
    if proc.returncode or not proc.stdout.strip():
        raise ValueError("init requires an existing git repository")
    actual = Path(proc.stdout.strip()).resolve()
    if root.resolve() != actual:
        raise ValueError("--root must be the git repository root")
    return actual


@contextmanager
def _lock(root: Path):
    """A non-blocking stdlib lock: concurrent mutations fail closed."""
    path = _safe(root, ".context/context.lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    acquired = False
    try:
        handle.seek(0); handle.write(b"0"); handle.flush()
        if os.name == "nt":
            import msvcrt
            try:
                handle.seek(0); msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1); acquired = True
            except OSError as exc: raise ValueError("context operation already in progress") from exc
        else:
            import fcntl
            try: fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB); acquired = True
            except OSError as exc: raise ValueError("context operation already in progress") from exc
        yield
    finally:
        try:
            if acquired and os.name == "nt":
                import msvcrt
                handle.seek(0); msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
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


def rollback(root: Path, backup_id: str) -> dict[str, object]:
    root = _repo_root(root)
    if not re.fullmatch(r"[0-9TZ-]+-[0-9a-f]{8}", backup_id): raise ValueError("invalid backup id")
    with _lock(root):
        path = _safe(root, f".context/backups/{backup_id}.json")
        if not path.is_file(): raise ValueError("backup not found")
        data = json.loads(path.read_text(encoding="utf-8")); guarded = []; applied = []
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
_STATE_SCHEMA_VERSION = 7
ROUTING_STATE_MAX_BYTES = 8 * 1024
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


def _state_path(root: Path) -> Path:
    return _safe(root, _STATE_NAME)


def _state_ignored(root: Path) -> bool:
    return subprocess.run(["git", "check-ignore", "-q", "--", _STATE_NAME], cwd=root, check=False).returncode == 0


def _check_json(value: object) -> None:
    if isinstance(value, str):
        if len(value) > 16_384 or any(ord(char) < 32 and char not in "\n\t" for char in value):
            raise ValueError("state contains control characters or oversized text")
    elif isinstance(value, list):
        if len(value) > 512:
            raise ValueError("state list exceeds limit")
        for item in value:
            _check_json(item)
    elif isinstance(value, dict):
        if len(value) > 64:
            raise ValueError("state object exceeds limit")
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("state keys must be strings")
            _check_json(item)
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
        proc = subprocess.run(["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"], cwd=root, capture_output=True, check=False)
    except (OSError, subprocess.SubprocessError):
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
    proc = subprocess.run(["git", "rev-parse", "--verify", "HEAD"], cwd=root, capture_output=True, text=True, check=False)
    value = proc.stdout.strip().lower()
    return value if proc.returncode == 0 and re.fullmatch(r"[0-9a-f]{40,64}", value) else None


def _record(value: object, source_ids: set[str], record_ids: set[str]) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != _RECORD_FIELDS:
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


def _evidence_ref(value: object, ids: set[str]) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("invalid source reference")
    allowed = {"id", "kind", "locator", "summary", "confidence", "source_refs"}
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


def _verification_result(value: object, source_ids: set[str] | None = None) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("invalid verification observation")
    required = {"id", "kind", "outcome", "summary", "source_refs", "observed_by", "observed_at", "observed_at_revision", "candidate_identity", "observed_files", "result_hash"}
    if set(value) != required:
        raise ValueError("invalid verification observation")
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


def _validate_state(root: Path, state: object) -> dict[str, object]:
    _check_json(state)
    if not isinstance(state, dict):
        raise ValueError("invalid task state schema")
    if set(state) != _STATE_FIELDS or state.get("schema_version") != _STATE_SCHEMA_VERSION:
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
        if not isinstance(values, list) or len(values) > 64 or not all(isinstance(item, str) and item.strip() and len(item) <= 4096 for item in values):
            raise ValueError(f"invalid {field}")
    routing_bytes = len(json.dumps(
        {"active_work": state["active_work"], "pending_results": state["pending_results"]},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8"))
    if routing_bytes > ROUTING_STATE_MAX_BYTES:
        raise ValueError(
            f"Active Work + Pending Results exceed {ROUTING_STATE_MAX_BYTES} UTF-8 bytes; "
            "store long content as a Record or Artifact"
        )

    sources = state.get("evidence_refs")
    if not isinstance(sources, list) or len(sources) > 512:
        raise ValueError("invalid source references")
    source_ids: set[str] = set()
    for source in sources:
        _evidence_ref(source, source_ids)
        source_ids.add(str(source["id"]))
    if any(any(ref not in source_ids for ref in source.get("source_refs", [])) for source in sources):
        raise ValueError("source reference points to an unknown source")

    records = state.get("records")
    if not isinstance(records, list) or len(records) > 512:
        raise ValueError("invalid task records")
    record_ids: set[str] = set()
    for item in records:
        _record(item, source_ids, record_ids)
        record_ids.add(str(item["id"]))

    artifacts = state.get("artifact_refs")
    if not isinstance(artifacts, list) or len(artifacts) > 256:
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
    if not isinstance(results, list) or len(results) > 256:
        raise ValueError("invalid verification observations")
    result_ids: set[str] = set()
    for result in results:
        _verification_result(result, source_ids)
        if result["id"] in result_ids:
            raise ValueError("duplicate verification observation id")
        result_ids.add(str(result["id"]))

    object_groups = (source_ids, record_ids, artifact_ids, result_ids)
    if sum(len(group) for group in object_groups) != len(set().union(*object_groups)):
        raise ValueError("task object id collision")

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
    return state


def _state_payload(root: Path, state: dict[str, object]) -> bytes:
    state = _validate_state(root, state)
    payload = (json.dumps(state, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    if len(payload) > 512 * 1024:
        raise ValueError("task state exceeds 512 KiB")
    return payload


def _write_state(root: Path, state: dict[str, object]) -> None:
    _atomic_write(_state_path(root), _state_payload(root, state))


def _load_state(root: Path, *, active: bool = False) -> dict[str, object]:
    path = _state_path(root)
    if not path.is_file():
        raise ValueError("no current task state")
    if path.stat().st_size > 512 * 1024:
        raise ValueError("task state exceeds 512 KiB")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("invalid task state JSON") from exc
    state = _validate_state(root, raw)
    if active and state["status"] != "ACTIVE":
        raise ValueError("current task is not ACTIVE")
    return state


def _task_object_ids(state: dict[str, object]) -> set[str]:
    """Return the single task-wide identity set for addressable objects."""
    return {
        str(item["id"])
        for field in ("evidence_refs", "records", "artifact_refs", "verification_results")
        for item in state[field]
    }


def _read_input(value: str | None) -> dict[str, object]:
    if value is None:
        return {}
    source = sys.stdin.read() if value == "-" else Path(value).read_text(encoding="utf-8")
    raw = json.loads(source)
    _check_json(raw)
    if not isinstance(raw, dict):
        raise ValueError("task input must be a JSON object")
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


def task_start(root: Path, goal: str, milestone: str | None, input_file: str | None, *, actor: str = "unspecified") -> dict[str, object]:
    root = _repo_root(root)
    if not _state_ignored(root):
        raise ValueError("task state is not ignored; run context init first")
    if not isinstance(goal, str) or not goal.strip() or len(goal) > 16_384:
        raise ValueError("goal must not be empty")
    partial = _read_input(input_file)
    allowed = {"records", "active_work", "pending_results", "evidence_refs"}
    if set(partial) - allowed:
        raise ValueError("task-start accepts only mechanical ledger fields")
    with _lock(root):
        path = _state_path(root)
        if path.is_file() and _load_state(root)["status"] == "ACTIVE":
            raise ValueError("an ACTIVE task already exists")
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
        _write_state(root, state)
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
        if state["revision"] != base_revision:
            raise ValueError("task revision conflict")
        changed: list[str] = []
        if "evidence_refs" in partial:
            additions = partial["evidence_refs"]
            if not isinstance(additions, list):
                raise ValueError("evidence_refs must be append-only additions")
            known_source_ids = {str(item["id"]) for item in state["evidence_refs"]}
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
            known_sources = {str(item["id"]) for item in state["evidence_refs"]}
            known_records = {str(item["id"]) for item in state["records"]}
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
    )
    matches = [(kind, item) for kind, values in collections for item in values if item.get("id") == identifier]
    if len(matches) != 1:
        raise ValueError("task object not found")
    kind, item = matches[0]
    return {"ok": True, "task_id": state["task_id"], "revision": state["revision"], "object_type": kind, "object": item}


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


def _task_status_packet(state: dict[str, object]) -> dict[str, object]:
    """Return current routing mechanics without replaying the durable ledger."""
    goal = str(state["goal"])
    artifact_ids = [str(item["id"]) for item in state["artifact_refs"]]
    return {
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
            "records": len(state["records"]),
            "sources": len(state["evidence_refs"]),
            "artifacts": len(state["artifact_refs"]),
            "verification_observations": len(state["verification_results"]),
        },
        "Recent Artifact IDs": artifact_ids[-8:],
        "Active Artifact Count": len(_artifact_activity(state["artifact_refs"])),
    }


def task_status(root: Path) -> dict[str, object]:
    root = _repo_root(root)
    state = _load_state(root)
    return _task_status_packet(state)


def task_artifact(root: Path, base_revision: int, artifact_id: str, path: str, summary: str, *, producer: str | None = None, registered_by: str = "unspecified", scope: str | None = None, evidence_refs: list[str] | None = None, supersedes: list[str] | None = None) -> dict[str, object]:
    root = _repo_root(root)
    if not isinstance(registered_by, str) or not registered_by:
        raise ValueError("invalid artifact registrar")
    draft: dict[str, object] = {"id": artifact_id, "path": path, "summary": summary}
    _artifact_ref(root, draft, require_target=True)
    with _lock(root):
        state = _load_state(root, active=True)
        if state["revision"] != base_revision:
            raise ValueError("task revision conflict")
        if artifact_id in _task_object_ids(state):
            raise ValueError("task object id already exists")
        known_sources = {str(item["id"]) for item in state["evidence_refs"]}
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
        if state["revision"] != base_revision:
            raise ValueError("task revision conflict")
        if result_id in _task_object_ids(state):
            raise ValueError("task object id already exists")
        if source_refs is not None and source_paths is not None:
            raise ValueError("provide source refs or source paths, not both")
        known_sources = {str(item["id"]) for item in state["evidence_refs"]}
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


def task_close(root: Path, base_revision: int, *, expected_task_id: str | None = None) -> dict[str, object]:
    root = _repo_root(root)
    with _lock(root):
        state = _load_state(root, active=True)
        if state["revision"] != base_revision or (expected_task_id is not None and state["task_id"] != expected_task_id):
            raise ValueError("task revision conflict")
        state["status"] = "DONE"
        state["revision"] = base_revision + 1
        _write_state(root, state)
    return _task_ack(state, ["status"])


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
        if state["revision"] != base_revision:
            raise ValueError("task revision conflict")
        sources = {str(item["id"]): item for item in state["evidence_refs"]}
        artifacts = {str(item["id"]): item for item in state["artifact_refs"]}
        known_refs = set(sources) | set(artifacts)
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
                if source is None:
                    raise ValueError("artifact provenance source reference is unknown")
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


def _durable_relative_path(root: Path, path: str) -> tuple[str, Path]:
    relative = path.rstrip("/")
    _valid_relative(root, relative)
    if relative not in {".agent-memory", ".milestones"} and not relative.startswith((".agent-memory/", ".milestones/")):
        raise ValueError("durable path must be under .agent-memory or .milestones")
    return relative, _safe_without_final_symlink(root, relative)


def _index_reference_errors(root: Path, index: Path, body: str, *, planned_paths: set[str] | None = None) -> list[str]:
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
        if relative not in (planned_paths or set()) and (final_symlink or not candidate.exists()):
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
