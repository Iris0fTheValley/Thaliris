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
from .intent_audit import MANAGED_HOOKS_DESCRIPTION, bind_unbound_intent, cleanup_task_audit, merge_hooks, remove_hooks, task_close_audit

MANAGED_START = "<!-- thaliris:begin -->"
MANAGED_END = "<!-- thaliris:end -->"
IGNORE_START = "# thaliris:begin"
IGNORE_END = "# thaliris:end"
# Accepted only so repositories initialized before the rename can be upgraded
# or uninstalled without losing content outside the managed block.
LEGACY_MANAGED_START = "<!-- codex-context:begin -->"
LEGACY_MANAGED_END = "<!-- codex-context:end -->"
LEGACY_IGNORE_START = "# codex-context:begin"
LEGACY_IGNORE_END = "# codex-context:end"
IGNORE_RULES = (".context/backups/", ".context/state.json", ".context/context.lock", ".context/audit/")
# Keep the generated instruction surface small. Detailed policy lives in the
# role-pack document and is loaded only when a task needs it.
MANAGED = f"""{MANAGED_START}
## Thaliris Router

Codex remains the runtime. Thaliris stores bounded task control and pointers; it has no worker, scheduler, polling loop, or authority to decide correctness.

Controller uses `context task-status` or `context prepare --role controller` for bounded packets. `context task-show` is explicit raw diagnostics; `context task-artifact` passes pointers, not contents. Only Controller registers artifact pointers, which must target ordinary task-local files rather than `.context/`, `.git/`, `.agent-memory/`, or `.milestones/` control data.

### Controller orchestration economy

- `task-start` already returns a bounded packet; do not immediately repeat `task-status`.
- After a spawn, use one `wait_agent` with a realistic blocking timeout as the normal single-child primitive. For the measured T2/T3 children (104–257 seconds), the benchmark uses `timeout_ms=240000`; do not poll with repeated waits or fall back to sub-minimum values.
- Do not call `list_agents` on the normal single-child path. Use it only for topology checks or recovery after an unexpected wait/result.
- Query `task-status` only after a known task mutation, a state/revision change, or recovery is required; do not repeat an unchanged revision.
- Use `send_message` only for a new constraint, correction, or material evidence. Do not use it to ask for progress or to say “continue”.

During an ACTIVE task, the persistent Controller is control-plane-only. The Controller MUST NOT perform repository investigation or source mutation at any time, before or after child dispatch. Dispatching a child never grants the Controller permission to investigate or edit. Repository investigation and source mutation belong only to fresh execution children using `fork_turns="none"`. The Controller may perform only bounded routing/state operations and deterministic acceptance checks. Root actions are mechanically guarded at PreToolUse; PostToolUse records dispatch evidence. Codex owns execution; Thaliris has no worker, scheduler, polling loop, or lifecycle runtime.
Every new root child must use `fork_turns="none"`; this never unlocks root investigation or mutation.

Read detailed role packs only when needed. Keep raw findings, evidence, transcripts, logs, and tool output outside Controller packets and durable memory; promote only explicit durable decisions, constraints, invariants, failure modes, or material milestone progress.
{MANAGED_END}
"""

