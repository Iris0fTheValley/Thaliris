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
import tempfile
import uuid

from .markdown import Entry, evidence_status, parse
from .models import ContextConfig

MANAGED_START = "<!-- codex-context:begin -->"
MANAGED_END = "<!-- codex-context:end -->"
MANAGED = f"""{MANAGED_START}
## Codex context

Controller: Sol mid; only Controller spawns (default concurrency: 1), and children MUST NOT delegate. Sol high reasons, Luna scouts/verifies, Terra implements/reviews. Use the Microtask fast path for bounded work; parallelize only independent worksets. Route memory and milestones through their INDEX files. Prefer Serena symbols, cachebro deltas, and explicit agentmemory recall when available. Entry point: `context`; current source/Git/tests are the correctness core, so adapters MUST fall back to native behavior.
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


def _entry(title: str, body: str, *, status: str = "DRAFT", evidence: str = "NONE", confidence: str = "UNVERIFIED", applicability: str = "PROJECT") -> bytes:
    return (f"---\nEvidence: {evidence}\nRevision: 1\nStatus: {status}\nApplicability: {applicability}\nConfidence: {confidence}\n---\n\n# {title}\n\n{body}\n").encode()


def _template_files() -> dict[str, bytes]:
    return {
        ".agent-memory/INDEX.md": _entry("Memory index", "- [Operator](operator.md)\n- [Prompt policy](prompt-policy.md)\n- [Project conventions](project-conventions.md)\n- [Decisions](decisions/INDEX.md)\n- [Lessons](lessons/INDEX.md)"),
        ".agent-memory/operator.md": _entry("Operator notes", "Unknown. Record only confirmed operating constraints."),
        ".agent-memory/prompt-policy.md": _entry("Prompt policy", "Use manual recall only. Automatic injection and compression are disabled."),
        ".agent-memory/project-conventions.md": _entry("Project conventions", "Unknown. Add conventions only with evidence."),
        ".agent-memory/decisions/INDEX.md": _entry("Decision index", "Link each project decision entry here."),
        ".agent-memory/decisions/PD-001.md": _entry("PD-001: decision template", "This is an unadopted template, not a project fact.\n\n## Decision\n\nUnknown.\n\n## Rationale\n\nUnknown."),
        ".agent-memory/lessons/INDEX.md": _entry("Lessons index", "- [L-001 lesson template](L-001.md)"),
        ".agent-memory/lessons/L-001.md": _entry("L-001: lesson template", "This is an unadopted template, not a historical claim.\n\n## Failure mode\n\nUnknown.\n\n## Prevention\n\nUnknown."),
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


def init(root: Path) -> dict[str, object]:
    root = _repo_root(root)
    # Validate before creating even the operational lock file: corrupt markers
    # must fail without a tool-owned filesystem mutation.
    pre_agents = _safe(root, "AGENTS.md")
    _managed_agents(pre_agents.read_bytes().decode("utf-8") if pre_agents.exists() else "")
    with _lock(root):
        files = {path: content for path, content in _template_files().items() if not _safe(root, path).exists()}
        agents = _safe(root, "AGENTS.md"); current = agents.read_bytes().decode("utf-8") if agents.exists() else ""
        rendered = _managed_agents(current)
        if current != rendered: files["AGENTS.md"] = rendered.encode()
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


def _route(root: Path, task: str) -> list[Entry]:
    words = set(re.findall(r"[a-z0-9_./-]+", task.lower())); candidates = _linked_entries(root) or entries(root)
    matched = [e for e in candidates if words & set(re.findall(r"[a-z0-9_./-]+", (e.path.name + " " + e.body).lower()))]
    defaults = [e for e in entries(root) if e.path.name in {"operator.md", "prompt-policy.md", "project-conventions.md"}]
    return list({e.path: e for e in matched + defaults}.values())


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


def prepare(root: Path, task: str, role: str) -> dict[str, object]:
    selected = _route(root, task); facts = []; constraints = []; decisions = []; unknowns = []; evidence = []; files = []
    for entry in selected:
        rel, text = str(entry.path.relative_to(root)).replace("\\", "/"), entry.body.strip()
        state, detail = evidence_status(entry, root); evidence.append({"path": rel, "state": state, "confidence": "STALE" if state == "STALE" else entry.meta["Confidence"], "details": detail})
        if state == "STALE":
            unknowns.append(f"{rel}: stale evidence; revalidate before use")
            continue
        recorded_evidence = entry.meta["Evidence"]
        trusted = entry.meta["Confidence"] in {"CONFIRMED", "SUPPORTED"} and recorded_evidence != "NONE" and recorded_evidence != []
        active = entry.meta["Status"] == "ACTIVE" and trusted and "unknown" not in text.lower()
        if active:
            applicability = entry.meta["Applicability"]
            scopes = applicability if isinstance(applicability, list) else [applicability]
            for scope in scopes:
                if not isinstance(scope, str) or scope in {"PROJECT", "NONE"}: continue
                try:
                    _safe(root, scope)
                    files.append(scope.replace("\\", "/"))
                except ValueError:
                    unknowns.append(f"{rel}: invalid applicability {scope}")
        if not active: unknowns.append(f"{rel}: {text.splitlines()[0] if text else 'Unknown'}")
        else: facts.append({"source": rel, "text": text})
        if active and any(term in rel for term in ("policy", "convention", "operator")): constraints.append({"source": rel, "text": text})
        if active and "/decisions/" in rel: decisions.append({"source": rel, "text": text})
    common = {"ok": True, "role": role}
    if role == "sol-high": return common | {"Goal": task, "Facts": facts, "Constraints": constraints, "Decisions": decisions, "Unknowns": unknowns, "Evidence": evidence}
    files = list(dict.fromkeys(files))
    if role == "luna": return common | {"Goal": task, "Files": files, "Unknowns": unknowns, "Evidence": evidence, "Investigation Target": task}
    if role == "terra-implementer": return common | {"Goal": task, "Facts": facts, "Files": files, "Constraints": constraints, "Modification Boundary": {"status": "SUPPORTED" if files else "UNVERIFIED", "paths": files}}
    if role == "terra-reviewer": return common | {"Architectural Intent": task, "Decisions": decisions, "Changed Surface": _changed_files(root), "Known Risks": unknowns, "Evidence": evidence}
    raise ValueError("invalid role")


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
