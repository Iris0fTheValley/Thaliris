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

from .markdown import Entry, evidence_status, parse
from .models import ContextConfig

MANAGED_START = "<!-- codex-context:begin -->"
MANAGED_END = "<!-- codex-context:end -->"
IGNORE_START = "# codex-context:begin"
IGNORE_END = "# codex-context:end"
IGNORE_RULES = (".context/backups/", ".context/state.json", ".context/context.lock")
MANAGED = f"""{MANAGED_START}
## Codex context

Controller: Sol mid; only Controller spawns (default concurrency: 1), and children MUST NOT delegate. Sol high reasons, Luna scouts/verifies, Terra implements/reviews; use the Microtask fast path. Route memory and milestones through their INDEX files. Use `context task-*` for concise, evidence-referenced handoffs—never transcripts or raw tool/test output. Current source/Git/tests are the correctness core; adapters MUST fall back to native behavior.
{MANAGED_END}
"""


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


def _entry(title: str, body: str, *, status: str = "DRAFT", evidence: str = "NONE", confidence: str = "UNVERIFIED", applicability: str = "PROJECT", audience: list[str] | None = None, topics: list[str] | None = None, symbols: list[str] | None = None, kind: str | None = None) -> bytes:
    audience = ["all"] if audience is None else audience
    topics = [] if topics is None else topics
    symbols = [] if symbols is None else symbols
    optional = ""
    for key, value in (("Audience", audience), ("Topics", topics), ("Symbols", symbols)):
        if value is not None:
            optional += f"{key}: {json.dumps(value, ensure_ascii=False)}\n"
    kind_line = f"Kind: {kind}\n" if kind is not None else ""
    return (f"---\nEvidence: {evidence}\nRevision: 1\nStatus: {status}\nApplicability: {applicability}\nConfidence: {confidence}\n{kind_line}{optional}---\n\n# {title}\n\n{body}\n").encode()


def _template_files() -> dict[str, bytes]:
    return {
        ".agent-memory/INDEX.md": _entry("Memory index", "- [Operator](operator.md)\n- [Prompt policy](prompt-policy.md)\n- [Project conventions](project-conventions.md)\n- [Decisions](decisions/INDEX.md)\n- [Lessons](lessons/INDEX.md)", audience=["all"], kind="MEMORY"),
        ".agent-memory/operator.md": _entry("Operator notes", "Unknown. Record only confirmed operating constraints.", kind="HARD_CONSTRAINT"),
        ".agent-memory/prompt-policy.md": _entry("Prompt policy", "Use manual recall only. Automatic injection and compression are disabled.", audience=["controller"], kind="HARD_CONSTRAINT"),
        ".agent-memory/project-conventions.md": _entry("Project conventions", "Unknown. Add conventions only with evidence.", kind="HARD_CONSTRAINT"),
        ".agent-memory/decisions/INDEX.md": _entry("Decision index", "Link each project decision entry here.", kind="MEMORY"),
        ".agent-memory/decisions/PD-001.md": _entry("PD-001: decision template", "This is an unadopted template, not a project fact.\n\n## Decision\n\nUnknown.\n\n## Rationale\n\nUnknown.", kind="MEMORY"),
        ".agent-memory/lessons/INDEX.md": _entry("Lessons index", "- [L-001 lesson template](L-001.md)", kind="MEMORY"),
        ".agent-memory/lessons/L-001.md": _entry("L-001: lesson template", "This is an unadopted template, not a historical claim.\n\n## Failure mode\n\nUnknown.\n\n## Prevention\n\nUnknown.", kind="MEMORY"),
        ".milestones/INDEX.md": _entry("Milestone index", "- [M001-name](M001-name/INDEX.md)"),
        ".milestones/M001-name/INDEX.md": _entry("M001-name", "- [Scope](scope.md)\n- [Decisions](decisions.md)\n- [Progress](progress.md)\n- [Verification](verification.md)"),
        ".milestones/M001-name/scope.md": _entry("Scope", "Unknown."),
        ".milestones/M001-name/decisions.md": _entry("Decisions", "None."),
        ".milestones/M001-name/progress.md": _entry("Progress", "0%."),
        ".milestones/M001-name/verification.md": _entry("Verification", "Not run."),
    }


def _managed_agents(current: str) -> str:
    begins, ends = current.count(MANAGED_START), current.count(MANAGED_END)
    if begins != ends or begins > 1: raise ValueError("AGENTS.md has duplicate or damaged codex-context markers")
    newline = "\r\n" if "\r\n" in current else "\n"
    block = MANAGED.replace("\n", newline)
    if begins == 0:
        if not current: return block
        separator = "" if current.endswith(("\n", "\r")) else newline
        return current + separator + block
    start, end = current.index(MANAGED_START), current.index(MANAGED_END) + len(MANAGED_END)
    suffix = current[end:]
    if suffix.startswith("\r\n"): suffix = suffix[2:]
    elif suffix.startswith("\n"): suffix = suffix[1:]
    return current[:start] + block + suffix


