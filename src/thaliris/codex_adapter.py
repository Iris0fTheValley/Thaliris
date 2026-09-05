"""Codex-specific mapping for Thaliris Core projections and lifecycle hooks."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

from . import core
from .intent_audit import MANAGED_HOOKS_DESCRIPTION, bind_unbound_intent, cleanup_task_audit, handle_hook, merge_hooks, remove_hooks, task_close_audit

CODEX_ROLE_MAP = {
    "luna": "investigator", "luna-investigator": "investigator",
    "luna-curator": "curator", "sol-high": "reasoning-specialist",
    "terra-implementer": "implementer", "terra-reviewer": "reviewer",
    # Codex built-in profile compatibility aliases; these are not Core roles.
    "worker": "implementer", "explorer": "investigator",
}
# The adapter accepts the Core vocabulary as well as Codex's concrete aliases.
# This is a CLI ingress contract, not a second role registry: every value is
# immediately normalized by semantic_role() before it reaches Core.
ROLE_CHOICES = tuple(sorted(core._PACK_ROLES | set(CODEX_ROLE_MAP)))


def semantic_role(runtime_role: str) -> str:
    if runtime_role in {"controller", "investigator", "curator", "reasoning-specialist", "implementer", "reviewer"}:
        return runtime_role
    try:
        return CODEX_ROLE_MAP[runtime_role]
    except KeyError as exc:
        raise ValueError(f"unknown Codex role: {runtime_role}") from exc


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

During an active task the persistent root Controller is control-plane-only. Every new root child is a spawned execution child and must be fresh with `fork_turns=\"none\"`; non-none values are denied and must be retried explicitly. This means no parent-thread history, not an empty Codex context. The child obtains its own Thaliris role projection directly, performs the assigned work, avoids child-to-child delegation, and returns a bounded result to the Controller. Known local PreToolUse surfaces used by managed mode are mechanically guarded; hosted, specialized, and unverified runtime surfaces remain outside that envelope. PostToolUse records dispatch evidence. Use serial managed dispatch unless sibling isolation has been independently observed for the current Codex runtime. Codex owns execution; Thaliris has no worker, scheduler, polling loop, or lifecycle runtime.

Read detailed role packs only when needed. Keep raw findings, evidence, transcripts, logs, and tool output outside Controller packets and durable memory; promote only explicit durable decisions, constraints, invariants, failure modes, or material milestone progress.
{MANAGED_END}
"""

LEGACY_ROLE_PACKS = """# Thaliris Role Packs

Load this document when the compact managed router is insufficient.

## Controller

Use `context task-status` for task identity/status, active work, pending results, unresolved questions, artifact pointers, and accepted constraints/decisions. Raw findings, reviews, evidence records, Git state, and broad memory/milestone bodies do not belong in normal Controller routing. `context task-show` is diagnostic-only.

Every active task starts with one fresh execution child using `fork_turns=\"none\"`. The child receives or loads its own role pack directly; the parent Controller must not consume child-only working material. The Controller may then add Investigator, Curator, Reasoning Specialist, or Reviewer children only when the bounded result shows that role is needed. Use native completion/mailbox observation; there is no Thaliris worker, scheduler, polling loop, or retry runtime.

Codex hook configuration is separate from current-session observation. A project `.codex/hooks.json` proves only configuration; input rewriting, root classification, payload fidelity, and native task delivery remain `UNKNOWN` until a live compatible session observes them. Unknown tools and unverified MCP paths remain `UNKNOWN`/fail-open.
"""