ROLE_PACKS = """# Thaliris Role Packs

Load this document when the compact managed router is insufficient.

## Controller

Use `context task-status` for task identity/status, active work, pending results,
unresolved questions, artifact pointers, and accepted constraints/decisions. Raw
findings, reviews, evidence records, Git state, and broad memory/milestone bodies
do not belong in normal Controller routing. `context task-show` is diagnostic-only.

Every active task starts with one fresh execution child using `fork_turns="none"`.
The Controller may then add Investigator, Curator, Reasoning Specialist, or
Reviewer children only when the bounded result shows that role is needed. A
one- or two-turn fork is also rewritten to `none`; no encrypted reason is used
as an exception. PreToolUse guards root shell investigation/mutation and
task-close-before-child; PostToolUse records native dispatch evidence. Use
native completion/mailbox observation; there is no Thaliris worker, scheduler,
polling loop, or retry runtime.

## Work And Retention

For a local microtask, use exactly one fresh Implementer then deterministic
verification; the persistent Controller never edits source directly.
Investigators append bounded findings; Curators compact a snapshot; Reasoning
Specialists receive accepted decisions rather than raw history; Implementers receive
the explicit Modification Boundary, including out-of-scope exclusions and required
verification; reviewers return independent findings. If bounded findings contain an
unresolved architecture, provenance, or cross-module decision, route only that
Decision Context to `sol-high` rather than investigating at root. Promote only
reusable decisions, constraints, invariants, failure modes, or material milestone
progress/verification. `task-artifact` records a bounded normalized external pointer. Artifact registration is Controller-only and excludes private control paths such as `.context/`, `.git/`, `.agent-memory/`, and `.milestones/`.
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


def _entry(title: str, body: str, *, status: str = "DRAFT", evidence: str = "NONE", confidence: str = "UNVERIFIED", applicability: str = "PROJECT", audience: list[str] | None = None, topics: list[str] | None = None, symbols: list[str] | None = None, kind: str | None = None, include_routing: bool = True) -> bytes:
    audience = ["all"] if audience is None else audience
    topics = [] if topics is None else topics
    symbols = [] if symbols is None else symbols
    optional = ""
    for key, value in (("Audience", audience), ("Topics", topics), ("Symbols", symbols)):
        if not include_routing:
            continue
        if value is not None:
            optional += f"{key}: {json.dumps(value, ensure_ascii=False)}\n"
    kind_line = f"Kind: {kind}\n" if kind is not None else ""
    return (f"---\nEvidence: {evidence}\nRevision: 1\nStatus: {status}\nApplicability: {applicability}\nConfidence: {confidence}\n{kind_line}{optional}---\n\n# {title}\n\n{body}\n").encode()


def _template_files(*, include_routing: bool = True, include_kind: bool = True, decision_link: bool = True) -> dict[str, bytes]:
    def template(title: str, body: str, **kwargs: object) -> bytes:
        kind = kwargs.pop("kind")
        return _entry(title, body, include_routing=include_routing, kind=kind if include_kind else None, **kwargs)
    return {
        "docs/thaliris-role-packs.md": ROLE_PACKS.encode(),
        ".agent-memory/INDEX.md": template("Memory index", "- [Operator](operator.md)\n- [Prompt policy](prompt-policy.md)\n- [Project conventions](project-conventions.md)\n- [Decisions](decisions/INDEX.md)\n- [Lessons](lessons/INDEX.md)", audience=["all"], kind="MEMORY"),
        ".agent-memory/operator.md": template("Operator notes", "Unknown. Record only confirmed operating constraints.", kind="HARD_CONSTRAINT"),
        ".agent-memory/prompt-policy.md": template("Prompt policy", "Use manual recall only. Automatic injection and compression are disabled.", audience=["controller"], kind="HARD_CONSTRAINT"),
        ".agent-memory/project-conventions.md": template("Project conventions", "Unknown. Add conventions only with evidence.", kind="HARD_CONSTRAINT"),
        ".agent-memory/decisions/INDEX.md": template("Decision index", "- [PD-001 decision template](PD-001.md)" if decision_link else "Link each project decision entry here.", kind="MEMORY"),
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


def _managed_span(current: str, start_marker: str, end_marker: str, legacy_start: str, legacy_end: str, label: str) -> tuple[int, int] | None:
    counts = tuple(current.count(marker) for marker in (start_marker, end_marker, legacy_start, legacy_end))
    if counts == (0, 0, 0, 0):
        return None
    if counts == (1, 1, 0, 0):
        start, end_start = current.index(start_marker), current.index(end_marker)
        end = end_start + len(end_marker)
    elif counts == (0, 0, 1, 1):
        start, end_start = current.index(legacy_start), current.index(legacy_end)
        end = end_start + len(legacy_end)
    else:
        raise ValueError(f"{label} has duplicate, mixed, or damaged managed markers")
    if start >= end_start:
        raise ValueError(f"{label} has duplicate, mixed, or damaged managed markers")
    return start, end


def _managed_agents(current: str) -> str:
    span = _managed_span(current, MANAGED_START, MANAGED_END, LEGACY_MANAGED_START, LEGACY_MANAGED_END, "AGENTS.md")
    newline = "\r\n" if "\r\n" in current else "\n"
    block = MANAGED.replace("\n", newline)
    if span is None:
        if not current: return block
        separator = "" if current.endswith(("\n", "\r")) else newline
        return current + separator + block
    start, end = span
    suffix = current[end:]
    if suffix.startswith("\r\n"): suffix = suffix[2:]
    elif suffix.startswith("\n"): suffix = suffix[1:]
    return current[:start] + block + suffix


def _managed_gitignore(current: str) -> str:
    span = _managed_span(current, IGNORE_START, IGNORE_END, LEGACY_IGNORE_START, LEGACY_IGNORE_END, ".gitignore")
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
        manual: list[str] = []
        agents = _safe(root, "AGENTS.md"); current = agents.read_bytes().decode("utf-8") if agents.exists() else ""
        rendered = _managed_agents(current)
        if current != rendered: files["AGENTS.md"] = rendered.encode()
        ignore = _safe(root, ".gitignore"); current_ignore = ignore.read_bytes().decode("utf-8") if ignore.exists() else ""
        rendered_ignore = _managed_gitignore(current_ignore)
        if current_ignore != rendered_ignore: files[".gitignore"] = rendered_ignore.encode()
        hooks = _safe(root, ".codex/hooks.json")
        if hooks.exists():
            try:
                hook_data = json.loads(hooks.read_text(encoding="utf-8"))
                if not isinstance(hook_data, dict): raise ValueError("hooks root must be an object")
                rendered_hooks, hooks_changed = merge_hooks(hook_data)
                if hooks_changed: files[".codex/hooks.json"] = (json.dumps(rendered_hooks, ensure_ascii=False, indent=2) + "\n").encode()
            except (OSError, ValueError, json.JSONDecodeError):
                manual.append(".codex/hooks.json")
        else:
            rendered_hooks, _ = merge_hooks({"description": MANAGED_HOOKS_DESCRIPTION})
            files[".codex/hooks.json"] = (json.dumps(rendered_hooks, ensure_ascii=False, indent=2) + "\n").encode()
        if not _safe(root, ".context/config.json").exists(): files[".context/config.json"] = ContextConfig().write(root)
        if not files: return {"ok": True, "changed": False, "backup": None, "manual_migration_required": manual}
        return {"ok": True, "changed": True, "backup": _apply_with_backup(root, files, [], "init"), "files": sorted(files), "manual_migration_required": manual}


def migrate(root: Path) -> dict[str, object]:
    """Migrate only byte-for-byte known generated memory templates.

    Normal routing never scans as a fallback.  This bounded scan is deliberately
    migration-only so a user-edited legacy file is reported rather than replaced.
    """
    result = init(root)
    root = _repo_root(root)
    current = _template_files()
    historical = (
        _template_files(include_routing=False, include_kind=False, decision_link=False),
        _template_files(include_routing=True, include_kind=False, decision_link=False),
        _template_files(include_routing=True, include_kind=True, decision_link=False),
    )
    writes: dict[str, bytes] = {}
    manual: list[str] = list(result.get("manual_migration_required", []))
    with _lock(root):
        base = root / ".agent-memory"
        if base.is_dir():
            for path in sorted(base.rglob("*.md")):
                rel = str(path.relative_to(root)).replace("\\", "/")
                data = path.read_bytes()
                normalized = data.replace(b"\r\n", b"\n")
                if rel in current and any(normalized == version.get(rel) for version in historical):
                    if data != current[rel]: writes[rel] = current[rel]
                elif b"Audience:" not in data or b"Kind:" not in data:
                    manual.append(rel)
        backup = _apply_with_backup(root, writes, [], "migrate") if writes else None
    result.update({"changed": bool(result.get("changed") or writes), "migration": "v2", "migrated": sorted(writes), "manual_migration_required": manual, "migration_backup": backup})
    return result


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
    # Validate before acquiring the operational lock: corrupt markers must fail
    # without creating the tool-owned .context directory or lock file.
    pre_agents = _safe(root, "AGENTS.md")
    if pre_agents.is_file():
        current = pre_agents.read_bytes().decode("utf-8")
        _managed_span(current, MANAGED_START, MANAGED_END, LEGACY_MANAGED_START, LEGACY_MANAGED_END, "AGENTS.md")
    pre_ignore = _safe(root, ".gitignore")
    if pre_ignore.is_file():
        current = pre_ignore.read_bytes().decode("utf-8")
        _managed_span(current, IGNORE_START, IGNORE_END, LEGACY_IGNORE_START, LEGACY_IGNORE_END, ".gitignore")
    private_state_present = any(
        (_safe(root, relative).is_file() or _safe(root, relative).is_dir())
        for relative in (".context/audit", ".context/backups", ".context/state.json", ".context/context.lock")
    )
    with _lock(root):
        writes: dict[str, bytes] = {}; deletes: list[str] = []; kept: list[str] = []; manual: list[str] = []
        agents = _safe(root, "AGENTS.md")
        if agents.is_file():
            current = agents.read_bytes().decode("utf-8")
            span = _managed_span(current, MANAGED_START, MANAGED_END, LEGACY_MANAGED_START, LEGACY_MANAGED_END, "AGENTS.md")
            if span is not None:
                start, end = span
                suffix = current[end:]
                if suffix.startswith("\r\n"): suffix = suffix[2:]
                elif suffix.startswith("\n"): suffix = suffix[1:]
                stripped = current[:start] + suffix
                if stripped: writes["AGENTS.md"] = stripped.encode()
                else: deletes.append("AGENTS.md")
        ignore = _safe(root, ".gitignore")
        # Never remove the private-state protection while any audit/state or
        # backup data remains.  Uninstall is not permission to expose it in
        # git status; a later explicit cleanup can remove the data safely.
        if ignore.is_file() and not private_state_present:
            current = ignore.read_bytes().decode("utf-8")
            span = _managed_span(current, IGNORE_START, IGNORE_END, LEGACY_IGNORE_START, LEGACY_IGNORE_END, ".gitignore")
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
        hooks = _safe(root, ".codex/hooks.json")
        if hooks.is_file():
            try:
                hook_data = json.loads(hooks.read_text(encoding="utf-8"))
                if not isinstance(hook_data, dict): raise ValueError("hooks root must be an object")
                rendered_hooks, hooks_changed = remove_hooks(hook_data)
                if hooks_changed:
                    owned_empty = (
                        hook_data.get("description") == MANAGED_HOOKS_DESCRIPTION
                        and set(rendered_hooks) <= {"description", "hooks"}
                        and rendered_hooks.get("description") == MANAGED_HOOKS_DESCRIPTION
                        and rendered_hooks.get("hooks", {}) == {}
                    )
                    if owned_empty: deletes.append(".codex/hooks.json")
                    else: writes[".codex/hooks.json"] = (json.dumps(rendered_hooks, ensure_ascii=False, indent=2) + "\n").encode()
            except (OSError, ValueError, json.JSONDecodeError):
                manual.append(".codex/hooks.json")
        if not writes and not deletes: return {"ok": True, "changed": False, "kept": sorted(set(kept)), "backup": None, "manual_migration_required": manual}
        return {"ok": True, "changed": True, "kept": sorted(set(kept)), "backup": _apply_with_backup(root, writes, deletes, "uninstall"), "deleted": sorted(deletes), "manual_migration_required": manual}


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
# is not a second memory store; durable_promotion_count is task-local
# bookkeeping, but task-promote includes it with durable writes in its existing
# backup mutation.
_STATE_NAME = ".context/state.json"
_STATE_FIELDS = {
    "schema_version", "revision", "task_id", "status", "goal", "current_milestone",
    "confirmed_facts", "supported_evidence", "unknowns", "contradictions", "constraints",
    "decisions", "relevant_files", "relevant_symbols", "modification_boundary",
    "changed_surface", "evidence_refs", "verification_target", "architectural_intent",
    "investigation_findings", "investigation_snapshot", "review_findings",
    "investigation_covered_through", "review_handled_through", "durable_promotion_count",
    "active_work", "pending_results", "artifact_refs",
}
_LIST_STATEMENTS = {"confirmed_facts", "supported_evidence", "unknowns", "contradictions", "constraints", "decisions"}
_SNAPSHOT_MAX_ITEMS = 64
_SNAPSHOT_MAX_BYTES = 32 * 1024
_PROMOTION_BUDGET = 16
_CONTROLLER_FIELDS = _STATE_FIELDS - {
    "schema_version", "revision", "task_id", "status", "goal", "durable_promotion_count",
    "investigation_findings", "investigation_snapshot", "review_findings",
}
_ROLE_FIELDS = {
    "controller": _CONTROLLER_FIELDS,
    "luna": {"investigation_findings", "evidence_refs"},
    "luna-investigator": {"investigation_findings", "evidence_refs"},
    "luna-curator": {"investigation_snapshot", "investigation_covered_through"},
    "sol-high": set(),
    "terra-implementer": {"changed_surface", "evidence_refs"},
    "terra-reviewer": {"review_findings", "evidence_refs"},
}
_PACK_ROLES = {"controller", "sol-high", "luna", "luna-investigator", "luna-curator", "terra-implementer", "terra-reviewer"}


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


def _snapshot_item(value: object, ids: set[str], findings: list[dict[str, object]]) -> None:
    keys = {"id", "kind", "text", "derived_from", "supersedes", "evidence_refs"}
    if not isinstance(value, dict) or set(value) != keys or not isinstance(value.get("id"), str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.:-]{0,63}", value["id"]) or value.get("kind") not in {"CONFIRMED", "SUPPORTED", "UNKNOWN", "CONTRADICTION"}:
        raise ValueError("invalid investigation snapshot item")
    _statement({"text": value.get("text"), "evidence_refs": value.get("evidence_refs")}, ids)
    derived = value.get("derived_from")
    supersedes = value.get("supersedes")
    if not isinstance(derived, list) or not derived or len(set(derived)) != len(derived) or not all(type(index) is int and 0 <= index < len(findings) for index in derived):
        raise ValueError("snapshot derived_from must reference raw finding indexes")
    if not isinstance(supersedes, list) or len(set(supersedes)) != len(supersedes) or not all(isinstance(item, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_.:-]{0,63}", item) for item in supersedes):
        raise ValueError("invalid snapshot supersedes")
    source_kinds = {findings[index]["kind"] for index in derived}
    source_evidence = {ref for index in derived for ref in findings[index]["evidence_refs"]}
    if not set(value["evidence_refs"]) <= source_evidence:
        raise ValueError("snapshot evidence must come from derived raw findings")
    if value["kind"] != "UNKNOWN" and not value["evidence_refs"]:
        raise ValueError("non-unknown snapshot item requires evidence refs")
    if value["kind"] == "CONFIRMED" and source_kinds != {"CONFIRMED"}:
        raise ValueError("snapshot cannot promote epistemic status")
    # A mixed UNKNOWN/CONTRADICTION source set is not a supported conclusion:
    # compression cannot wash unresolved uncertainty out of the working view.
    if value["kind"] == "SUPPORTED" and not source_kinds <= {"SUPPORTED", "CONFIRMED"}:
        raise ValueError("snapshot cannot promote epistemic status")
    if value["kind"] == "CONTRADICTION" and "CONTRADICTION" not in source_kinds:
        raise ValueError("snapshot cannot promote epistemic status")


def _valid_relative(root: Path, value: object) -> None:
    if not isinstance(value, str) or "\\" in value or not value or value.startswith("/") or any(part in {"", ".", ".."} for part in value.split("/")):
        raise ValueError("path must be normalized POSIX repo-relative")
    _safe(root, value)


def _bounded_lines(value: object, field: str) -> None:
    if not isinstance(value, list) or len(value) > 16 or not all(
        isinstance(item, str) and item.strip() and len(item) <= 300 and not _bad_text(item)
        for item in value
    ):
        raise ValueError(f"invalid {field}")


def _artifact_ref(root: Path, value: object) -> None:
    if not isinstance(value, dict) or not {"id", "path", "summary"}.issubset(value) or set(value) - {"id", "path", "summary", "producer_role", "scope", "evidence_refs"}:
        raise ValueError("invalid artifact reference")
    identifier, path, summary = value["id"], value["path"], value["summary"]
    if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.:-]{0,63}", identifier):
        raise ValueError("invalid artifact reference")
    _valid_relative(root, path)
    if path == ".git" or path.startswith(".git/") or path == ".context" or path.startswith(".context/") or path == ".agent-memory" or path.startswith(".agent-memory/") or path == ".milestones" or path.startswith(".milestones/"):
        raise ValueError("artifact path targets private control data")
    if not isinstance(summary, str) or not summary.strip() or _bad_text(summary) or len(summary) > 300:
        raise ValueError("invalid artifact reference")
    if "producer_role" in value and (not isinstance(value["producer_role"], str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", value["producer_role"])):
        raise ValueError("invalid artifact reference")
    if "scope" in value and (not isinstance(value["scope"], str) or not value["scope"].strip() or _bad_text(value["scope"]) or len(value["scope"]) > 300):
        raise ValueError("invalid artifact reference")
    if "evidence_refs" in value and (not isinstance(value["evidence_refs"], list) or len(value["evidence_refs"]) > 16 or not all(isinstance(ref, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_.:-]{0,63}", ref) for ref in value["evidence_refs"])):
        raise ValueError("invalid artifact reference")


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


def _require_fresh_confirmed_items(root: Path, refs: list[dict[str, object]], items: list[dict[str, object]]) -> None:
    fresh = {ref["id"] for ref in refs if ref["kind"] in {"file", "git"} and ref["confidence"] == "CONFIRMED" and _evidence_fresh(root, ref)}
    if any(item["kind"] == "CONFIRMED" and not set(item["evidence_refs"]) & fresh for item in items):
        raise ValueError("new CONFIRMED investigation material requires fresh native CONFIRMED evidence")


def _validate_state(root: Path, state: object, *, enforce_fresh: bool = False) -> dict[str, object]:
    _check_json(state)
    # Schema v1 snapshots predate append-only finding collections, cursors,
    # and bounded task-local durable-promotion bookkeeping.
    if isinstance(state, dict) and state.get("schema_version") == 1:
        state.setdefault("investigation_findings", [])
        state.setdefault("investigation_snapshot", [])
        state.setdefault("review_findings", [])
        state.setdefault("investigation_covered_through", 0)
        state.setdefault("review_handled_through", 0)
        state.setdefault("durable_promotion_count", 0)
        state.setdefault("active_work", [])
        state.setdefault("pending_results", [])
        state.setdefault("artifact_refs", [])
        for ref in state.get("evidence_refs", []):
            if isinstance(ref, dict) and ref.get("kind") in {"test", "runtime"} and "source_refs" not in ref:
                ref["source_refs"] = []
    if not isinstance(state, dict) or set(state) != _STATE_FIELDS:
        raise ValueError("invalid task state schema")
    if state["schema_version"] != 1 or type(state["revision"]) is not int or state["revision"] < 1:
        raise ValueError("invalid task state revision")
    if type(state["durable_promotion_count"]) is not int or not 0 <= state["durable_promotion_count"] <= _PROMOTION_BUDGET:
        raise ValueError("invalid durable_promotion_count")
    if not isinstance(state["task_id"], str): raise ValueError("invalid task id")
    try: uuid.UUID(state["task_id"])
    except (ValueError, AttributeError) as exc: raise ValueError("invalid task id") from exc
    if state["status"] not in {"ACTIVE", "DONE"} or not isinstance(state["goal"], str) or not state["goal"].strip() or len(state["goal"]) > 2000:
        raise ValueError("invalid task status or goal")
    _bounded_lines(state["active_work"], "active_work")
    _bounded_lines(state["pending_results"], "pending_results")
    if not isinstance(state["artifact_refs"], list) or len(state["artifact_refs"]) > 32:
        raise ValueError("invalid artifact_refs")
    artifact_ids: set[str] = set()
    for artifact in state["artifact_refs"]:
        _artifact_ref(root, artifact)
        if artifact["id"] in artifact_ids:
            raise ValueError("duplicate artifact reference id")
        artifact_ids.add(artifact["id"])
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
    declared_confirmed_ids = {ref["id"] for ref in refs if ref["kind"] in {"file", "git"} and ref["confidence"] == "CONFIRMED"}
    if any(item["kind"] == "CONFIRMED" and not set(item["evidence_refs"]) & declared_confirmed_ids for item in state["investigation_findings"]):
        raise ValueError("CONFIRMED investigation findings require native CONFIRMED evidence")
    snapshot = state["investigation_snapshot"]
    if not isinstance(snapshot, list) or len(snapshot) > _SNAPSHOT_MAX_ITEMS:
        raise ValueError(f"investigation_snapshot exceeds {_SNAPSHOT_MAX_ITEMS} items")
    if len(json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()) > _SNAPSHOT_MAX_BYTES:
        raise ValueError(f"investigation_snapshot exceeds {_SNAPSHOT_MAX_BYTES} bytes")
    snapshot_ids: set[str] = set()
    for item in snapshot:
        _snapshot_item(item, ids, state["investigation_findings"])
        if item["kind"] == "CONFIRMED" and not set(item["evidence_refs"]) & declared_confirmed_ids:
            raise ValueError("CONFIRMED snapshot items require native CONFIRMED evidence")
        if item["id"] in snapshot_ids: raise ValueError("duplicate investigation snapshot id")
        snapshot_ids.add(item["id"])
    if not isinstance(state["review_findings"], list): raise ValueError("invalid review_findings")
    for item in state["review_findings"]: _review_finding(item, ids)
    for key, size in (("investigation_covered_through", len(state["investigation_findings"])), ("review_handled_through", len(state["review_findings"]))):
        if type(state[key]) is not int or not 0 <= state[key] <= size:
            raise ValueError(f"invalid {key}")
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


def _state_payload(root: Path, state: dict[str, object], *, enforce_fresh: bool = True) -> bytes:
    _validate_state(root, state, enforce_fresh=enforce_fresh)
    payload = (json.dumps(state, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    if len(payload) > 256 * 1024: raise ValueError("task state exceeds 256 KiB")
    return payload


def _write_state(root: Path, state: dict[str, object], *, enforce_fresh: bool = True) -> None:
    _atomic_write(_state_path(root), _state_payload(root, state, enforce_fresh=enforce_fresh))


def _milestone_exists(root: Path, milestone: str) -> bool:
    index = root / ".milestones" / "INDEX.md"
    if not index.is_file() or "/" in milestone or "\\" in milestone or milestone in {"", ".", ".."}: return False
    try: body = parse(index).body
    except ValueError: return False
    return f"]({milestone}/INDEX.md)" in body


def _blank_state(root: Path, goal: str, milestone: str | None) -> dict[str, object]:
    if milestone is not None and not _milestone_exists(root, milestone): raise ValueError("milestone is not linked by the top-level milestone index")
    return {"schema_version": 1, "revision": 1, "task_id": str(uuid.uuid4()), "status": "ACTIVE", "goal": goal,
            "current_milestone": milestone, "confirmed_facts": [], "supported_evidence": [], "unknowns": [], "contradictions": [], "constraints": [], "decisions": [], "investigation_findings": [], "investigation_snapshot": [], "review_findings": [], "investigation_covered_through": 0, "review_handled_through": 0, "durable_promotion_count": 0, "active_work": [], "pending_results": [], "artifact_refs": [], "relevant_files": [], "relevant_symbols": [], "modification_boundary": {"status": "UNVERIFIED", "includes": [], "excludes": [], "evidence_refs": []}, "changed_surface": [], "evidence_refs": [], "verification_target": None, "architectural_intent": None}


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


def task_start(root: Path, goal: str, milestone: str | None, input_file: str | None, intent_capture_id: str | None = None) -> dict[str, object]:
    root = _repo_root(root)
    if not _state_ignored(root): raise ValueError("task state is not ignored; run context init first")
    if not goal.strip(): raise ValueError("goal must not be empty")
    partial = _read_input(input_file)
    allowed = _STATE_FIELDS - {"schema_version", "revision", "task_id", "status", "goal", "current_milestone", "durable_promotion_count"}
    if set(partial) - allowed: raise ValueError("task-start input has forbidden fields")
    with _lock(root):
        if not _state_ignored(root): raise ValueError("task state is not ignored; run context init first")
        path = _state_path(root)
        if path.is_file() and _load_state(root)["status"] == "ACTIVE": raise ValueError("an ACTIVE task already exists")
        state = _blank_state(root, goal, milestone); state.update(partial)
        if any(item.get("supersedes") for item in state["investigation_snapshot"] if isinstance(item, dict)):
            raise ValueError("initial snapshot cannot supersede prior entries")
        _require_fresh_confirmed_items(root, state["evidence_refs"], state["investigation_findings"] + state["investigation_snapshot"])
        _write_state(root, state)
        try:
            # UserPromptSubmit precedes Controller's task-start. Only its
            # opaque one-time capability may bind the raw root turn.
            bind_unbound_intent(root, str(state["task_id"]), intent_capture_id)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass
    return _controller_ack(state, ["task"], include_packet=True)


def task_update(root: Path, role: str, base_revision: int, input_file: str | None) -> dict[str, object]:
    root = _repo_root(root)
    if role not in _ROLE_FIELDS or type(base_revision) is not int: raise ValueError("invalid task update")
    partial = _read_input(input_file)
    forbidden = set(partial) - _ROLE_FIELDS[role]
    if forbidden:
        if role == "controller" and forbidden & {"investigation_findings", "investigation_snapshot", "review_findings"}:
            raise ValueError("append-only findings and snapshots are not controller-writable")
        raise ValueError("role is not allowed to update these fields")
    if not partial: raise ValueError("role is not allowed to update these fields")
    with _lock(root):
        state = _load_state(root, active=True)
        if state["revision"] != base_revision: raise ValueError("task revision conflict")
        new_investigation: list[dict[str, object]] = []
        # Raw provenance is immutable for every role, including Controller.
        # Inputs are additions rather than a replacement of the stored prefix.
        for key, additions_role in (("investigation_findings", {"luna", "luna-investigator"}), ("review_findings", {"terra-reviewer"})):
            if key not in partial:
                continue
            if role not in additions_role:
                raise ValueError("role is not allowed to update these fields")
            additions = partial[key]
            existing = state[key]
            if not isinstance(additions, list) or not additions or any(item in existing for item in additions):
                raise ValueError(f"{key} must contain new append-only additions")
            if key == "investigation_findings": new_investigation = additions
            partial = partial | {key: existing + additions}
        if "investigation_snapshot" in partial:
            previous_ids = {item["id"] for item in state["investigation_snapshot"]}
            proposed = partial["investigation_snapshot"]
            if not isinstance(proposed, list) or any(not set(item.get("supersedes", [])) <= previous_ids for item in proposed if isinstance(item, dict)):
                raise ValueError("snapshot supersedes must reference the previous snapshot")
            if role == "luna-curator" and "investigation_covered_through" not in partial:
                # A fresh curator consumes the supplied uncovered suffix by default.
                partial = partial | {"investigation_covered_through": len(state["investigation_findings"])}
        if role == "luna-curator" and "investigation_covered_through" in partial and partial["investigation_covered_through"] < state["investigation_covered_through"]:
            raise ValueError("curator coverage cannot move backwards")
        if "evidence_refs" in partial:
            additions = partial["evidence_refs"]
            if not isinstance(additions, list): raise ValueError("evidence_refs must be additions")
            existing = {ref["id"]: ref for ref in state["evidence_refs"]}
            proposed = {ref.get("id"): ref for ref in additions if isinstance(ref, dict) and isinstance(ref.get("id"), str)}
            if len(proposed) != len(additions) or any(ref_id in existing or ref_id is None for ref_id in proposed):
                raise ValueError("evidence_refs must be append-only additions with new immutable IDs")
            # State validation checks every complete entry after this merge.
            partial = partial | {"evidence_refs": state["evidence_refs"] + additions}
        if "artifact_refs" in partial:
            additions = partial["artifact_refs"]
            existing_ids = {item["id"] for item in state["artifact_refs"]}
            if not isinstance(additions, list) or not additions or any(
                not isinstance(item, dict) or item.get("id") in existing_ids for item in additions
            ):
                raise ValueError("artifact_refs must be append-only additions with new immutable IDs")
            partial = partial | {"artifact_refs": state["artifact_refs"] + additions}
        state.update(partial); state["revision"] = base_revision + 1
        new_snapshot = state["investigation_snapshot"] if "investigation_snapshot" in partial else []
        _require_fresh_confirmed_items(root, state["evidence_refs"], new_investigation + new_snapshot)
        _write_state(root, state, enforce_fresh=bool({"evidence_refs", "confirmed_facts"} & set(partial)))
    return _controller_ack(state, sorted(partial))


def task_show(root: Path) -> dict[str, object]:
    root = _repo_root(root)
    return {"ok": True, "state": _load_state(root)}


def _controller_packet(state: dict[str, object]) -> dict[str, object]:
    """Return control metadata only; raw evidence remains task-show-only."""
    statements = lambda items: [item["text"] for item in items]
    boundary = state["modification_boundary"]
    return {
        "ok": True,
        "schema_version": state["schema_version"],
        "role": "controller",
        "Task": {"id": state["task_id"], "goal": state["goal"], "status": state["status"], "revision": state["revision"], "milestone": state["current_milestone"]},
        "Active Work": state["active_work"],
        "Pending Results": state["pending_results"],
        "Unresolved Questions": statements(state["unknowns"]),
        "Artifact Refs": state["artifact_refs"],
        "Accepted Constraints": statements(state["constraints"]),
        "Accepted Decisions": statements(state["decisions"]),
        "Modification Boundary": {
            "status": boundary["status"],
            "includes": boundary["includes"],
            "excludes": boundary["excludes"],
            "evidence_refs": boundary["evidence_refs"],
        },
        "Verification Target": state["verification_target"],
    }


def _controller_ack(state: dict[str, object], changed: list[str], *, include_packet: bool = False) -> dict[str, object]:
    """Return mutation metadata without exposing the internal task state."""
    result: dict[str, object] = {
        "ok": True,
        "task_id": state["task_id"],
        "revision": state["revision"],
        "status": state["status"],
        "changed": sorted({value for value in changed if isinstance(value, str)}),
    }
    if include_packet:
        result["controller_packet"] = _controller_packet(state)
    return result


def task_status(root: Path) -> dict[str, object]:
    root = _repo_root(root)
    return _controller_packet(_load_state(root))


def task_artifact(root: Path, base_revision: int, artifact_id: str, path: str, summary: str, *, producer_role: str | None = None, scope: str | None = None, evidence_refs: list[str] | None = None) -> dict[str, object]:
    root = _repo_root(root)
    if producer_role not in {None, "controller"}:
        raise ValueError("only Controller may register artifact pointers")
    artifact = {"id": artifact_id, "path": path, "summary": summary}
    if producer_role is not None: artifact["producer_role"] = producer_role
    if scope is not None: artifact["scope"] = scope
    if evidence_refs is not None: artifact["evidence_refs"] = evidence_refs
    _artifact_ref(root, artifact)
    with _lock(root):
        state = _load_state(root, active=True)
        if state["revision"] != base_revision:
            raise ValueError("task revision conflict")
        if artifact_id in {item["id"] for item in state["artifact_refs"]}:
            raise ValueError("artifact reference id already exists")
        state["artifact_refs"].append(artifact)
        state["revision"] = base_revision + 1
        _write_state(root, state, enforce_fresh=False)
    return _controller_ack(state, ["artifact_refs"])


def task_close(root: Path, base_revision: int) -> dict[str, object]:
    root = _repo_root(root)
    with _lock(root):
        state = _load_state(root, active=True)
        if state["revision"] != base_revision: raise ValueError("task revision conflict")
        task_id = str(state["task_id"])
    try:
        # Do not hold the core task lock across the external auditor. A task
        # update racing this snapshot is detected below and remains ACTIVE.
        audit = task_close_audit(root, task_id, cleanup=False)
    except (OSError, ValueError, TypeError, subprocess.SubprocessError, json.JSONDecodeError):
        # Audit is supplemental; task-close remains available when its
        # private capture plane is damaged or unavailable.
        audit = {"status": "UNKNOWN", "findings": [], "reason": "audit_capture_failure"}
    with _lock(root):
        current = _load_state(root, active=True)
        if current["revision"] != base_revision or current["task_id"] != task_id:
            raise ValueError("task revision conflict")
        state = current
        if audit.get("status") == "DRIFT":
            # Preserve raw evidence and ACTIVE state so Controller can correct
            # the delegation and retry task-close. Never expose model text.
            return {
                "ok": False,
                "task_id": state["task_id"],
                "revision": state["revision"],
                "status": state["status"],
                "changed": [],
                "intent_audit": {"status": "DRIFT", "finding": "Correct delegation scope before closing this task."},
            }
        try:
            cleanup_task_audit(root, task_id, audit.get("status"))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            # Fail open: a cleanup failure cannot turn normal task-close into
            # a Controller-visible audit result.
            audit = {"status": "UNKNOWN", "findings": [], "reason": "audit_cleanup_failure"}
        state["status"] = "DONE"; state["revision"] = base_revision + 1; _write_state(root, state, enforce_fresh=False)
    # PASS and UNKNOWN intentionally stay entirely in the private audit plane.
    return _controller_ack(state, ["status"])


_PROMOTION_TYPES = {"decision", "invariant", "failure_mode", "constraint"}
_PROMOTION_RECORD_KEYS = {"type", "id", "title", "text", "evidence_refs", "confidence", "audience", "topics", "symbols", "applicability"}
_PROMOTION_MILESTONE_KEYS = {"id", "progress", "verification", "evidence_refs", "confidence"}
_PROMOTION_ID = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{0,63}")
_PROMOTION_AUDIENCE = {"all", "controller", "sol-high", "luna", "terra-implementer", "terra-reviewer"}


def _promotion_text(value: object, field: str, *, maximum: int = 2000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum or any(ord(char) < 32 or char in "\r\n" for char in value):
        raise ValueError(f"promotion {field} must be bounded single-line text")
    return value


def _promotion_list(value: object, field: str, *, maximum: int = 16) -> list[str]:
    if not isinstance(value, list) or not value or len(value) > maximum or not all(isinstance(item, str) and item and len(item) <= 200 and not any(ord(char) < 32 or char in "\r\n" for char in item) for item in value):
        raise ValueError(f"promotion {field} must be a bounded string list")
    return value


def _promotion_optional_list(value: object, field: str) -> list[str]:
    if value is None: return []
    if not isinstance(value, list) or len(value) > 16 or not all(isinstance(item, str) and item and len(item) <= 200 and not any(ord(char) < 32 or char in "\r\n" for char in item) for item in value):
        raise ValueError(f"promotion {field} must be a bounded string list")
    return value


def _promotion_applicability(value: object) -> str | list[str]:
    if isinstance(value, str): return _promotion_text(value, "applicability", maximum=200)
    if isinstance(value, list): return _promotion_optional_list(value, "applicability")
    raise ValueError("promotion applicability must be text or a string list")


def _promotion_evidence(root: Path, state: dict[str, object], evidence_ids: object, confidence: str) -> list[str]:
    ids = _promotion_list(evidence_ids, "evidence_refs")
    registry = {ref["id"]: ref for ref in state["evidence_refs"]}
    locators: list[str] = []
    directly_confirmed = False
    for evidence_id in ids:
        ref = registry.get(evidence_id)
        if ref is None:
            raise ValueError("promotion evidence_refs must use current task evidence")
        kind = ref["kind"]
        if kind in {"file", "git"}:
            if not _evidence_fresh(root, ref):
                raise ValueError("promotion requires fresh native evidence")
            locators.append(str(ref["locator"]))
            directly_confirmed = directly_confirmed or ref["confidence"] == "CONFIRMED"
        elif kind in {"test", "runtime"}:
            source_refs = ref.get("source_refs")
            if not isinstance(source_refs, list) or not source_refs or not _evidence_fresh(root, ref, registry):
                raise ValueError("promotion test/runtime evidence requires fresh native source_refs")
            for source_id in source_refs:
                source = registry[source_id]
                locators.append(str(source["locator"]))
        else:
            raise ValueError("promotion accepts only fresh native file/git or test/runtime evidence; memory/task-input/NONE is rejected")
    locators = list(dict.fromkeys(locators))
    if not locators:
        raise ValueError("promotion requires usable native evidence")
    if confidence == "CONFIRMED" and not directly_confirmed:
        raise ValueError("CONFIRMED promotion requires directly referenced fresh native CONFIRMED evidence")
    return locators


def _promotion_evidence_value(locators: list[str]) -> str:
    return locators[0] if len(locators) == 1 else json.dumps(locators, ensure_ascii=False)


def _promoted_milestone_entry(path: Path, text: str, locators: list[str], confidence: str) -> bytes:
    try:
        entry = parse(path)
    except (ValueError, OSError) as exc:
        raise ValueError(f"milestone file is invalid: {exc}") from exc
    heading = next((line for line in entry.body.splitlines() if line.startswith("# ")), None)
    if heading is None:
        raise ValueError(f"milestone file missing required heading: {path.name}")
    raw = path.read_text(encoding="utf-8")
    end = raw.find("\n---\n", 4)
    front = raw[:end]
    lines = front.splitlines()
    replacements = {"Evidence": _promotion_evidence_value(locators), "Revision": str(int(entry.meta["Revision"]) + 1), "Confidence": confidence}
    rendered = []
    for line in lines:
        key = line.split(":", 1)[0]
        rendered.append(f"{key}: {replacements[key]}" if key in replacements else line)
    newline = "\r\n" if "\r\n" in raw else "\n"
    return (newline.join(rendered) + newline + "---" + newline + newline + heading + newline + newline + text + newline).encode("utf-8")


def task_promote(root: Path, role: str, base_revision: int, input_file: str | None) -> dict[str, object]:
    root = _repo_root(root)
    if role != "controller":
        raise ValueError("only the Controller may promote durable records")
    if type(base_revision) is not int:
        raise ValueError("invalid task promotion revision")
    payload = _read_input(input_file)
    if set(payload) - {"records", "milestone"}:
        raise ValueError("task-promote accepts only records and milestone; raw findings/logs/transcripts are not durable records; large maintenance routes to a fresh child")
    records = payload.get("records", [])
    milestone = payload.get("milestone")
    if not isinstance(records, list) or len(records) > 16:
        raise ValueError("promotion records must be a bounded list; large maintenance routes to a fresh child")
    if milestone is None and not records:
        raise ValueError("task-promote requires explicit records or milestone fields")
    if milestone is not None and not isinstance(milestone, dict):
        raise ValueError("promotion milestone must be an object")
    with _lock(root):
        state = _load_state(root, active=True)
        if state["revision"] != base_revision:
            raise ValueError("task revision conflict")
        budget_units = len(records)
        if milestone is not None:
            budget_units += sum(field in milestone for field in ("progress", "verification"))
        if state["durable_promotion_count"] + budget_units > _PROMOTION_BUDGET:
            raise ValueError(f"promotion budget exceeds {_PROMOTION_BUDGET} task-local units")
        writes: dict[str, bytes] = {}
        index_additions: dict[str, list[tuple[str, str]]] = {}
        seen_targets: set[str] = set()
        for record in records:
            required_record_keys = {"type", "id", "title", "text", "evidence_refs", "confidence"}
            if not isinstance(record, dict) or set(record) - _PROMOTION_RECORD_KEYS or not required_record_keys <= set(record):
                raise ValueError("promotion records require only bounded semantic fields: type/id/title/text/evidence_refs/confidence and routing hints")
            record_type = record.get("type")
            if not isinstance(record_type, str) or record_type not in _PROMOTION_TYPES:
                raise ValueError("promotion type must be decision, invariant, failure_mode, or constraint; raw findings are rejected")
            record_id = record.get("id")
            if not isinstance(record_id, str) or not _PROMOTION_ID.fullmatch(record_id) or record_id == "INDEX":
                raise ValueError("promotion id is not a safe durable filename")
            title = _promotion_text(record.get("title"), "title", maximum=200)
            if any(char in title for char in "[]()"):
                raise ValueError("promotion title contains Markdown link characters")
            body = _promotion_text(record.get("text"), "text")
            refs = record.get("evidence_refs")
            confidence = record.get("confidence")
            if not isinstance(confidence, str) or confidence not in {"CONFIRMED", "SUPPORTED"}:
                raise ValueError("promotion confidence must be explicitly CONFIRMED or SUPPORTED")
            locators = _promotion_evidence(root, state, refs, confidence)
            audience = _promotion_list(record.get("audience", ["all"]), "audience")
            if not set(audience) <= _PROMOTION_AUDIENCE:
                raise ValueError("promotion audience contains an unknown role")
            topics = _promotion_optional_list(record.get("topics"), "topics")
            symbols = _promotion_optional_list(record.get("symbols"), "symbols")
            applicability = _promotion_applicability(record.get("applicability", "PROJECT"))
            if record_type == "decision": directory, index = "decisions", ".agent-memory/decisions/INDEX.md"
            elif record_type == "failure_mode": directory, index = "lessons", ".agent-memory/lessons/INDEX.md"
            else: directory, index = "", ".agent-memory/INDEX.md"
            relative = f".agent-memory/{directory + '/' if directory else ''}{record_id}.md"
            if relative in seen_targets or _safe(root, relative).exists():
                raise ValueError("promotion refuses to overwrite an existing durable target")
            seen_targets.add(relative)
            writes[relative] = _entry(title, body, status="ACTIVE", evidence=_promotion_evidence_value(locators), confidence=confidence, applicability=json.dumps(applicability, ensure_ascii=False) if isinstance(applicability, list) else applicability, audience=audience, topics=topics, symbols=symbols, kind="HARD_CONSTRAINT" if record_type == "constraint" else "MEMORY")
            index_additions.setdefault(index, []).append((title, f"{record_id}.md"))
        for index, additions in index_additions.items():
            index_path = _safe(root, index)
            try:
                parse(index_path)
            except (ValueError, OSError) as exc:
                raise ValueError(f"promotion INDEX is invalid: {exc}") from exc
            updated = index_path.read_text(encoding="utf-8")
            newline = "\r\n" if "\r\n" in updated else "\n"
            for title, filename in additions:
                if re.search(rf"\]\({re.escape(filename)}\)", updated):
                    raise ValueError("promotion target is already routed by INDEX")
                updated = updated.rstrip("\r\n") + f"{newline}- [{title}]({filename}){newline}"
            writes[index] = updated.encode("utf-8")
        if milestone is not None:
            if set(milestone) - _PROMOTION_MILESTONE_KEYS:
                raise ValueError("promotion milestone accepts only id/progress/verification/evidence_refs/confidence")
            milestone_id = milestone.get("id")
            if milestone_id != state["current_milestone"] or not isinstance(milestone_id, str) or not _milestone_exists(root, milestone_id):
                raise ValueError("promotion milestone must be the current linked milestone")
            fields = [field for field in ("progress", "verification") if field in milestone]
            if not fields:
                raise ValueError("promotion milestone must explicitly provide progress or verification")
            confidence = milestone.get("confidence")
            if not isinstance(confidence, str) or confidence not in {"CONFIRMED", "SUPPORTED"}:
                raise ValueError("promotion milestone confidence must be explicit")
            locators = _promotion_evidence(root, state, milestone.get("evidence_refs"), confidence)
            for field in fields:
                text = _promotion_text(milestone[field], f"milestone {field}")
                relative = f".milestones/{milestone_id}/{field}.md"
                if relative in writes or not _safe(root, relative).is_file():
                    raise ValueError("promotion milestone path is unknown")
                writes[relative] = _promoted_milestone_entry(_safe(root, relative), text, locators, confidence)
        state["durable_promotion_count"] += budget_units
        writes[_STATE_NAME] = _state_payload(root, state)
        backup = _apply_with_backup(root, writes, [], "task-promote")
    return {"ok": True, "task_id": state["task_id"], "state_revision": state["revision"], "promoted": sorted(path for path in writes if path != _STATE_NAME), "backup": backup}


def _linked_entries(root: Path) -> tuple[list[Entry], list[str]]:
    """Traverse only the root memory INDEX graph, failing closed on corruption.

    INDEX nodes are navigation records, not recall candidates.  The deliberately
    small bounds prevent a malformed graph from becoming a broad filesystem scan.
    """
    base = root / ".agent-memory"
    root_index = base / "INDEX.md"
    if not root_index.is_file(): return [], ["memory INDEX missing"]
    indexed: list[Entry] = []
    errors: list[str] = []
    stack: list[tuple[Path, int]] = [(root_index, 0)]
    seen: set[Path] = set()
    while stack:
        index_path, depth = stack.pop()
        resolved = index_path.resolve(strict=False)
        if resolved in seen: errors.append(f"memory INDEX cycle: {index_path.relative_to(root)}"); break
        if depth > 8 or len(seen) >= 128: errors.append("memory INDEX traversal limit exceeded"); break
        seen.add(resolved)
        try: index = parse(index_path)
        except (ValueError, OSError) as exc: errors.append(f"memory INDEX invalid: {exc}"); break
        links = re.findall(r"\[[^]]+\]\(([^)]+\.md)\)", index.body)
        if not links: errors.append(f"memory INDEX empty: {index_path.relative_to(root)}"); break
        for link in links:
            try:
                target = _safe(index_path.parent, link)
                target.relative_to(base.resolve(strict=True))
            except ValueError:
                errors.append(f"memory INDEX link escapes: {link}"); break
            if not target.is_file(): errors.append(f"memory INDEX link missing: {link}"); break
            if target.name == "INDEX.md":
                stack.append((target, depth + 1)); continue
            try: indexed.append(parse(target))
            except (ValueError, OSError) as exc: errors.append(f"memory entry invalid: {exc}"); break
        if errors: break
    return ([], errors) if errors else (indexed, [])


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


def _route(root: Path, task: str, role: str) -> tuple[list[Entry], list[str]]:
    indexed, errors = _linked_entries(root)
    if errors: return [], errors
    words = _tokens(task); candidates = [entry for entry in indexed if _audience(entry, role)]
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
    return list({entry.path: entry for entry in matched}.values()), []


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
    for name, label in (("scope.md", "Scope"), ("decisions.md", "Decisions"), ("progress.md", "Progress"), ("verification.md", "Verification")):
        path = directory / name
        if path.is_file():
            try:
                entry = parse(path); state, _ = evidence_status(entry, root)
                result[label] = {"source": str(path.relative_to(root)).replace("\\", "/"), "status": entry.meta["Status"], "confidence": entry.meta["Confidence"], "state": state, "text": entry.body.strip()}
            except ValueError: pass
    return result


def _memory_context(root: Path, task: str, role: str) -> dict[str, object]:
    selected, routing_errors = _route(root, task, role); confirmed = []; supported = []; constraints = []; decisions = []; unknowns = []; evidence = []; files = []; symbols = []
    unknowns.extend({"text": f"memory routing unavailable: {error}", "evidence_refs": []} for error in routing_errors)
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


def _effective_findings(root: Path, items: list[dict[str, object]], registry: dict[str, dict[str, object]]) -> list[dict[str, object]]:
    """Project historical finding records without claiming stale evidence is live."""
    result: list[dict[str, object]] = []
    for item in items:
        copy = dict(item)
        refs = [ref for ref in item["evidence_refs"] if ref in registry]
        stale = [ref for ref in refs if registry[ref]["kind"] in {"file", "git", "memory", "test", "runtime"} and not _evidence_fresh(root, registry[ref], registry)]
        confirmed_live = any(
            registry[ref]["kind"] in {"file", "git"}
            and registry[ref]["confidence"] == "CONFIRMED"
            and _evidence_fresh(root, registry[ref], registry)
            for ref in refs
        )
        if (item["kind"] == "CONFIRMED" and not confirmed_live) or (item["kind"] in {"CONFIRMED", "SUPPORTED", "CONTRADICTION"} and stale):
            copy["recorded_kind"] = item["kind"]
            copy["kind"] = "UNKNOWN"
            copy["stale_evidence_refs"] = stale or refs
        result.append(copy)
    return result


def _effective_snapshot(root: Path, snapshot: list[dict[str, object]], effective_raw: list[dict[str, object]], registry: dict[str, dict[str, object]]) -> list[dict[str, object]]:
    """Preserve a snapshot's history while refusing an invalid live conclusion."""
    result = _effective_findings(root, snapshot, registry)
    for stored, projected in zip(snapshot, result):
        source_kinds = {effective_raw[index]["kind"] for index in stored["derived_from"]}
        valid = (
            projected["kind"] == "UNKNOWN"
            or (projected["kind"] == "CONFIRMED" and source_kinds == {"CONFIRMED"})
            or (projected["kind"] == "SUPPORTED" and source_kinds <= {"CONFIRMED", "SUPPORTED"})
            or (projected["kind"] == "CONTRADICTION" and "CONTRADICTION" in source_kinds)
        )
        if not valid:
            projected["recorded_kind"] = stored["kind"]
            projected["kind"] = "UNKNOWN"
            projected["invalid_derived_from"] = list(stored["derived_from"])
    return result