def _managed_gitignore(current: str) -> str:
    begins, ends = current.count(IGNORE_START), current.count(IGNORE_END)
    if begins != ends or begins > 1: raise ValueError(".gitignore has duplicate or damaged codex-context markers")
    if begins == 0 and set(IGNORE_RULES) <= set(current.splitlines()): return current
    newline = "\r\n" if "\r\n" in current else "\n"
    block = newline.join((IGNORE_START, *IGNORE_RULES, IGNORE_END)) + newline
    if begins == 0:
        separator = "" if not current or current.endswith(("\n", "\r")) else newline
        return current + separator + block
    start, end = current.index(IGNORE_START), current.index(IGNORE_END) + len(IGNORE_END)
    suffix = current[end:]
    if suffix.startswith("\r\n"): suffix = suffix[2:]
    elif suffix.startswith("\n"): suffix = suffix[1:]
    return current[:start] + block + suffix


def init(root: Path) -> dict[str, object]:
    root = _repo_root(root)
    # Validate before creating even the operational lock file: corrupt markers
    # must fail without a tool-owned filesystem mutation.
    pre_agents = _safe(root, "AGENTS.md")
    _managed_agents(pre_agents.read_bytes().decode("utf-8") if pre_agents.exists() else "")
    pre_ignore = _safe(root, ".gitignore")
    _managed_gitignore(pre_ignore.read_bytes().decode("utf-8") if pre_ignore.exists() else "")
    with _lock(root):
        files = {path: content for path, content in _template_files().items() if not _safe(root, path).exists()}
        agents = _safe(root, "AGENTS.md"); current = agents.read_bytes().decode("utf-8") if agents.exists() else ""
        rendered = _managed_agents(current)
        if current != rendered: files["AGENTS.md"] = rendered.encode()
        ignore = _safe(root, ".gitignore"); current_ignore = ignore.read_bytes().decode("utf-8") if ignore.exists() else ""
        rendered_ignore = _managed_gitignore(current_ignore)
        if current_ignore != rendered_ignore: files[".gitignore"] = rendered_ignore.encode()
        if not _safe(root, ".context/config.json").exists(): files[".context/config.json"] = ContextConfig().write(root)
        if not files: return {"ok": True, "changed": False, "backup": None}
        return {"ok": True, "changed": True, "backup": _apply_with_backup(root, files, [], "init"), "files": sorted(files)}


def migrate(root: Path) -> dict[str, object]:
    result = init(root); result["migration"] = "v1"; return result


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


def uninstall(root: Path) -> dict[str, object]:
    root = _repo_root(root)
    with _lock(root):
        writes: dict[str, bytes] = {}; deletes: list[str] = []; kept: list[str] = []
        agents = _safe(root, "AGENTS.md")
        if agents.is_file():
            current = agents.read_bytes().decode("utf-8")
            if MANAGED_START in current and MANAGED_END in current:
                start, end = current.index(MANAGED_START), current.index(MANAGED_END) + len(MANAGED_END)
                suffix = current[end:]
                if suffix.startswith("\r\n"): suffix = suffix[2:]
                elif suffix.startswith("\n"): suffix = suffix[1:]
                stripped = current[:start] + suffix
                if stripped: writes["AGENTS.md"] = stripped.encode()
                else: deletes.append("AGENTS.md")
            elif MANAGED_START in current or MANAGED_END in current: kept.append("AGENTS.md")
        ignore = _safe(root, ".gitignore")
        if ignore.is_file():
            current = ignore.read_bytes().decode("utf-8")
            if IGNORE_START in current and IGNORE_END in current:
                start, end = current.index(IGNORE_START), current.index(IGNORE_END) + len(IGNORE_END)
                suffix = current[end:]
                if suffix.startswith("\r\n"): suffix = suffix[2:]
                elif suffix.startswith("\n"): suffix = suffix[1:]
                stripped = current[:start] + suffix
                if stripped: writes[".gitignore"] = stripped.encode()
                else: deletes.append(".gitignore")
            elif IGNORE_START in current or IGNORE_END in current: kept.append(".gitignore")
        expected = _template_files() | {".context/config.json": ContextConfig().write(root)}
        for relative, template in expected.items():
            target = _safe(root, relative)
            if not target.is_file(): continue
            if _digest(target.read_bytes()) == _digest(template): deletes.append(relative)
            else: kept.append(relative)
        if not writes and not deletes: return {"ok": True, "changed": False, "kept": sorted(set(kept)), "backup": None}
        return {"ok": True, "changed": True, "kept": sorted(set(kept)), "backup": _apply_with_backup(root, writes, deletes, "uninstall"), "deleted": sorted(deletes)}


def entries(root: Path) -> list[Entry]:
    base = root / ".agent-memory"
    return [parse(path) for path in sorted(base.rglob("*.md"))] if base.exists() else []


def stale(root: Path) -> dict[str, object]:
    result = []
    for entry in entries(root):
        state, details = evidence_status(entry, root)
        result.append({"path": str(entry.path.relative_to(root)).replace("\\", "/"), "state": state, "stale": details, "captured_confidence": entry.meta["Confidence"], "effective_confidence": "STALE" if state == "STALE" else entry.meta["Confidence"]})
    return {"ok": True, "entries": result, "stale": sum(x["state"] == "STALE" for x in result)}


