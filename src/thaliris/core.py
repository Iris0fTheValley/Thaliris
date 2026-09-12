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
import unicodedata
import uuid

from .markdown import Entry, evidence_status, parse, parse_text
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


def _entry(title: str, body: str, *, status: str = "DRAFT", evidence: str = "NONE", confidence: str = "UNVERIFIED", applicability: str = "PROJECT", audience: list[str] | None = None, topics: list[str] | None = None, symbols: list[str] | None = None, kind: str | None = None, include_routing: bool = True) -> bytes:
    audience = ["all"] if audience is None else audience
    topics = [] if topics is None else topics
    symbols = [] if symbols is None else symbols
    for field, value, maximum in (
        ("title", title, 300),
        ("status", status, 128),
        ("evidence", evidence, 65_536),
        ("confidence", confidence, 128),
        ("applicability", applicability, 128),
    ):
        if not isinstance(value, str) or not value.strip() or len(value) > maximum or "\n" in value or "\r" in value:
            raise ValueError(f"invalid durable {field}")
    if not isinstance(body, str):
        raise ValueError("invalid durable body")
    if kind is not None and (not isinstance(kind, str) or not kind.strip() or len(kind) > 128 or "\n" in kind or "\r" in kind):
        raise ValueError("invalid durable kind")
    for field, values in (("audience", audience), ("topics", topics), ("symbols", symbols)):
        if not isinstance(values, list) or len(values) > 64 or any(
            not isinstance(item, str) or not item.strip() or len(item) > 256 or "\n" in item or "\r" in item
            for item in values
        ):
            raise ValueError(f"invalid durable {field}")
    optional = ""
    for key, value in (("Audience", audience), ("Topics", topics), ("Symbols", symbols)):
        if not include_routing:
            continue
        if value is not None:
            optional += f"{key}: {json.dumps(value, ensure_ascii=False)}\n"
    kind_line = f"Kind: {kind}\n" if kind is not None else ""
    rendered = f"---\nEvidence: {evidence}\nRevision: 1\nStatus: {status}\nApplicability: {applicability}\nConfidence: {confidence}\n{kind_line}{optional}---\n\n# {title}\n\n{body}\n"
    parse_text(rendered)
    return rendered.encode()


