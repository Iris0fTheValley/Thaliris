"""Codex-specific mapping for Thaliris Core projections and lifecycle hooks."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

from . import core
from .intent_audit import MANAGED_HOOKS_DESCRIPTION, bind_unbound_intent, cleanup_task_audit, handle_hook, merge_hooks, remove_hooks, task_close_audit


def _read_text(path: Path) -> str:
    return path.read_bytes().decode("utf-8")

MANAGED_START = "<!-- thaliris:begin -->"
MANAGED_END = "<!-- thaliris:end -->"
LEGACY_MANAGED_START = "<!-- codex-context:begin -->"
LEGACY_MANAGED_END = "<!-- codex-context:end -->"
AUDIT_IGNORE_START = "# thaliris-codex:begin"
AUDIT_IGNORE_END = "# thaliris-codex:end"
AUDIT_IGNORE_RULE = ".context/audit/"

MANAGED = f"""{MANAGED_START}
## Thaliris Router

Codex remains the runtime. Thaliris stores bounded task control and pointers; it has no worker, scheduler, polling loop, or authority to decide correctness.

Controller uses `context task-status` or `context prepare --role controller` for bounded packets. `context task-show` is explicit raw diagnostics; `context task-artifact` passes pointers, not contents.

During an active task the persistent root Controller is control-plane-only. Every new root child is a spawned execution child and must be fresh with `fork_turns=\"none\"`; this means no parent-thread history, not an empty Codex context. The child obtains its own Thaliris role projection directly, performs the assigned work, avoids child-to-child delegation, and returns a bounded result to the Controller. Root shell investigation/mutation is mechanically guarded at PreToolUse; PostToolUse records dispatch evidence. Codex owns execution; Thaliris has no worker, scheduler, polling loop, or lifecycle runtime.

Read detailed role packs only when needed. Keep raw findings, evidence, transcripts, logs, and tool output outside Controller packets and durable memory; promote only explicit durable decisions, constraints, invariants, failure modes, or material milestone progress.
{MANAGED_END}
"""

ROLE_PACKS = """# Thaliris Role Packs

Load this document when the compact managed router is insufficient.

## Controller

Use `context task-status` for task identity/status, active work, pending results, unresolved questions, artifact pointers, and accepted constraints/decisions. Raw findings, reviews, evidence records, Git state, and broad memory/milestone bodies do not belong in normal Controller routing. `context task-show` is diagnostic-only.

Every active task starts with one fresh execution child using `fork_turns=\"none\"`. The child receives or loads its own role pack directly; the parent Controller must not consume child-only working material. The Controller may then add Investigator, Curator, Reasoning Specialist, or Reviewer children only when the bounded result shows that role is needed. Use native completion/mailbox observation; there is no Thaliris worker, scheduler, polling loop, or retry runtime.