# The current task is intentionally a small, private operational snapshot.  It
# is not a second memory store and is never included in the backup mechanism.
_STATE_NAME = ".context/state.json"
_STATE_FIELDS = {
    "schema_version", "revision", "task_id", "status", "goal", "current_milestone",
    "confirmed_facts", "supported_evidence", "unknowns", "contradictions", "constraints",
    "decisions", "relevant_files", "relevant_symbols", "modification_boundary",
    "changed_surface", "evidence_refs", "verification_target", "architectural_intent",
    "investigation_findings", "review_findings",
}
_LIST_STATEMENTS = {"confirmed_facts", "supported_evidence", "unknowns", "contradictions", "constraints", "decisions"}
_ROLE_FIELDS = {
    "controller": _STATE_FIELDS - {"schema_version", "revision", "task_id", "status", "goal"},
    "luna": {"investigation_findings", "relevant_files", "relevant_symbols", "evidence_refs", "verification_target"},
    "sol-high": {"relevant_files", "relevant_symbols", "evidence_refs", "verification_target", "architectural_intent"},
    "terra-implementer": {"changed_surface", "evidence_refs"},
    "terra-reviewer": {"review_findings", "evidence_refs"},
}
_PACK_ROLES = {"sol-high", "luna", "terra-implementer", "terra-reviewer"}


def _state_path(root: Path) -> Path:
    return _safe(root, _STATE_NAME)


def _state_ignored(root: Path) -> bool:
    return subprocess.run(["git", "check-ignore", "-q", "--", _STATE_NAME], cwd=root, check=False).returncode == 0


def _bad_text(value: str) -> bool:
    return len(value) > 2000 or any(ord(char) < 32 or char in "\r\n" for char in value)


def _check_json(value: object) -> None:
    if isinstance(value, str):
        if _bad_text(value): raise ValueError("state contains control characters or oversized text")
    elif isinstance(value, list):
        if len(value) > 512: raise ValueError("state list exceeds limit")
        for item in value: _check_json(item)
    elif isinstance(value, dict):
        if len(value) > 64: raise ValueError("state object exceeds limit")
        for key, item in value.items():
            if not isinstance(key, str) or key in {"transcript", "raw", "log", "stdout", "stderr"}:
                raise ValueError("state field is prohibited")
            _check_json(item)
    elif value is not None and type(value) not in {int, bool, float}:
        raise ValueError("state contains unsupported JSON value")


def _statement(value: object, ids: set[str]) -> None:
    if not isinstance(value, dict) or set(value) != {"text", "evidence_refs"} or not isinstance(value["text"], str) or len(value["text"]) > 1000 or not isinstance(value["evidence_refs"], list) or not all(isinstance(ref, str) and ref in ids for ref in value["evidence_refs"]):
        raise ValueError("invalid statement")


def _finding(value: object, ids: set[str]) -> None:
    if not isinstance(value, dict) or set(value) != {"kind", "text", "evidence_refs"} or value.get("kind") not in {"CONFIRMED", "SUPPORTED", "UNKNOWN", "CONTRADICTION"}:
        raise ValueError("invalid investigation finding")
    _statement({"text": value.get("text"), "evidence_refs": value.get("evidence_refs")}, ids)
    if value["kind"] != "UNKNOWN" and not value["evidence_refs"]:
        raise ValueError("non-unknown investigation finding requires evidence refs")


def _review_finding(value: object, ids: set[str]) -> None:
    if not isinstance(value, dict) or set(value) != {"issue", "impact", "evidence_refs"} or not isinstance(value.get("issue"), str) or not value["issue"] or len(value["issue"]) > 1000 or not isinstance(value.get("impact"), str) or not value["impact"] or len(value["impact"]) > 1000 or not isinstance(value.get("evidence_refs"), list) or not value["evidence_refs"] or not all(isinstance(ref, str) and ref in ids for ref in value["evidence_refs"]):
        raise ValueError("invalid review finding")


def _valid_relative(root: Path, value: object) -> None:
    if not isinstance(value, str) or "\\" in value or not value or value.startswith("/") or any(part in {"", ".", ".."} for part in value.split("/")):
        raise ValueError("path must be normalized POSIX repo-relative")
    _safe(root, value)