def _template_files() -> dict[str, bytes]:
    def template(title: str, body: str, **kwargs: object) -> bytes:
        kind = kwargs.pop("kind")
        return _entry(title, body, kind=kind, **kwargs)
    return {
        ".agent-memory/INDEX.md": template("Memory index", "- [Operator](operator.md)\n- [Prompt policy](prompt-policy.md)\n- [Project conventions](project-conventions.md)\n- [Decisions](decisions/INDEX.md)\n- [Lessons](lessons/INDEX.md)", audience=["all"], kind="MEMORY"),
        ".agent-memory/operator.md": template("Operator notes", "Unknown. Record only confirmed operating constraints.", kind="HARD_CONSTRAINT"),
        ".agent-memory/prompt-policy.md": template("Prompt policy", "Use explicit recall only. Retained memory is never automatically added to a Child handoff. Automatic compression is disabled.", audience=["controller"], kind="HARD_CONSTRAINT"),
        ".agent-memory/project-conventions.md": template("Project conventions", "Unknown. Add conventions only with evidence.", kind="HARD_CONSTRAINT"),
        ".agent-memory/decisions/INDEX.md": template("Decision index", "- [PD-001 decision template](PD-001.md)", kind="MEMORY"),
        ".agent-memory/decisions/PD-001.md": template("PD-001: decision template", "This is an unadopted template, not a project fact.\n\n## Decision\n\nUnknown.\n\n## Rationale\n\nUnknown.", kind="MEMORY"),
        ".agent-memory/lessons/INDEX.md": template("Lessons index", "- [L-001 lesson template](L-001.md)", kind="MEMORY"),
        ".agent-memory/lessons/L-001.md": template("L-001: lesson template", "This is an unadopted template, not a historical claim.\n\n## Failure mode\n\nUnknown.\n\n## Prevention\n\nUnknown.", kind="MEMORY"),
        ".milestones/INDEX.md": _entry("Milestone index", "- [M001-name](M001-name/INDEX.md)"),
        ".milestones/M001-name/INDEX.md": _entry("M001-name", "- [Scope](scope.md)\n- [Decisions](decisions.md)\n- [Progress](progress.md)\n- [Verification](verification.md)"),
        ".milestones/M001-name/scope.md": _entry("Scope", "Unknown."),
        ".milestones/M001-name/decisions.md": _entry("Decisions", "None."),
        ".milestones/M001-name/progress.md": _entry("Progress", "0%."),
        ".milestones/M001-name/verification.md": _entry("Verification", "Not run."),
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
    return [parse(path) for path in sorted(base.rglob("*.md"))] if base.exists() else []


def stale(root: Path) -> dict[str, object]:
    result = []
    for entry in entries(root):
        state, details = evidence_status(entry, root)
        result.append({"path": str(entry.path.relative_to(root)).replace("\\", "/"), "state": state, "detail": details, "metadata_confidence": entry.meta["Confidence"]})
    return {"ok": True, "entries": result, "not_fresh": sum(x["state"] in {"CHANGED", "MISSING"} for x in result)}


# Task state is a mechanical ledger. Models author record labels and interpret
# them; Core validates only shape, identity, references, bounds, and CAS.
_STATE_NAME = ".context/state.json"
_STATE_SCHEMA_VERSION = 6
_PACK_ROLES = {"controller", "investigator", "curator", "reasoning-specialist", "implementer", "reviewer"}
_EXECUTION_ROLES = _PACK_ROLES - {"controller"}
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
    return {"path": path, "state": "FILE", "identity": _digest(raw.read_bytes()), "mode": raw.stat().st_mode & 0o7777, "git_status": status}


def _surface_snapshot(root: Path) -> list[dict[str, object]]:
    proc = subprocess.run(["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"], cwd=root, capture_output=True, check=False)
    if proc.returncode:
        return []
    fields = proc.stdout.decode("utf-8", errors="surrogateescape").split("\0")
    result: list[dict[str, object]] = []
    index = 0
    while index < len(fields):
        item = fields[index]
        index += 1
        if not item:
            continue
        status, path = item[:2], item[3:].replace("\\", "/")
        if status[:1] in {"R", "C"} and index < len(fields):
            path = fields[index].replace("\\", "/")
            index += 1
        _valid_relative(root, path)
        result.append(_surface_identity(root, path, status))
    return sorted(result, key=lambda item: str(item["path"]))


def _surface_delta(root: Path, baseline: list[dict[str, object]]) -> dict[str, object]:
    before = {str(item["path"]): item for item in baseline}
    after = {str(item["path"]): item for item in _surface_snapshot(root)}
    paths = sorted(path for path in set(before) | set(after) if before.get(path) != after.get(path))
    return {"before": [before[path] for path in paths if path in before], "after": [after[path] for path in paths if path in after], "paths": paths}


def _git_head(root: Path) -> str | None:
    proc = subprocess.run(["git", "rev-parse", "--verify", "HEAD"], cwd=root, capture_output=True, text=True, check=False)
    value = proc.stdout.strip().lower()
    return value if proc.returncode == 0 and re.fullmatch(r"[0-9a-f]{40,64}", value) else None


def _record(value: object, source_ids: set[str], record_ids: set[str]) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != _RECORD_FIELDS:
        raise ValueError("invalid task record")
    identifier = _bounded_label(value.get("id"), "record id")
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
        "evidence_refs", "source_refs", "content_sha256", "supersedes", "task_id",
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
    supersedes = value.get("supersedes", [])
    if not isinstance(supersedes, list) or len(supersedes) > 64 or len(set(supersedes)) != len(supersedes) or value["id"] in supersedes or not all(isinstance(item, str) for item in supersedes):
        raise ValueError("invalid artifact supersession")
    if require_target:
        target = _safe(root, path)
        if target.is_symlink() or not target.is_file():
            raise ValueError("artifact path must name an existing regular file")
    return value


def _artifact_freshness(root: Path, artifact: dict[str, object]) -> str:
    try:
        target = _safe(root, str(artifact["path"]))
    except ValueError:
        return "MISSING"
    if target.is_symlink() or not target.is_file():
        return "MISSING"
    identity = artifact.get("content_sha256")
    if not isinstance(identity, str):
        return "UNKNOWN"
    return "FRESH" if _digest(target.read_bytes()) == identity else "CHANGED"


def _artifact_activity(artifacts: list[dict[str, object]]) -> set[str]:
    ids = {str(item["id"]) for item in artifacts}
    inactive: set[str] = set()
    for item in artifacts:
        targets = item.get("supersedes", [])
        if any(target not in ids for target in targets):
            raise ValueError("artifact supersession target is not registered")
        inactive.update(targets)
    return ids - inactive


def _verification_result(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("invalid verification observation")
    required = {"id", "kind", "outcome", "summary", "observed_by", "observed_at", "observed_at_revision", "candidate_identity", "observed_files", "result_hash"}
    if set(value) != required:
        raise ValueError("invalid verification observation")
    _bounded_label(value.get("id"), "verification id")
    _bounded_label(value.get("kind"), "verification kind")
    _bounded_label(value.get("outcome"), "verification outcome")
    _bounded_label(value.get("observed_by"), "verification observer")
    if not isinstance(value.get("summary"), str) or len(value["summary"]) > 4096:
        raise ValueError("invalid verification summary")
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
    _artifact_activity(artifacts)

    results = state.get("verification_results")
    if not isinstance(results, list) or len(results) > 256:
        raise ValueError("invalid verification observations")
    result_ids: set[str] = set()
    for result in results:
        _verification_result(result)
        if result["id"] in result_ids:
            raise ValueError("duplicate verification observation id")
        result_ids.add(str(result["id"]))

    baseline = state.get("task_surface_baseline")
    if not isinstance(baseline, list):
        raise ValueError("invalid task surface baseline")
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


def _normalize_new_record(value: object, *, producer: str, revision: int, known_sources: set[str], known_records: set[str]) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("invalid task record")
    allowed = {"id", "kind", "text", "producer", "revision", "source_refs", "evidence_refs", "status", "supersedes"}
    if set(value) - allowed:
        raise ValueError("invalid task record")
    record = {
        "id": value.get("id"),
        "kind": value.get("kind"),
        "text": value.get("text"),
        "producer": value.get("producer", producer),
        "revision": value.get("revision", revision),
        "source_refs": value.get("source_refs", value.get("evidence_refs", [])),
        "status": value.get("status", "RECORDED"),
        "supersedes": value.get("supersedes", []),
    }
    _record(record, known_sources, known_records)
    return record


def _controller_ack(state: dict[str, object], changed: list[str]) -> dict[str, object]:
    return {
        "ok": True,
        "task_id": state["task_id"],
        "revision": state["revision"],
        "status": state["status"],
        "changed": sorted(set(changed)),
    }


def task_start(root: Path, goal: str, milestone: str | None, input_file: str | None) -> dict[str, object]:
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
        state = _blank_state(root, goal, milestone)
        state["active_work"] = partial.get("active_work", [])
        state["pending_results"] = partial.get("pending_results", [])
        state["evidence_refs"] = partial.get("evidence_refs", [])
        source_ids = {str(item.get("id")) for item in state["evidence_refs"] if isinstance(item, dict)}
        known: set[str] = set()
        for item in partial.get("records", []):
            record = _normalize_new_record(item, producer="controller", revision=1, known_sources=source_ids, known_records=known)
            state["records"].append(record)
            known.add(str(record["id"]))
        _write_state(root, state)
    return _controller_ack(state, ["task"])


def task_update(root: Path, role: str, base_revision: int, input_file: str | None) -> dict[str, object]:
    root = _repo_root(root)
    if role != "controller" or type(base_revision) is not int:
        raise ValueError("only Controller may update the task ledger")
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
                record = _normalize_new_record(item, producer="controller", revision=base_revision + 1, known_sources=known_sources, known_records=known_records)
                state["records"].append(record)
                known_records.add(str(record["id"]))
            changed.append("records")
        for field in ("active_work", "pending_results", "current_milestone"):
            if field in partial:
                state[field] = partial[field]
                changed.append(field)
        state["revision"] = base_revision + 1
        _write_state(root, state)
    return _controller_ack(state, changed)


def task_show(root: Path) -> dict[str, object]:
    root = _repo_root(root)
    state = _load_state(root)
    return {"ok": True, "state": state, "task_surface_delta": _surface_delta(root, state["task_surface_baseline"])}


def _controller_status(state: dict[str, object]) -> dict[str, object]:
    """Return current routing mechanics without replaying the durable ledger."""
    goal = str(state["goal"])
    artifact_ids = [str(item["id"]) for item in state["artifact_refs"]]
    return {
        "ok": True,
        "schema_version": state["schema_version"],
        "role": "controller",
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
    return _controller_status(_load_state(root))


def task_artifact(root: Path, base_revision: int, artifact_id: str, path: str, summary: str, *, producer_role: str | None = None, registered_by: str = "controller", scope: str | None = None, evidence_refs: list[str] | None = None, supersedes: list[str] | None = None) -> dict[str, object]:
    root = _repo_root(root)
    if registered_by != "controller":
        raise ValueError("only Controller may register artifact pointers")
    draft: dict[str, object] = {"id": artifact_id, "path": path, "summary": summary}
    _artifact_ref(root, draft, require_target=True)
    with _lock(root):
        state = _load_state(root, active=True)
        if state["revision"] != base_revision:
            raise ValueError("task revision conflict")
        if artifact_id in {item["id"] for item in state["artifact_refs"]}:
            raise ValueError("artifact reference id already exists")
        known_sources = {str(item["id"]) for item in state["evidence_refs"]}
        refs = evidence_refs or []
        if any(ref not in known_sources for ref in refs):
            raise ValueError("artifact source reference is unknown")
        superseded = supersedes or []
        known_artifacts = {str(item["id"]) for item in state["artifact_refs"]}
        if any(item not in known_artifacts for item in superseded):
            raise ValueError("artifact supersession target is not registered")
        target = _safe(root, path)
        artifact: dict[str, object] = {
            "id": artifact_id,
            "path": path,
            "summary": summary,
            "producer": producer_role or "unspecified",
            "registered_by": "controller",
            "source_refs": refs,
            "supersedes": superseded,
            "task_id": state["task_id"],
            "revision": base_revision + 1,
            "content_sha256": _digest(target.read_bytes()),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        if scope is not None:
            artifact["scope"] = scope
        _artifact_ref(root, artifact, require_target=True)
        state["artifact_refs"].append(artifact)
        _artifact_activity(state["artifact_refs"])
        state["revision"] = base_revision + 1
        _write_state(root, state)
    return _controller_ack(state, ["artifact_refs"])


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
        if result_id in {item["id"] for item in state["verification_results"]}:
            raise ValueError("verification result id already exists")
        if source_refs is not None and source_paths is not None:
            raise ValueError("provide source refs or source paths, not both")
        known_sources = {str(item["id"]) for item in state["evidence_refs"]}
        if source_refs is not None and any(ref not in known_sources for ref in source_refs):
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
    return _controller_ack(state, ["verification_results"])


def task_close(root: Path, base_revision: int, *, expected_task_id: str | None = None) -> dict[str, object]:
    root = _repo_root(root)
    with _lock(root):
        state = _load_state(root, active=True)
        if state["revision"] != base_revision or (expected_task_id is not None and state["task_id"] != expected_task_id):
            raise ValueError("task revision conflict")
        state["status"] = "DONE"
        state["revision"] = base_revision + 1
        _write_state(root, state)
    return _controller_ack(state, ["status"])


def task_promote(root: Path, role: str, base_revision: int, input_file: str | None) -> dict[str, object]:
    """Persist exactly the model-selected records without epistemic adjudication."""
    root = _repo_root(root)
    if role != "controller":
        raise ValueError("only the Controller may promote durable records")
    payload = _read_input(input_file)
    if set(payload) != {"records"} or not isinstance(payload["records"], list) or not payload["records"]:
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
        for value in payload["records"]:
            if not isinstance(value, dict):
                raise ValueError("invalid promotion record")
            allowed = {"id", "kind", "title", "text", "source_refs", "status", "audience", "topics", "symbols", "applicability", "confidence"}
            if set(value) - allowed:
                raise ValueError("invalid promotion record")
            identifier = _bounded_label(value.get("id"), "promotion id")
            title = value.get("title", identifier)
            text = value.get("text")
            if not isinstance(title, str) or not title.strip() or len(title) > 300 or "\n" in title or "\r" in title or not isinstance(text, str) or not text.strip() or len(text) > 16_384:
                raise ValueError("invalid promotion record")
            refs = value.get("source_refs", [])
            if not isinstance(refs, list) or len(refs) > 64 or len(set(refs)) != len(refs) or any(not isinstance(ref, str) or ref not in known_refs for ref in refs):
                raise ValueError("promotion source reference is unknown")
            descriptors: list[dict[str, object]] = []
            for ref in refs:
                if ref in sources and ref in artifacts:
                    raise ValueError("promotion source reference is ambiguous")
                if ref in artifacts:
                    artifact = artifacts[ref]
                    descriptors.append({
                        "type": "artifact",
                        "artifact_id": artifact["id"],
                        "path": artifact["path"],
                        "content_sha256": artifact["content_sha256"],
                        "producer": artifact["producer"],
                        "task_id": artifact["task_id"],
                        "revision": artifact["revision"],
                    })
                else:
                    source = sources[ref]
                    descriptor = {
                        "type": "source",
                        "source_id": source["id"],
                        "kind": source["kind"],
                        "locator": source["locator"],
                    }
                    if "confidence" in source:
                        descriptor["confidence"] = source["confidence"]
                    descriptors.append(descriptor)
            relative = f".agent-memory/promoted/{identifier}.md"
            if _safe(root, relative).exists():
                raise ValueError("promotion refuses to overwrite an existing durable target")
            kind = value.get("kind", "record")
            status = value.get("status", "ACTIVE")
            confidence = value.get("confidence", "MODEL_AUTHORED")
            applicability = value.get("applicability", "PROJECT")
            audience = value.get("audience", ["all"])
            topics = value.get("topics", [])
            symbols = value.get("symbols", [])
            durable_body = text
            if descriptors:
                durable_body += "\n\n## Durable Source Descriptors\n\n```json\n" + json.dumps(descriptors, ensure_ascii=False, sort_keys=True, indent=2) + "\n```"
            rendered = _entry(
                title,
                durable_body,
                status=status,
                evidence="DURABLE_SOURCE_DESCRIPTORS" if descriptors else "NONE",
                confidence=confidence,
                applicability=applicability,
                audience=audience,
                topics=topics,
                symbols=symbols,
                kind=kind,
            )
            parse_text(rendered.decode("utf-8"), Path(relative))
            writes[relative] = rendered
            promoted.append(relative)
        backup = _apply_with_backup(root, writes, [], "task-promote")
    return {"ok": True, "task_id": state["task_id"], "state_revision": state["revision"], "promoted": promoted, "backup": backup}


def _tokens(text: str) -> set[str]:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return {token for token in re.findall(r"[\w.-]+", normalized) if len(token) > 1}


def _memory_candidates(root: Path, query: str) -> list[dict[str, object]]:
    wanted = _tokens(query)
    candidates: list[dict[str, object]] = []
    for entry in entries(root):
        relative = entry.path.relative_to(root).as_posix()
        searchable = " ".join((
            relative,
            entry.path.stem,
            entry.body,
            json.dumps(entry.meta.get("Topics", []), ensure_ascii=False),
            json.dumps(entry.meta.get("Symbols", []), ensure_ascii=False),
        ))
        score = len(wanted & _tokens(searchable)) if wanted else 0
        if wanted and score == 0:
            continue
        freshness, detail = evidence_status(entry, root)
        candidates.append({
            "path": relative,
            "title": entry.path.stem,
            "status": entry.meta.get("Status"),
            "kind": entry.meta.get("Kind"),
            "confidence": entry.meta.get("Confidence"),
            "audience": entry.meta.get("Audience"),
            "topics": entry.meta.get("Topics", []),
            "symbols": entry.meta.get("Symbols", []),
            "applicability": entry.meta.get("Applicability"),
            "freshness": freshness,
            "freshness_detail": detail,
            "score": score,
        })
    return sorted(candidates, key=lambda item: (-int(item["score"]), str(item["path"])))


def recall(root: Path, query: str, role: str) -> dict[str, object]:
    """Explicit memory search. Metadata is a search hint, never a permission gate."""
    if role not in _PACK_ROLES:
        raise ValueError("invalid role")
    root = _repo_root(root)
    return {
        "ok": True,
        "schema_version": 2,
        "role_hint": role,
        "query": query,
        "candidates": _memory_candidates(root, query),
    }


def memory_get(root: Path, path: str) -> dict[str, object]:
    """Explicitly retrieve one memory document by its repo-relative address."""
    root = _repo_root(root)
    _valid_relative(root, path)
    if not path.startswith(".agent-memory/"):
        raise ValueError("memory path must be under .agent-memory")
    target = _safe(root, path)
    if target.is_symlink() or not target.is_file():
        raise ValueError("memory entry not found")
    entry = parse(target)
    freshness, detail = evidence_status(entry, root)
    return {
        "ok": True,
        "path": path,
        "title": entry.path.stem,
        "metadata": entry.meta,
        "body": entry.body,
        "freshness": freshness,
        "freshness_detail": detail,
    }


def prepare(root: Path, task: str | None, role: str) -> dict[str, object]:
    """Return Controller state or a context-free execution-role marker.

    Execution roles receive their task-specific information only in the native
    Controller handoff. This command never rebuilds task, memory, milestone,
    artifact, finding, or review context for a child.
    """
    if role not in _PACK_ROLES:
        raise ValueError("invalid role")
    root = _repo_root(root)
    if role == "controller":
        if task is None:
            return task_status(root)
        return {
            "ok": True,
            "schema_version": _STATE_SCHEMA_VERSION,
            "role": "controller",
            "Task": {"id": None, "goal": task, "status": "UNBOUND", "revision": None, "milestone": None},
        }
    return {
        "ok": True,
        "schema_version": _STATE_SCHEMA_VERSION,
        "role": role,
        "task_specific_context": "CONTROLLER_HANDOFF_ONLY",
    }


def milestone_check(root: Path) -> dict[str, object]:
    index = root / ".milestones" / "INDEX.md"; errors: list[str] = []; checked: list[str] = []
    try: top = parse(index)
    except (ValueError, OSError) as exc: return {"ok": False, "errors": [str(exc)]}
    links = re.findall(r"\[[^]]+\]\(([^)]+/INDEX\.md)\)", top.body)
    if not links: errors.append("milestone index has no directory INDEX links")
    required = {"INDEX.md": "# ", "scope.md": "# Scope", "decisions.md": "# Decisions", "progress.md": "# Progress", "verification.md": "# Verification"}
    for link in links:
        try: directory = _safe(index.parent, str(Path(link).parent))
        except ValueError: errors.append(f"path escapes milestones: {link}"); continue
        for name, heading in required.items():
            target = _safe(directory, name)
            if not target.is_file(): errors.append(f"{link}: missing {name}"); continue
            try:
                item = parse(target)
                if heading not in item.body: errors.append(f"{link}: {name} missing required heading")
            except ValueError as exc: errors.append(str(exc))
        checked.append(link)
    return {"ok": not errors, "checked": checked, "errors": errors}