Codex hook configuration is separate from current-session observation. A project `.codex/hooks.json` proves only configuration; input rewriting, root classification, payload fidelity, and native task delivery remain `UNKNOWN` until a live compatible session observes them. Unknown tools and unverified MCP paths remain `UNKNOWN`/fail-open.
"""


def _managed_span(current: str, label: str) -> tuple[int, int] | None:
    counts = tuple(current.count(marker) for marker in (MANAGED_START, MANAGED_END, LEGACY_MANAGED_START, LEGACY_MANAGED_END))
    if counts == (0, 0, 0, 0):
        return None
    if counts == (1, 1, 0, 0):
        start, end_start = current.index(MANAGED_START), current.index(MANAGED_END)
        end = end_start + len(MANAGED_END)
    elif counts == (0, 0, 1, 1):
        start, end_start = current.index(LEGACY_MANAGED_START), current.index(LEGACY_MANAGED_END)
        end = end_start + len(LEGACY_MANAGED_END)
    else:
        raise ValueError(f"{label} has duplicate, mixed, or damaged managed markers")
    if start >= end_start:
        raise ValueError(f"{label} has duplicate, mixed, or damaged managed markers")
    return start, end


def _managed_agents(current: str) -> str:
    span = _managed_span(current, "AGENTS.md")
    newline = "\r\n" if "\r\n" in current else "\n"
    block = MANAGED.replace("\n", newline)
    if span is None:
        return block if not current else current + ("" if current.endswith(("\n", "\r")) else newline) + block
    start, end = span
    suffix = current[end:]
    if suffix.startswith("\r\n"):
        suffix = suffix[2:]
    elif suffix.startswith("\n"):
        suffix = suffix[1:]
    return current[:start] + block + suffix


def _audit_ignore(current: str, *, remove: bool = False) -> str:
    counts = tuple(current.count(marker) for marker in (AUDIT_IGNORE_START, AUDIT_IGNORE_END))
    if counts not in {(0, 0), (1, 1)}:
        raise ValueError(".gitignore has duplicate or damaged Codex managed markers")
    if counts == (0, 0):
        if remove:
            return current
        newline = "\r\n" if "\r\n" in current else "\n"
        block = newline.join((AUDIT_IGNORE_START, AUDIT_IGNORE_RULE, AUDIT_IGNORE_END)) + newline
        return current + ("" if not current or current.endswith(("\n", "\r")) else newline) + block
    start, end_start = current.index(AUDIT_IGNORE_START), current.index(AUDIT_IGNORE_END)
    if start >= end_start:
        raise ValueError(".gitignore has duplicate or damaged Codex managed markers")
    if not remove:
        return current
    end = end_start + len(AUDIT_IGNORE_END)
    suffix = current[end:]
    if suffix.startswith("\r\n"):
        suffix = suffix[2:]
    elif suffix.startswith("\n"):
        suffix = suffix[1:]
    return current[:start] + suffix


def _install(root: Path) -> dict[str, object]:
    root = core._repo_root(root)
    agents = core._safe(root, "AGENTS.md")
    _managed_agents(_read_text(agents) if agents.is_file() else "")
    ignore = core._safe(root, ".gitignore")
    _audit_ignore(_read_text(ignore) if ignore.is_file() else "")
    with core._lock(root):
        writes: dict[str, bytes] = {}
        manual: list[str] = []
        current_agents = _read_text(agents) if agents.is_file() else ""
        rendered_agents = _managed_agents(current_agents)
        if current_agents != rendered_agents:
            writes["AGENTS.md"] = rendered_agents.encode("utf-8")
        role_packs = core._safe(root, "docs/thaliris-role-packs.md")
        if not role_packs.exists():
            writes["docs/thaliris-role-packs.md"] = ROLE_PACKS.encode("utf-8")
        current_ignore = _read_text(ignore) if ignore.is_file() else ""
        rendered_ignore = _audit_ignore(current_ignore)
        if current_ignore != rendered_ignore:
            writes[".gitignore"] = rendered_ignore.encode("utf-8")
        hooks = core._safe(root, ".codex/hooks.json")
        if hooks.exists():
            try:
                value = json.loads(_read_text(hooks))
                if not isinstance(value, dict):
                    raise ValueError("hooks root must be an object")
                merged, changed = merge_hooks(value)
                if changed:
                    writes[".codex/hooks.json"] = (json.dumps(merged, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            except (OSError, ValueError, json.JSONDecodeError):
                manual.append(".codex/hooks.json")
        else:
            merged, _ = merge_hooks({"description": MANAGED_HOOKS_DESCRIPTION})
            writes[".codex/hooks.json"] = (json.dumps(merged, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        if not writes:
            return {"ok": True, "changed": False, "backup": None, "files": [], "manual_migration_required": manual}
        return {"ok": True, "changed": True, "backup": core._apply_with_backup(root, writes, [], "codex-init"), "files": sorted(writes), "manual_migration_required": manual}


def _install_plan(root: Path) -> tuple[dict[str, bytes], list[str]]:
    """Plan Codex-owned files without taking a second lock or backup."""
    root = core._repo_root(root)
    agents = core._safe(root, "AGENTS.md")
    _managed_agents(_read_text(agents) if agents.is_file() else "")
    ignore = core._safe(root, ".gitignore")
    _audit_ignore(_read_text(ignore) if ignore.is_file() else "")
    writes: dict[str, bytes] = {}
    manual: list[str] = []
    current_agents = _read_text(agents) if agents.is_file() else ""
    rendered_agents = _managed_agents(current_agents)
    if current_agents != rendered_agents:
        writes["AGENTS.md"] = rendered_agents.encode("utf-8")
    role_packs = core._safe(root, "docs/thaliris-role-packs.md")
    if not role_packs.exists():
        writes["docs/thaliris-role-packs.md"] = ROLE_PACKS.encode("utf-8")
    current_ignore = _read_text(ignore) if ignore.is_file() else ""
    rendered_ignore = _audit_ignore(current_ignore)
    if current_ignore != rendered_ignore:
        writes[".gitignore"] = rendered_ignore.encode("utf-8")
    hooks = core._safe(root, ".codex/hooks.json")
    if hooks.exists():
        try:
            value = json.loads(_read_text(hooks))
            if not isinstance(value, dict):
                raise ValueError("hooks root must be an object")
            merged, changed = merge_hooks(value)
            if changed:
                writes[".codex/hooks.json"] = (json.dumps(merged, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        except (OSError, ValueError, json.JSONDecodeError):
            manual.append(".codex/hooks.json")
    else:
        merged, _ = merge_hooks({"description": MANAGED_HOOKS_DESCRIPTION})
        writes[".codex/hooks.json"] = (json.dumps(merged, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    return writes, manual


def init(root: Path) -> dict[str, object]:
    resolved = core._repo_root(root)
    agents = core._safe(resolved, "AGENTS.md")
    if agents.is_file():
        _managed_span(_read_text(agents), "AGENTS.md")
    ignore = core._safe(resolved, ".gitignore")
    if ignore.is_file():
        _audit_ignore(_read_text(ignore))
    root = core._repo_root(root)
    generic_files, generic_manual = core._init_plan(root)
    adapter_files, adapter_manual = _install_plan(root)
    # Both layers contribute ignored private paths. Compose the adapter's
    # addition over the Core-rendered .gitignore before the single mutation.
    if ".gitignore" in generic_files:
        adapter_files[".gitignore"] = _audit_ignore(generic_files[".gitignore"].decode("utf-8")).encode("utf-8")
    files = generic_files | adapter_files
    manual = sorted(set(generic_manual) | set(adapter_manual))
    with core._lock(root):
        backup = core._apply_with_backup(root, files, [], "init") if files else None
    return {"ok": True, "changed": bool(files), "backup": backup, "files": sorted(files), "manual_migration_required": manual}


def migrate(root: Path) -> dict[str, object]:
    root = core._repo_root(root)
    generic_files, generic_manual, migrated = core._migrate_plan(root)
    adapter_files, adapter_manual = _install_plan(root)
    if ".gitignore" in generic_files:
        adapter_files[".gitignore"] = _audit_ignore(generic_files[".gitignore"].decode("utf-8")).encode("utf-8")
    files = generic_files | adapter_files
    manual = sorted(set(generic_manual) | set(adapter_manual))
    with core._lock(root):
        backup = core._apply_with_backup(root, files, [], "migrate") if files else None
    return {"ok": True, "changed": bool(files), "backup": backup, "files": sorted(files), "migration": "v2", "migrated": migrated, "manual_migration_required": manual, "migration_backup": backup}


def _uninstall(root: Path) -> dict[str, object]:
    root = core._repo_root(root)
    agents = core._safe(root, "AGENTS.md")
    if agents.is_file():
        _managed_span(_read_text(agents), "AGENTS.md")
    ignore = core._safe(root, ".gitignore")
    if ignore.is_file():
        current_ignore = _read_text(ignore)
        _audit_ignore(current_ignore)
        core._managed_gitignore(current_ignore)
    audit_present = (root / ".context" / "audit").exists()
    with core._lock(root):
        writes: dict[str, bytes] = {}
        deletes: list[str] = []
        kept: list[str] = []
        manual: list[str] = []
        if agents.is_file():
            current = _read_text(agents)
            span = _managed_span(current, "AGENTS.md")
            if span is not None:
                start, end = span
                suffix = current[end:]
                if suffix.startswith("\r\n"):
                    suffix = suffix[2:]
                elif suffix.startswith("\n"):
                    suffix = suffix[1:]
                stripped = current[:start] + suffix
                if stripped:
                    writes["AGENTS.md"] = stripped.encode("utf-8")
                else:
                    deletes.append("AGENTS.md")
        if ignore.is_file() and not audit_present:
            current = _read_text(ignore)
            counts = (current.count(AUDIT_IGNORE_START), current.count(AUDIT_IGNORE_END))
            if counts == (0, 0) and current.count(core.LEGACY_IGNORE_START) == current.count(core.LEGACY_IGNORE_END) == 1:
                start = current.index(core.LEGACY_IGNORE_START)
                end = current.index(core.LEGACY_IGNORE_END) + len(core.LEGACY_IGNORE_END)
                suffix = current[end:]
                if suffix.startswith("\r\n"):
                    suffix = suffix[2:]
                elif suffix.startswith("\n"):
                    suffix = suffix[1:]
                rendered = current[:start] + suffix
            else:
                rendered = _audit_ignore(current, remove=True)
            if rendered != current:
                writes[".gitignore"] = rendered.encode("utf-8")
        packs = core._safe(root, "docs/thaliris-role-packs.md")
        if packs.is_file():
            if packs.read_bytes() == ROLE_PACKS.encode("utf-8"):
                deletes.append("docs/thaliris-role-packs.md")
            else:
                kept.append("docs/thaliris-role-packs.md")
        hooks = core._safe(root, ".codex/hooks.json")
        if hooks.is_file():
            try:
                value = json.loads(_read_text(hooks))
                if not isinstance(value, dict):
                    raise ValueError("hooks root must be an object")
                cleaned, changed = remove_hooks(value)
                if changed:
                    owned_empty = value.get("description") == MANAGED_HOOKS_DESCRIPTION and set(cleaned) <= {"description", "hooks"} and cleaned.get("description") == MANAGED_HOOKS_DESCRIPTION and cleaned.get("hooks", {}) == {}
                    if owned_empty:
                        deletes.append(".codex/hooks.json")
                    else:
                        writes[".codex/hooks.json"] = (json.dumps(cleaned, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            except (OSError, ValueError, json.JSONDecodeError):
                manual.append(".codex/hooks.json")
        if not writes and not deletes:
            return {"ok": True, "changed": False, "backup": None, "kept": kept, "manual_migration_required": manual}
        return {"ok": True, "changed": True, "backup": core._apply_with_backup(root, writes, deletes, "codex-uninstall"), "kept": kept, "manual_migration_required": manual}


def uninstall(root: Path) -> dict[str, object]:
    adapter = _uninstall(root)
    generic = core.uninstall(root)
    return {"ok": True, "changed": bool(adapter["changed"] or generic["changed"]), "backup": generic["backup"] or adapter["backup"], "kept": sorted(set(adapter.get("kept", [])) | set(generic.get("kept", []))), "manual_migration_required": sorted(set(adapter.get("manual_migration_required", [])) | set(generic.get("manual_migration_required", [])))}


def task_start(root: Path, goal: str, milestone: str | None, input_file: str | None, intent_capture_id: str | None = None) -> dict[str, object]:
    result = core.task_start(root, goal, milestone, input_file)
    try:
        bind_unbound_intent(core._repo_root(root), str(result["task_id"]), intent_capture_id)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass
    return result


def task_close(root: Path, base_revision: int) -> dict[str, object]:
    state = core.task_show(root)["state"]
    task_id = str(state["task_id"])
    try:
        audit = task_close_audit(core._repo_root(root), task_id, cleanup=False)
    except (OSError, ValueError, TypeError, subprocess.SubprocessError, json.JSONDecodeError):
        audit = {"status": "UNKNOWN"}
    if audit.get("status") == "DRIFT":
        return {"ok": False, "task_id": task_id, "revision": state["revision"], "status": state["status"], "changed": [], "intent_audit": {"status": "DRIFT", "finding": "Correct delegation scope before closing this task."}}
    result = core.task_close(root, base_revision, expected_task_id=task_id)
    try:
        cleanup_task_audit(core._repo_root(root), task_id, audit.get("status"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass
    return result


def audit_hook(root: Path, event: str, payload: object) -> str:
    return handle_hook(root, event, payload)


def doctor(root: Path) -> dict[str, object]:
    from .doctor import report
    return report(root)