def _effective_review_findings(root: Path, items: list[dict[str, object]], registry: dict[str, dict[str, object]]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for item in items:
        copy = dict(item)
        stale = [ref for ref in item["evidence_refs"] if ref in registry and registry[ref]["kind"] in {"file", "git", "memory", "test", "runtime"} and not _evidence_fresh(root, registry[ref], registry)]
        if stale:
            copy["effective_state"] = "UNKNOWN"
            copy["stale_evidence_refs"] = stale
        else:
            copy["effective_state"] = "SUPPORTED"
        result.append(copy)
    return result


def _state_pack(root: Path, state: dict[str, object], role: str) -> dict[str, object]:
    if role == "controller":
        return _controller_packet(state)
    milestone = _milestone_slice(root, state["current_milestone"])
    query = " ".join([state["goal"], *state["relevant_symbols"], *state["relevant_files"]])
    memory_role = "luna" if role == "luna-investigator" else role
    memory = _memory_context(root, query, memory_role) if role != "luna-curator" else {"confirmed": [], "supported": [], "constraints": [], "decisions": [], "unknowns": [], "evidence": [], "files": [], "symbols": []}
    registry = {ref["id"]: ref for ref in state["evidence_refs"]}
    effective_raw = _effective_findings(root, state["investigation_findings"], registry)
    effective_snapshot = _effective_snapshot(root, state["investigation_snapshot"], effective_raw, registry)
    effective_reviews = _effective_review_findings(root, state["review_findings"], registry)
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
    investigation_pending = len(state["investigation_findings"]) - state["investigation_covered_through"]
    review_pending = len(state["review_findings"]) - state["review_handled_through"]
    readiness = {"raw_finding_count": len(state["investigation_findings"]), "covered_through": state["investigation_covered_through"], "pending_findings": investigation_pending, "status": "PENDING" if investigation_pending else "READY"}
    review_status = {"finding_count": len(state["review_findings"]), "handled_through": state["review_handled_through"], "pending_findings": review_pending, "status": "PENDING" if review_pending else "READY"}
    if role == "luna-curator":
        suffix = effective_raw[state["investigation_covered_through"]:]
        payload = {"Goal": state["goal"], "Current Investigation Snapshot": effective_snapshot, "Uncovered Investigation Findings": suffix, "Investigation Readiness": readiness}
        return meta | payload | {"Evidence refs": refs_for(effective_snapshot, suffix)}
    if role == "sol-high":
        facts, supported = confirmed + memory["confirmed"], supported + memory["supported"]
        constraints, decisions = state["constraints"] + memory["constraints"], state["decisions"] + memory["decisions"]
        payload = {"Goal": state["goal"], "Confirmed Facts": facts, "Supported Evidence": supported, "Hard Constraints": constraints, "Decisions": decisions, "Unknowns": state["unknowns"] + demoted + demoted_supported + memory["unknowns"], "Contradictions": state["contradictions"], "Investigation Readiness": readiness, "Review Readiness": review_status, "Milestone Scope": milestone.get("Scope"), "Milestone Decisions": milestone.get("Decisions")}
        return meta | payload | {"Evidence refs": refs_for(facts, supported, constraints, decisions, payload["Unknowns"], payload["Contradictions"])}
    if role in {"luna", "luna-investigator"}:
        unknowns = state["unknowns"] + demoted + demoted_supported + memory["unknowns"]
        constraints = state["constraints"] + memory["constraints"]
        payload = {"Goal": state["goal"], "Investigation Target": state["verification_target"] or state["goal"], "Investigation Snapshot": effective_snapshot, "Relevant Files": list(dict.fromkeys(state["relevant_files"] + memory["files"])), "Relevant Symbols": list(dict.fromkeys(state["relevant_symbols"] + memory["symbols"])), "Hard Constraints": constraints, "Unknowns": unknowns, "Contradictions": state["contradictions"], "Verification Target": state["verification_target"] or milestone.get("Verification"), "Milestone Verification": milestone.get("Verification"), "Investigation Readiness": readiness}
        return meta | payload | {"Evidence refs": refs_for(constraints, unknowns, state["contradictions"], effective_snapshot)}
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
    if role == "luna-curator": raise ValueError("luna-curator requires current task state")
    if role == "controller":
        return {"ok": True, "schema_version": 1, "role": "controller", "Task": {"id": None, "goal": task, "status": "UNBOUND", "revision": None, "milestone": None}, "Active Work": [], "Pending Results": [], "Unresolved Questions": [], "Artifact Refs": [], "Accepted Constraints": [], "Accepted Decisions": []}
    memory_role = "luna" if role == "luna-investigator" else role
    memory = _memory_context(root, task, memory_role)
    common = {"ok": True, "schema_version": 1, "task_id": None, "state_revision": None, "role": role, "Goal": task, "Evidence refs": memory["evidence"]}
    if role == "sol-high": return common | {"Confirmed Facts": memory["confirmed"], "Supported Evidence": memory["supported"], "Hard Constraints": memory["constraints"], "Decisions": memory["decisions"], "Unknowns": memory["unknowns"], "Contradictions": [], "Investigation Readiness": {"raw_finding_count": 0, "covered_through": 0, "pending_findings": 0, "status": "READY"}, "Review Readiness": {"finding_count": 0, "handled_through": 0, "pending_findings": 0, "status": "READY"}}
    if role in {"luna", "luna-investigator"}: return common | {"Investigation Target": task, "Investigation Snapshot": [], "Relevant Files": memory["files"], "Relevant Symbols": memory["symbols"], "Hard Constraints": memory["constraints"], "Unknowns": memory["unknowns"], "Contradictions": [], "Verification Target": task}
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