def _evidence_fresh(root: Path, ref: dict[str, object], registry: dict[str, dict[str, object]] | None = None) -> bool:
    kind, locator = ref["kind"], ref["locator"]
    if kind in {"file", "git"}:
        match = re.fullmatch(r"(file|git):([^#]+)#([0-9a-fA-F]{40,64})", str(locator))
        if not match or match.group(1) != kind: return False
        path = match.group(2)
        try: _valid_relative(root, path)
        except ValueError: return False
        entry = Entry(Path(), {"Evidence": locator}, "")
        # Reuse the native evidence evaluator, with the repository-relative locator.
        return evidence_status(entry, root)[0] == "FRESH"
    if kind == "memory":
        if not isinstance(locator, str) or not locator.startswith(".agent-memory/"):
            return False
        try:
            _valid_relative(root, locator); entry = parse(_safe(root, locator))
        except (ValueError, OSError): return False
        return entry.meta["Status"] == "ACTIVE" and entry.meta["Confidence"] in {"CONFIRMED", "SUPPORTED"} and evidence_status(entry, root)[0] == "FRESH"
    if kind in {"test", "runtime"} and registry is not None:
        source_refs = ref.get("source_refs")
        return isinstance(source_refs, list) and bool(source_refs) and all(
            source in registry and registry[source]["kind"] in {"file", "git"} and _evidence_fresh(root, registry[source])
            for source in source_refs
        )
    return False


def _validate_state(root: Path, state: object, *, enforce_fresh: bool = False) -> dict[str, object]:
    _check_json(state)
    # Schema v1 snapshots predate the two append-only finding collections.
    if isinstance(state, dict) and state.get("schema_version") == 1:
        state.setdefault("investigation_findings", [])
        state.setdefault("review_findings", [])
        for ref in state.get("evidence_refs", []):
            if isinstance(ref, dict) and ref.get("kind") in {"test", "runtime"} and "source_refs" not in ref:
                ref["source_refs"] = []
    if not isinstance(state, dict) or set(state) != _STATE_FIELDS:
        raise ValueError("invalid task state schema")
    if state["schema_version"] != 1 or type(state["revision"]) is not int or state["revision"] < 1:
        raise ValueError("invalid task state revision")
    if not isinstance(state["task_id"], str): raise ValueError("invalid task id")
    try: uuid.UUID(state["task_id"])
    except (ValueError, AttributeError) as exc: raise ValueError("invalid task id") from exc
    if state["status"] not in {"ACTIVE", "DONE"} or not isinstance(state["goal"], str) or not state["goal"].strip() or len(state["goal"]) > 2000:
        raise ValueError("invalid task status or goal")
    milestone = state["current_milestone"]
    if milestone is not None and (not isinstance(milestone, str) or not _milestone_exists(root, milestone)):
        raise ValueError("current_milestone must be linked by the top-level milestone index")
    refs = state["evidence_refs"]
    if not isinstance(refs, list): raise ValueError("invalid evidence_refs")
    ids: set[str] = set()
    registry: dict[str, dict[str, object]] = {}
    for ref in refs:
        kind = ref.get("kind") if isinstance(ref, dict) else None
        expected_keys = {"id", "kind", "locator", "summary", "confidence", "source_refs"} if kind in {"test", "runtime"} else {"id", "kind", "locator", "summary", "confidence"}
        if not isinstance(ref, dict) or set(ref) != expected_keys or not all(isinstance(ref.get(k), str) and ref[k] for k in ("id", "kind", "locator", "summary")) or len(ref["summary"]) > 2000 or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.:-]{0,63}", ref["id"]) or ref["id"].startswith("memory:") or kind not in {"file", "git", "memory", "test", "runtime", "task-input"} or ref.get("confidence") not in {"CONFIRMED", "SUPPORTED"} or ref["id"] in ids:
            raise ValueError("invalid evidence reference")
        if ref["kind"] in {"memory", "test", "runtime", "task-input"} and ref["confidence"] != "SUPPORTED": raise ValueError("non-native evidence may only be SUPPORTED")
        ids.add(ref["id"]); registry[ref["id"]] = ref
    for ref in refs:
        if ref["kind"] in {"test", "runtime"}:
            source_refs = ref["source_refs"]
            if not isinstance(source_refs, list) or not all(isinstance(source, str) and source in registry and registry[source]["kind"] in {"file", "git"} for source in source_refs):
                raise ValueError("test/runtime evidence requires file or git source_refs")
            if enforce_fresh and (not source_refs or not _evidence_fresh(root, ref, registry)):
                raise ValueError("test/runtime evidence requires fresh source_refs")
    for key in _LIST_STATEMENTS:
        if not isinstance(state[key], list): raise ValueError(f"invalid {key}")
        for item in state[key]: _statement(item, ids)
    if any(not item["evidence_refs"] for item in state["supported_evidence"]):
        raise ValueError("supported evidence requires evidence refs")
    if any(not item["evidence_refs"] for item in state["contradictions"]):
        raise ValueError("contradictions require evidence refs")
    if not isinstance(state["investigation_findings"], list): raise ValueError("invalid investigation_findings")
    for item in state["investigation_findings"]: _finding(item, ids)
    if not isinstance(state["review_findings"], list): raise ValueError("invalid review_findings")
    for item in state["review_findings"]: _review_finding(item, ids)
    confirmed = state["confirmed_facts"]
    confirmed_ids = {ref["id"] for ref in refs if ref["kind"] in {"file", "git"} and ref["confidence"] == "CONFIRMED" and _evidence_fresh(root, ref)}
    if any(not set(item["evidence_refs"]) & confirmed_ids for item in confirmed):
        if enforce_fresh: raise ValueError("confirmed facts require fresh native CONFIRMED evidence")
    for key in ("relevant_files", "changed_surface"):
        if not isinstance(state[key], list): raise ValueError(f"invalid {key}")
        for path in state[key]: _valid_relative(root, path)
    if not isinstance(state["relevant_symbols"], list) or not all(isinstance(symbol, str) and symbol for symbol in state["relevant_symbols"]): raise ValueError("invalid relevant_symbols")
    boundary = state["modification_boundary"]
    if not isinstance(boundary, dict) or set(boundary) != {"status", "includes", "excludes", "evidence_refs"} or boundary["status"] not in {"UNVERIFIED", "SUPPORTED", "CONFIRMED"} or not isinstance(boundary["includes"], list) or not isinstance(boundary["excludes"], list) or not isinstance(boundary["evidence_refs"], list): raise ValueError("invalid modification_boundary")
    for path in boundary["includes"] + boundary["excludes"]: _valid_relative(root, path)
    if not all(isinstance(ref, str) and ref in ids for ref in boundary["evidence_refs"]): raise ValueError("invalid boundary evidence refs")
    for key in ("verification_target", "architectural_intent"):
        if state[key] is not None and not isinstance(state[key], str): raise ValueError(f"invalid {key}")
    return state