ROLE_PACKS = """<!-- thaliris-role-packs:v2 -->
# Thaliris Role Packs

Load this document when the compact managed router is insufficient.

## Controller

The Controller routes work and accepts completion. It reads `context task-status`
for only task identity, active work, pending results, unresolved questions,
artifact pointers, and accepted constraints/decisions. It does not request raw
findings, review bodies, evidence records, Git status, or broad memory/milestone
bodies as part of normal routing. Use `context task-show` only for an explicit
diagnostic need.

Every active task uses serial fresh execution children with `fork_turns=\"none\"`.
This means no parent-thread history, not an empty Codex context: applicable
system/developer instructions, AGENTS, custom-agent instructions, environment,
native tool context, and delegation content may still be present. A non-none
fork is denied and must be retried explicitly. The child loads its own Thaliris
role projection directly, performs the assigned role, does not create
child-to-child workflow, and returns a bounded result to the persistent
Controller. The Controller must not consume child-only working material.
During an ACTIVE task the persistent Controller does not perform repository
investigation or source mutation; successful child dispatch does not change
those permissions. `task-close` requires a qualifying successful child
dispatch. PostToolUse keeps native dispatch evidence auditable.

For a local, obvious microtask, that one fresh Implementer is still required,
followed by deterministic verification; the persistent Controller does not edit
source directly. Larger work adds only the roles needed by risk and unknowns.
Wait for native completion or mailbox updates; Thaliris has no polling, worker,
retry, or scheduling runtime.

Known local PreToolUse surfaces used by managed mode are mechanically guarded.
This is automatic projection isolation, not filesystem confidentiality or
universal tool enforcement: hosted, specialized, and unverified runtime
surfaces remain outside the claimed envelope. Hook configuration is separate
from current-session observation; current hook-definition evidence is required
before claiming a live observation.

## Evidence Roles

Investigators append bounded findings and evidence references. Curators receive a
current snapshot and uncovered suffix only, then may replace the compact snapshot.
Reasoning Specialists receive accepted Decision Context rather than raw
investigation or review history. Implementers receive the explicit Modification
Boundary, including out-of-scope exclusions and required verification. If bounded
findings contain an unresolved architecture, provenance, or cross-module decision,
route only that Decision Context to `sol-high` rather than investigating at root.
Reviewers receive intent, changed surface, constraints, and decisions; their
findings are independent evidence, not an automatic implementation loop.

Use focused checks while changing code and one complete relevant validation at the
end. Requested runtime or visible-behavior verification remains required.

## State And Retention

`active_work` and `pending_results` are short controller-visible labels. Use
`context task-artifact --base-revision N --id ID --path repo/relative --summary TEXT`
to append a path-safe pointer to external work. Only the Controller registers
the pointer; pass `--producer-role` to record which child produced it. Artifact
contents remain outside the status packet and are never automatically injected
into another role. Raw task state remains diagnostic-only in `.context/state.json`.

Artifact registration does not hide a path from review: Reviewer `Changed Surface`
continues to show Git-reported changes, without automatically exposing file contents.

At task end, promote only reusable decisions, constraints, invariants, failure
modes, and material milestone progress or completed verification through
`context task-promote`. Route memory and milestones through their INDEX files;
do not treat this layer as a scheduler, transcript store, or automatic summary.
"""


def _effective_agents_path(root: Path) -> Path:
    """Return Codex's root instruction winner; never silently write a shadowed file."""
    override = core._safe(root, "AGENTS.override.md")
    return override if override.is_file() else core._safe(root, "AGENTS.md")


def _strip_managed_agents(current: str) -> str:
    span = _managed_span(current, "AGENTS.md")
    if span is None:
        return current
    start, end = span
    suffix = current[end:]
    if suffix.startswith("\r\n"):
        suffix = suffix[2:]
    elif suffix.startswith("\n"):
        suffix = suffix[1:]
    return current[:start] + suffix


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
    user_text = _strip_managed_agents(current) if span is not None else current
    return block if not user_text else block + newline + user_text


def _role_pack_state(value: bytes) -> str:
    try:
        text = value.decode("utf-8").replace("\r\n", "\n")
    except UnicodeDecodeError:
        return "user"
    if text == ROLE_PACKS:
        return "current"
    if text == LEGACY_ROLE_PACKS:
        return "legacy"
    # This is the previous adapter-owned generated document. Its old fork
    # rewrite wording identifies it precisely enough to upgrade without
    # overwriting arbitrary user role notes.
    if (
        text.startswith("# Thaliris Role Packs\n")
        and "A positive fork is rewritten to `none`;" in text
        and "## Evidence Roles\n" in text
        and "## State And Retention\n" in text
    ):
        return "legacy"
    return "user"


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
    writes, manual = _install_plan(root)
    with core._lock(root):
        if not writes:
            return {"ok": True, "changed": False, "backup": None, "files": [], "manual_migration_required": manual, "hook_definition_changed": False, "hook_trust_required": False}
        hook_changed = ".codex/hooks.json" in writes
        return {"ok": True, "changed": True, "backup": core._apply_with_backup(root, writes, [], "codex-init"), "files": sorted(writes), "manual_migration_required": manual, "hook_definition_changed": hook_changed, "hook_trust_required": hook_changed}