def _write_state(root: Path, state: dict[str, object], *, enforce_fresh: bool = True) -> None:
    _validate_state(root, state, enforce_fresh=enforce_fresh)
    payload = (json.dumps(state, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    if len(payload) > 256 * 1024: raise ValueError("task state exceeds 256 KiB")
    _atomic_write(_state_path(root), payload)


def _milestone_exists(root: Path, milestone: str) -> bool:
    index = root / ".milestones" / "INDEX.md"
    if not index.is_file() or "/" in milestone or "\\" in milestone or milestone in {"", ".", ".."}: return False
    try: body = parse(index).body
    except ValueError: return False
    return f"]({milestone}/INDEX.md)" in body


def _blank_state(root: Path, goal: str, milestone: str | None) -> dict[str, object]:
    if milestone is not None and not _milestone_exists(root, milestone): raise ValueError("milestone is not linked by the top-level milestone index")
    return {"schema_version": 1, "revision": 1, "task_id": str(uuid.uuid4()), "status": "ACTIVE", "goal": goal,
            "current_milestone": milestone, "confirmed_facts": [], "supported_evidence": [], "unknowns": [], "contradictions": [], "constraints": [], "decisions": [], "investigation_findings": [], "review_findings": [], "relevant_files": [], "relevant_symbols": [], "modification_boundary": {"status": "UNVERIFIED", "includes": [], "excludes": [], "evidence_refs": []}, "changed_surface": [], "evidence_refs": [], "verification_target": None, "architectural_intent": None}


def _read_input(value: str | None) -> dict[str, object]:
    if value is None: return {}
    source = sys.stdin.read() if value == "-" else Path(value).read_text(encoding="utf-8")
    raw = json.loads(source)
    _check_json(raw)
    if not isinstance(raw, dict): raise ValueError("task input must be a JSON object")
    return raw


def _load_state(root: Path, *, active: bool = False) -> dict[str, object]:
    path = _state_path(root)
    if not path.is_file(): raise ValueError("no current task state")
    if path.stat().st_size > 256 * 1024: raise ValueError("task state exceeds 256 KiB")
    try: state = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc: raise ValueError("invalid task state JSON") from exc
    state = _validate_state(root, state)
    if active and state["status"] != "ACTIVE": raise ValueError("current task is not ACTIVE")
    return state


def task_start(root: Path, goal: str, milestone: str | None, input_file: str | None) -> dict[str, object]:
    root = _repo_root(root)
    if not _state_ignored(root): raise ValueError("task state is not ignored; run context init first")
    if not goal.strip(): raise ValueError("goal must not be empty")
    partial = _read_input(input_file)
    allowed = _STATE_FIELDS - {"schema_version", "revision", "task_id", "status", "goal", "current_milestone"}
    if set(partial) - allowed: raise ValueError("task-start input has forbidden fields")
    with _lock(root):
        if not _state_ignored(root): raise ValueError("task state is not ignored; run context init first")
        path = _state_path(root)
        if path.is_file() and _load_state(root)["status"] == "ACTIVE": raise ValueError("an ACTIVE task already exists")
        state = _blank_state(root, goal, milestone); state.update(partial); _write_state(root, state)
    return {"ok": True, "state": state}


def task_update(root: Path, role: str, base_revision: int, input_file: str | None) -> dict[str, object]:
    root = _repo_root(root)
    if role not in _ROLE_FIELDS or type(base_revision) is not int: raise ValueError("invalid task update")
    partial = _read_input(input_file)
    if not partial or set(partial) - _ROLE_FIELDS[role]: raise ValueError("role is not allowed to update these fields")
    with _lock(root):
        state = _load_state(root, active=True)
        if state["revision"] != base_revision: raise ValueError("task revision conflict")
        if role != "controller" and "evidence_refs" in partial:
            existing = {ref["id"]: ref for ref in state["evidence_refs"]}
            proposed = {ref["id"]: ref for ref in partial["evidence_refs"] if isinstance(ref, dict) and isinstance(ref.get("id"), str)}
            if any(ref_id not in proposed or proposed[ref_id] != ref for ref_id, ref in existing.items()):
                raise ValueError("non-controller evidence_refs are append-only")
        state.update(partial); state["revision"] = base_revision + 1
        _write_state(root, state, enforce_fresh=bool({"evidence_refs", "confirmed_facts"} & set(partial)))
    return {"ok": True, "state": state}


def task_show(root: Path) -> dict[str, object]:
    root = _repo_root(root)
    return {"ok": True, "state": _load_state(root)}


def task_close(root: Path, base_revision: int) -> dict[str, object]:
    root = _repo_root(root)
    with _lock(root):
        state = _load_state(root, active=True)
        if state["revision"] != base_revision: raise ValueError("task revision conflict")
        state["status"] = "DONE"; state["revision"] = base_revision + 1; _write_state(root, state, enforce_fresh=False)
    return {"ok": True, "state": state}


def _linked_entries(root: Path) -> list[Entry]:
    indexed: list[Entry] = []
    for index_path in (root / ".agent-memory" / "INDEX.md", root / ".agent-memory" / "decisions" / "INDEX.md", root / ".agent-memory" / "lessons" / "INDEX.md"):
        if not index_path.is_file(): continue
        try: index = parse(index_path)
        except ValueError: continue
        for link in re.findall(r"\[[^]]+\]\(([^)]+\.md)\)", index.body):
            try: target = _safe(index_path.parent, link)
            except ValueError: continue
            if target.is_file():
                try: indexed.append(parse(target))
                except ValueError: continue
    return indexed


def _tokens(text: str) -> set[str]:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    runs = re.findall(r"[\u4e00-\u9fff]+", normalized)
    result = {"".join(run) for run in re.findall(r"[^\W_]+", normalized, flags=re.UNICODE) if len(run) > 1}
    for run in runs:
        result.update(run); result.update(run[index:index + 2] for index in range(len(run) - 1))
    return result


def _audience(entry: Entry, role: str) -> bool:
    audience = entry.meta.get("Audience")
    if audience is None: return False
    return "all" in audience or role in audience


def _route(root: Path, task: str, role: str) -> list[Entry]:
    words = _tokens(task); candidates = [entry for entry in (_linked_entries(root) or entries(root)) if _audience(entry, role)]
    matched: list[Entry] = []
    for entry in candidates:
        explicit = entry.meta.get("Topics", []) + entry.meta.get("Symbols", [])
        haystack = " ".join(explicit) if explicit else f"{entry.path.name} {entry.body}"
        project_wide_constraint = (
            entry.meta.get("Kind") == "HARD_CONSTRAINT"
            and entry.meta["Applicability"] == "PROJECT"
            and entry.meta["Status"] == "ACTIVE"
            and entry.meta["Confidence"] in {"CONFIRMED", "SUPPORTED"}
            and entry.meta["Evidence"] != "NONE"
            and entry.meta["Evidence"] != []
            and evidence_status(entry, root)[0] == "FRESH"
        )
        if project_wide_constraint or words & _tokens(haystack): matched.append(entry)
    return list({entry.path: entry for entry in matched}.values())


def _changed_files(root: Path) -> list[str]:
    proc = subprocess.run(["git", "status", "--porcelain=v1", "-z"], cwd=root, capture_output=True, text=True, check=False)
    if proc.returncode: return []
    records = proc.stdout.split("\0"); paths: list[str] = []; index = 0
    while index < len(records):
        record = records[index]
        if not record: break
        status = record[:2]
        if len(record) > 3: paths.append(record[3:].replace("\\", "/"))
        if "R" in status or "C" in status:
            index += 1
            if index < len(records) and records[index]: paths.append(records[index].replace("\\", "/"))
        index += 1
    return list(dict.fromkeys(paths))


def _milestone_slice(root: Path, milestone: str | None) -> dict[str, dict[str, object]]:
    if not milestone: return {}
    directory = root / ".milestones" / milestone
    result: dict[str, dict[str, object]] = {}
    for name, label in (("scope.md", "Scope"), ("decisions.md", "Decisions"), ("verification.md", "Verification")):
        path = directory / name
        if path.is_file():
            try:
                entry = parse(path); state, _ = evidence_status(entry, root)
                result[label] = {"source": str(path.relative_to(root)).replace("\\", "/"), "status": entry.meta["Status"], "confidence": entry.meta["Confidence"], "state": state, "text": entry.body.strip()}
            except ValueError: pass
    return result


def _memory_context(root: Path, task: str, role: str) -> dict[str, object]:
    selected = _route(root, task, role); confirmed = []; supported = []; constraints = []; decisions = []; unknowns = []; evidence = []; files = []; symbols = []
    for entry in selected:
        rel, text = str(entry.path.relative_to(root)).replace("\\", "/"), entry.body.strip()
        state, detail = evidence_status(entry, root)
        confidence = "STALE" if state == "STALE" else ("SUPPORTED" if entry.meta["Confidence"] in {"CONFIRMED", "SUPPORTED"} else entry.meta["Confidence"])
        ref_id = f"memory:{rel}"
        evidence.append({"id": ref_id, "kind": "memory", "locator": rel, "summary": "; ".join(detail) or "fresh memory entry", "confidence": confidence})
        if state == "STALE":
            unknowns.append({"text": f"{rel}: stale evidence; revalidate before use", "evidence_refs": [ref_id]})
            continue
        recorded_evidence = entry.meta["Evidence"]
        trusted = entry.meta["Confidence"] in {"CONFIRMED", "SUPPORTED"} and recorded_evidence != "NONE" and recorded_evidence != []
        active = entry.meta["Status"] == "ACTIVE" and trusted
        if active:
            applicability = entry.meta["Applicability"]
            scopes = applicability if isinstance(applicability, list) else [applicability]
            for scope in scopes:
                if not isinstance(scope, str) or scope in {"PROJECT", "NONE"}: continue
                try:
                    _safe(root, scope)
                    files.append(scope.replace("\\", "/"))
                except ValueError:
                    unknowns.append({"text": f"{rel}: invalid applicability {scope}", "evidence_refs": [ref_id]})
        statement = {"source": rel, "text": text, "evidence_refs": [ref_id]}
        if not active: unknowns.append({"text": f"{rel}: {text.splitlines()[0] if text else 'Unknown'}", "evidence_refs": [ref_id]})
        elif entry.meta.get("Kind") == "HARD_CONSTRAINT": constraints.append(statement)
        elif "/decisions/" in rel: decisions.append(statement)
        else: supported.append(statement)
        symbols.extend(entry.meta.get("Symbols", []))
    # Applicability is memory routing metadata, never a change authorization.
    return {"confirmed": confirmed, "supported": supported, "constraints": constraints, "decisions": decisions, "unknowns": unknowns, "evidence": evidence, "files": list(dict.fromkeys(files)), "symbols": list(dict.fromkeys(symbols))}


def _state_pack(root: Path, state: dict[str, object], role: str) -> dict[str, object]:
    milestone = _milestone_slice(root, state["current_milestone"])
    query = " ".join([state["goal"], *state["relevant_symbols"], *state["relevant_files"]])
    memory = _memory_context(root, query, role)
    registry = {ref["id"]: ref for ref in state["evidence_refs"]}
    fresh_ids = {ref["id"] for ref in state["evidence_refs"] if ref["kind"] in {"file", "git"} and ref["confidence"] == "CONFIRMED" and _evidence_fresh(root, ref)}
    confirmed = [item for item in state["confirmed_facts"] if set(item["evidence_refs"]) & fresh_ids]
    demoted = [{"text": f"stale confirmed fact: {item['text']}", "evidence_refs": item["evidence_refs"]} for item in state["confirmed_facts"] if item not in confirmed]
    native_stale = {ref["id"] for ref in state["evidence_refs"] if ref["kind"] in {"file", "git", "memory", "test", "runtime"} and not _evidence_fresh(root, ref, registry)}
    stale_test_runtime = {
        ref["id"] for ref in state["evidence_refs"]
        if ref["kind"] in {"test", "runtime"} and not _evidence_fresh(root, ref, registry)
    }
    supported = [item for item in state["supported_evidence"] if not item["evidence_refs"] or (not set(item["evidence_refs"]).issubset(native_stale) and not set(item["evidence_refs"]) & stale_test_runtime)]
    demoted_supported = [{"text": f"stale supported evidence: {item['text']}", "evidence_refs": item["evidence_refs"]} for item in state["supported_evidence"] if item not in supported]
    def refs_for(*groups: object) -> list[dict[str, object]]:
        used: set[str] = set()
        def visit(value: object) -> None:
            if isinstance(value, dict):
                if isinstance(value.get("evidence_refs"), list): used.update(value["evidence_refs"])
                for child in value.values(): visit(child)
            elif isinstance(value, list):
                for child in value: visit(child)
        for group in groups: visit(group)
        registry = state["evidence_refs"] + memory["evidence"]
        by_id = {ref["id"]: ref for ref in registry}
        pending = list(used)
        while pending:
            ref = by_id.get(pending.pop())
            if ref and ref["kind"] in {"test", "runtime"}:
                for source in ref["source_refs"]:
                    if source not in used:
                        used.add(source); pending.append(source)
        return [ref for ref in registry if ref["id"] in used]
    meta = {"ok": True, "schema_version": state["schema_version"], "task_id": state["task_id"], "state_revision": state["revision"], "role": role}
    if role == "sol-high":
        facts, supported = confirmed + memory["confirmed"], supported + memory["supported"]
        constraints, decisions = state["constraints"] + memory["constraints"], state["decisions"] + memory["decisions"]
        payload = {"Goal": state["goal"], "Confirmed Facts": facts, "Supported Evidence": supported, "Hard Constraints": constraints, "Decisions": decisions, "Unknowns": state["unknowns"] + demoted + demoted_supported + memory["unknowns"], "Contradictions": state["contradictions"], "Milestone Scope": milestone.get("Scope"), "Milestone Decisions": milestone.get("Decisions")}
        return meta | payload | {"Evidence refs": refs_for(facts, supported, constraints, decisions, payload["Unknowns"], payload["Contradictions"])}
    if role == "luna":
        unknowns = state["unknowns"] + demoted + demoted_supported + memory["unknowns"]
        constraints = state["constraints"] + memory["constraints"]
        payload = {"Goal": state["goal"], "Investigation Target": state["verification_target"] or state["goal"], "Relevant Files": list(dict.fromkeys(state["relevant_files"] + memory["files"])), "Relevant Symbols": list(dict.fromkeys(state["relevant_symbols"] + memory["symbols"])), "Hard Constraints": constraints, "Unknowns": unknowns, "Contradictions": state["contradictions"], "Verification Target": state["verification_target"] or milestone.get("Verification"), "Milestone Verification": milestone.get("Verification")}
        return meta | payload | {"Evidence refs": refs_for(constraints, unknowns, state["contradictions"])}
    if role == "terra-implementer":
        facts, supported = confirmed + memory["confirmed"], supported + memory["supported"]
        constraints, decisions = state["constraints"] + memory["constraints"], state["decisions"] + memory["decisions"]
        payload = {"Goal": state["goal"], "Confirmed Facts": facts, "Supported Evidence": supported, "Hard Constraints": constraints, "Decisions": decisions, "Relevant Files": list(dict.fromkeys(state["relevant_files"] + memory["files"])), "Modification Boundary": state["modification_boundary"], "Required Verification": state["verification_target"], "Milestone Scope": milestone.get("Scope"), "Implementation Constraints": milestone.get("Decisions")}
        return meta | payload | {"Evidence refs": refs_for(facts, supported, constraints, decisions, state["modification_boundary"])}
    if role == "terra-reviewer":
        changed = list(dict.fromkeys(state["changed_surface"] + _changed_files(root)))
        intent = state["architectural_intent"] or milestone.get("Scope")
        constraints, decisions = state["constraints"] + memory["constraints"], state["decisions"] + memory["decisions"] + ([milestone["Decisions"]] if "Decisions" in milestone else [])
        payload = {"Review Goal": state["goal"], "Architectural Intent": intent, "Hard Constraints": constraints, "Durable Decisions": decisions, "Changed Surface": changed}
        relevant = refs_for(constraints, decisions)
        def touches(ref: dict[str, object]) -> bool:
            if ref["kind"] not in {"file", "git"}: return False
            match = re.fullmatch(r"(?:file|git):([^#]+)#[0-9a-fA-F]{40,64}", str(ref["locator"]))
            return bool(match and match.group(1) in changed)
        registry = state["evidence_refs"] + memory["evidence"]
        relevant = list({ref["id"]: ref for ref in [*relevant, *(ref for ref in registry if touches(ref))]}.values())
        return meta | payload | {"Evidence refs": relevant}
    raise ValueError("invalid role")


def prepare(root: Path, task: str | None, role: str) -> dict[str, object]:
    if role not in _PACK_ROLES: raise ValueError("invalid role")
    if task is None:
        root = _repo_root(root)
        return _state_pack(root, _load_state(root, active=True), role)
    memory = _memory_context(root, task, role)
    common = {"ok": True, "schema_version": 1, "task_id": None, "state_revision": None, "role": role, "Goal": task, "Evidence refs": memory["evidence"]}
    if role == "sol-high": return common | {"Confirmed Facts": memory["confirmed"], "Supported Evidence": memory["supported"], "Hard Constraints": memory["constraints"], "Decisions": memory["decisions"], "Unknowns": memory["unknowns"], "Contradictions": []}
    if role == "luna": return common | {"Investigation Target": task, "Relevant Files": memory["files"], "Relevant Symbols": memory["symbols"], "Hard Constraints": memory["constraints"], "Unknowns": memory["unknowns"], "Contradictions": [], "Verification Target": task}
    if role == "terra-implementer": return common | {"Confirmed Facts": memory["confirmed"], "Supported Evidence": memory["supported"], "Hard Constraints": memory["constraints"], "Decisions": memory["decisions"], "Relevant Files": memory["files"], "Modification Boundary": {"status": "UNVERIFIED", "includes": [], "excludes": [], "evidence_refs": []}, "Required Verification": None}
    visible = memory["constraints"] + memory["decisions"]
    used = {ref_id for item in visible for ref_id in item["evidence_refs"]}
    evidence = [ref for ref in memory["evidence"] if ref["id"] in used]
    return {"ok": True, "schema_version": 1, "task_id": None, "state_revision": None, "role": role, "Review Goal": task, "Architectural Intent": None, "Hard Constraints": memory["constraints"], "Durable Decisions": memory["decisions"], "Changed Surface": _changed_files(root), "Evidence refs": evidence}


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