def _install_plan(root: Path) -> tuple[dict[str, bytes], list[str]]:
    """Plan Codex-owned files without taking a second lock or backup."""
    root = core._repo_root(root)
    target_agents = _effective_agents_path(root)
    all_agents = (core._safe(root, "AGENTS.md"), core._safe(root, "AGENTS.override.md"))
    for agents in all_agents:
        if agents.is_file():
            _managed_span(_read_text(agents), agents.name)
    ignore = core._safe(root, ".gitignore")
    _audit_ignore(_read_text(ignore) if ignore.is_file() else "")
    writes: dict[str, bytes] = {}
    manual: list[str] = []
    current_agents = _read_text(target_agents) if target_agents.is_file() else ""
    rendered_agents = _managed_agents(current_agents)
    if current_agents != rendered_agents:
        writes[target_agents.relative_to(root).as_posix()] = rendered_agents.encode("utf-8")
    # If an override became active after an earlier install, remove only our
    # now-shadowed block from the inactive root file.
    for agents in all_agents:
        if agents == target_agents or not agents.is_file():
            continue
        current = _read_text(agents)
        stripped = _strip_managed_agents(current)
        if stripped != current:
            writes[agents.relative_to(root).as_posix()] = stripped.encode("utf-8")
    role_packs = core._safe(root, "docs/thaliris-role-packs.md")
    if not role_packs.exists():
        writes["docs/thaliris-role-packs.md"] = ROLE_PACKS.encode("utf-8")
    elif _role_pack_state(role_packs.read_bytes()) == "legacy":
        writes["docs/thaliris-role-packs.md"] = ROLE_PACKS.encode("utf-8")
    elif _role_pack_state(role_packs.read_bytes()) == "user":
        manual.append("docs/thaliris-role-packs.md")
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
    for agents in (core._safe(resolved, "AGENTS.md"), core._safe(resolved, "AGENTS.override.md")):
        if agents.is_file():
            _managed_span(_read_text(agents), agents.name)
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
    hook_changed = ".codex/hooks.json" in files
    return {"ok": True, "changed": bool(files), "backup": backup, "files": sorted(files), "manual_migration_required": manual, "hook_definition_changed": hook_changed, "hook_trust_required": hook_changed}


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
    hook_changed = ".codex/hooks.json" in files
    return {"ok": True, "changed": bool(files), "backup": backup, "files": sorted(files), "migration": "v2", "migrated": migrated, "manual_migration_required": manual, "migration_backup": backup, "hook_definition_changed": hook_changed, "hook_trust_required": hook_changed}


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


def _adapter_uninstall_plan(root: Path) -> tuple[dict[str, bytes], list[str], list[str], list[str]]:
    agent_paths = (core._safe(root, "AGENTS.md"), core._safe(root, "AGENTS.override.md"))
    ignore = core._safe(root, ".gitignore")
    for agents in agent_paths:
        if agents.is_file():
            _managed_span(_read_text(agents), agents.name)
    if ignore.is_file():
        _audit_ignore(_read_text(ignore))
    writes: dict[str, bytes] = {}
    deletes: list[str] = []
    kept: list[str] = []
    manual: list[str] = []
    for agents in agent_paths:
        if not agents.is_file():
            continue
        current = _read_text(agents)
        span = _managed_span(current, agents.name)
        if span is not None:
            stripped = _strip_managed_agents(current)
            name = agents.relative_to(root).as_posix()
            if stripped:
                writes[name] = stripped.encode("utf-8")
            else:
                deletes.append(name)
    audit_present = (root / ".context" / "audit").exists()
    if ignore.is_file() and not audit_present:
        current = _read_text(ignore)
        rendered = _audit_ignore(current, remove=True)
        if rendered != current:
            writes[".gitignore"] = rendered.encode("utf-8")
    packs = core._safe(root, "docs/thaliris-role-packs.md")
    if packs.is_file():
        if _role_pack_state(packs.read_bytes()) in {"current", "legacy"}:
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
    return writes, deletes, kept, manual


def uninstall(root: Path) -> dict[str, object]:
    root = core._repo_root(root)
    adapter = _adapter_uninstall_plan(root)
    generic_writes, generic_deletes, generic_kept, generic_manual = core._uninstall_plan(root)
    writes = generic_writes | adapter[0]
    deletes = sorted(set(generic_deletes) | set(adapter[1]))
    with core._lock(root):
        backup = core._apply_with_backup(root, writes, deletes, "uninstall") if writes or deletes else None
    return {"ok": True, "changed": bool(writes or deletes), "backup": backup, "kept": sorted(set(generic_kept) | set(adapter[2])), "manual_migration_required": sorted(set(generic_manual) | set(adapter[3]))}


def task_start(root: Path, goal: str, milestone: str | None, input_file: str | None, intent_capture_id: str | None = None) -> dict[str, object]:
    result = core.task_start(root, goal, milestone, input_file)
    try:
        bind_unbound_intent(core._repo_root(root), str(result["task_id"]), intent_capture_id)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass
    return result


def child_bootstrap(role: str) -> str:
    """Return the minimal native task instruction for a fresh execution child.

    The parent sends this marker as the delegation task. The child loads its
    own projection in its own session; the parent never preloads child-only
    pack content.
    """
    role = semantic_role(role)
    if role not in core._PACK_ROLES or role == "controller":
        raise ValueError("child role must be an execution role")
    return f"Obtain your Thaliris role context by running `context prepare --role {role}` in this fresh child, then perform the assigned task and return a bounded result. Do not delegate to another child."


def prepare_child(root: Path, role: str) -> dict[str, object]:
    """Load a role projection from inside the child runtime boundary."""
    role = semantic_role(role)
    if role not in core._PACK_ROLES or role == "controller":
        raise ValueError("child role must be an execution role")
    return core.prepare(root, None, role)


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
