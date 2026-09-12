"""Codex adapter for explicit handoff delivery and native lifecycle hooks."""
from __future__ import annotations

import json
import hashlib
from functools import lru_cache
import os
from pathlib import Path
import re
import subprocess
import tomllib

from . import core, lifecycle
from .lifecycle import MANAGED_HOOKS_DESCRIPTION, handle_hook, merge_hooks, remove_hooks

CODEX_ROLE_MAP = {
    "luna": "investigator", "luna-investigator": "investigator",
    "luna-curator": "curator", "sol-high": "reasoning-specialist",
    "terra-implementer": "implementer", "terra-reviewer": "reviewer",
    "thaliris-investigator": "investigator", "thaliris-curator": "curator",
    "thaliris-reasoning-specialist": "reasoning-specialist",
    "thaliris-implementer": "implementer", "thaliris-reviewer": "reviewer",
    # Codex built-in profile compatibility aliases; these are not Core roles.
    "worker": "implementer", "explorer": "investigator",
}
# The adapter accepts the Core vocabulary as well as Codex's concrete aliases.
# This is a CLI ingress contract, not a second role registry: every value is
# immediately normalized by semantic_role() before it reaches Core.
ROLE_CHOICES = tuple(sorted(core._PACK_ROLES | set(CODEX_ROLE_MAP)))

_AGENT_PROFILES = {
    "thaliris-investigator.toml": ("gpt-5.6-luna", "medium", "investigator"),
    "thaliris-curator.toml": ("gpt-5.6-luna", "medium", "curator"),
    "thaliris-reasoning-specialist.toml": ("gpt-5.6-sol", "xhigh", "reasoning-specialist"),
    "thaliris-implementer.toml": ("gpt-5.6-terra", "medium", "implementer"),
    "thaliris-reviewer.toml": ("gpt-5.6-terra", "high", "reviewer"),
}
_NATIVE_PROFILE_NAMES = frozenset(name.removesuffix(".toml") for name in _AGENT_PROFILES)
_KNOWN_HOST_WAIT_CAPABILITIES = {
    # These are release-pinned observations, not a cross-version assumption.
    "0.153.4": {"min": 10_000, "default": 30_000, "max": 3_600_000, "explicit_timeout_supported": True, "native_completion_reenters_root": "UNSUPPORTED"},
}


def _agent_profile(name: str, role: str, model: str, effort: str) -> bytes:
    shared = (
        "The Controller's explicit native spawn message is your sole task-specific input. "
        "Do not run context prepare to reconstruct task state, and do not infer unselected "
        "memory, milestone, Artifact, finding, decision, or review content. Keep repository "
        "reads, tool output, test logs, and intermediate exploration in your private working "
        "set. Return a distilled result with Conclusion, Key findings, Decision-changing "
        "unknowns, Contradictions if any, Verification performed, and Artifact refs if detailed "
        "reusable material was retained. Do not delegate to another child. "
    )
    role_instruction = {
        "investigator": (
            "Investigate the bounded handoff. You may save detailed reusable material as a "
            "repo-relative Artifact; return only its pointer and the distilled result by default."
        ),
        "curator": (
            "Compress or reconcile only the material explicitly supplied in the handoff. "
            "Your output is an ordinary result or Artifact; there is no Curator Core state."
        ),
        "reasoning-specialist": (
            "Resolve the selected decision from the supplied information. If a decision-changing "
            "fact is missing, identify it without reconstructing unselected task history."
        ),
        "implementer": (
            "Implement only the bounded change in the handoff and report verification as "
            "observations; Core does not supply semantic completion authority."
        ),
        "reviewer": (
            "Act as an independent read-only checker of the candidate named in the handoff. "
            "Return findings and a distilled verdict; the Controller decides what follows."
        ),
    }[role]
    instructions = shared + role_instruction
    return (
        f'name = "{name}"\n'
        f'description = "Thaliris {role} execution role"\n'
        f'model = "{model}"\n'
        f'model_reasoning_effort = "{effort}"\n'
        + ('sandbox_mode = "read-only"\n' if role == "reviewer" else "")
        + f'developer_instructions = "{instructions}"\n'
    ).encode("utf-8")


def _agent_profile_state(value: bytes, name: str) -> str:
    profile = _AGENT_PROFILES.get(name)
    if profile is None:
        return "user"
    expected = _agent_profile(name.removesuffix(".toml"), profile[2], profile[0], profile[1])
    return "current" if value == expected else "user"


def _profile_definition_present(root: Path) -> str:
    return "YES" if all((root / ".codex" / "agents" / name).is_file() for name in _AGENT_PROFILES) else "NO"


def _activation_fields(
    root: Path,
    profile_native_active: str = "UNKNOWN",
    project_layer_activation: str = "UNKNOWN",
    compatible_profile_observed: str = "UNKNOWN",
    compatible_project_hooks_observed: str = "UNKNOWN",
) -> dict[str, str]:
    return {
        "profile_definition_present": _profile_definition_present(root),
        "profile_native_active": profile_native_active,
        "project_layer_activation": project_layer_activation,
        "compatible_profile_observed": compatible_profile_observed,
        "compatible_project_hooks_observed": compatible_project_hooks_observed,
    }


def semantic_role(runtime_role: str) -> str:
    if runtime_role in {"controller", "investigator", "curator", "reasoning-specialist", "implementer", "reviewer"}:
        return runtime_role
    try:
        return CODEX_ROLE_MAP[runtime_role]
    except KeyError as exc:
        raise ValueError(f"unknown Codex role: {runtime_role}") from exc


@lru_cache(maxsize=8)
def _host_wait_mode_cached(runner: str) -> dict[str, object]:
    """Return a conservative, version-bound wait capability for this host."""
    try:
        completed = subprocess.run([runner, "--version"], capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return {"status": "UNSUPPORTED", "version": "UNKNOWN", "reason": "Codex executable is unavailable"}
    match = re.search(r"(?:codex(?:-cli)?\s+)?(\d+\.\d+\.\d+)", (completed.stdout or "") + (completed.stderr or ""))
    if completed.returncode != 0 or match is None:
        return {"status": "UNSUPPORTED", "version": "UNKNOWN", "reason": "Codex version could not be determined"}
    version = match.group(1)
    capability = _KNOWN_HOST_WAIT_CAPABILITIES.get(version)
    if capability is None:
        return {"status": "UNSUPPORTED", "version": version, "reason": "no version-pinned wait capability is recorded for this Codex host"}
    return {"status": "PASS", "version": version, **capability}


def host_wait_mode(executable: str | None = None) -> dict[str, object]:
    return dict(_host_wait_mode_cached(executable or os.environ.get("THALIRIS_CODEX_EXECUTABLE") or "codex"))


def host_explicit_blocking_wait(executable: str | None = None) -> dict[str, object]:
    """Return version-pinned support for an explicit, bounded native wait.

    This is a Host tool contract, not project configuration.  An explicit
    ``timeout_ms`` reaches the native wait primitive in the current tool call,
    so it neither relies on a default nor requires a session reload.
    """
    host = host_wait_mode(executable)
    if host.get("status") != "PASS":
        status = "UNSUPPORTED" if host.get("version") == "UNKNOWN" else "UNKNOWN"
        return {"status": status, "host": host}
    if host.get("explicit_timeout_supported") is not True:
        return {"status": "UNSUPPORTED", "host": host}
    return {
        "status": "PASS",
        "version": host["version"],
        "min_wait_timeout_ms": host["min"],
        "default_wait_timeout_ms": host["default"],
        "max_wait_timeout_ms": host["max"],
        "explicit_timeout_supported": True,
    }


def native_child_completion_reenters_root(executable: str | None = None) -> str:
    """Return only PASS, UNSUPPORTED, or UNKNOWN for native re-entry."""
    capability = host_wait_mode(executable)
    result = capability.get("native_completion_reenters_root")
    return result if result in {"PASS", "UNSUPPORTED", "UNKNOWN"} else "UNKNOWN"


def selected_continuation_mode(root: Path, executable: str | None = None) -> str:
    continuation = native_child_completion_reenters_root(executable)
    if continuation == "PASS":
        return "EVENT_DRIVEN"
    if host_explicit_blocking_wait(executable).get("status") == "PASS":
        return "BLOCKING_WAIT"
    return "UNAVAILABLE"


def _read_text(path: Path) -> str:
    return path.read_bytes().decode("utf-8")

MANAGED_START = "<!-- thaliris:begin -->"
MANAGED_END = "<!-- thaliris:end -->"
AUDIT_IGNORE_START = "# thaliris-codex:begin"
AUDIT_IGNORE_END = "# thaliris-codex:end"
AUDIT_IGNORE_RULE = ".context/audit/"

MANAGED = f"""{MANAGED_START}
## Thaliris Router

Codex is the runtime. Thaliris provides durable records, identities, revisions,
hashes, provenance, objective freshness observations, explicit retrieval, and
native lifecycle binding. It is not a semantic decision engine.

The Controller is the sole task-specific semantic router. Every root child is
fresh (`fork_turns="none"`) and receives its task plus selected information in
the Controller's native spawn message. `SubagentStart` validates authorization,
identity, role, and session and binds lifecycle metadata; it never calls Core to
construct or inject task context. Task state, memory, milestones, prior reviews,
and Artifact bodies never enter a child automatically.

A Child keeps its investigation, tool output, tests, and intermediate working
set private. By default it returns a distilled conclusion, key findings,
decision-changing unknowns or contradictions, verification performed, and
optional Artifact pointers. Detailed reusable material may be saved in a
repo-relative Artifact. The Controller decides whether to register or retrieve
it and whether any selected content belongs in a later handoff. Artifact
registration stores address, producer, revision, hash, provenance, and optional
supersession only; it does not interpret the body.

Memory and milestones are ordinary explicit storage. Search results and
Audience, Topics, Symbols, Applicability, Kind, Status, and Confidence metadata
are hints for models and displays, never routing permissions or correctness
gates. Freshness reports only FRESH, CHANGED, MISSING, or UNKNOWN facts.

Managed children are serial. Spawn authorization, native identity binding,
SubagentStart/Stop, missing-stop reconciliation, and explicit blocking waits are
mechanical. A short native wait is normalized to the host maximum only while an
authorized reservation or managed child is actually pending. The Controller
interprets Child results, verification observations, review findings, and task
surface deltas and decides the next handoff and when work is complete.
{MANAGED_END}
"""

ROLE_PACKS = """<!-- thaliris-role-packs:v4 -->
# Thaliris Role Profiles

These profiles are working-style defaults, not routing rules or semantic
permissions. The Controller's explicit native spawn message is the sole
task-specific input to every Child.

## Shared Child Result

Return a distilled result by default:

- Conclusion
- Key findings
- Decision-changing unknowns
- Contradictions, if any
- Verification performed
- Artifact refs, if detailed reusable material was retained

Keep repository reads, tool output, test logs, and intermediate exploration in
the Child's private working set. Do not copy an Artifact body into the result
unless the Controller explicitly requested that content.

## Investigator

Investigate the bounded task in the handoff. Save detailed reusable evidence as
an optional repo-relative Artifact and return its pointer with a short result.

## Curator

Optionally compress or reconcile only the material explicitly supplied by the
Controller. Curator output is an ordinary result or Artifact; Core has no
Curator state machine.

## Reasoning Specialist

Resolve the decision described in the handoff from the selected information.
If a decision-changing fact is missing, say what is missing. Do not reconstruct
unselected task history.

## Implementer

Implement the bounded change in the handoff, preserve stated constraints, and
report verification as observations. Do not infer additional task state from
Core.

## Reviewer

Independently inspect the candidate identified in the handoff. Return findings
and a distilled verdict. Finding classifications are model-authored labels; the
Controller decides what workflow, if any, follows.
"""

def _codex_config() -> dict[str, object]:
    base = Path(os.environ["CODEX_HOME"]) if os.environ.get("CODEX_HOME") else Path.home() / ".codex"
    path = base / "config.toml"
    if not path.is_file():
        return {}
    try:
        value = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _fallback_instruction_names(codex_config: dict[str, object] | None = None) -> tuple[str, ...]:
    value = (codex_config or _codex_config()).get("project_doc_fallback_filenames")
    if not isinstance(value, list):
        return ()
    names: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item or Path(item).name != item or item in names:
            continue
        names.append(item)
    return tuple(names)


def _root_instruction_candidates(root: Path, codex_config: dict[str, object] | None = None) -> tuple[Path, ...]:
    names = ("AGENTS.override.md", "AGENTS.md", *_fallback_instruction_names(codex_config))
    return tuple(core._safe(root, name) for name in names)


def _effective_root_instruction_path(root: Path, codex_config: dict[str, object] | None = None) -> Path:
    """Match Codex root discovery: first non-empty candidate wins.

    The adapter intentionally manages only the repository-root layer, not the
    full root-to-cwd instruction hierarchy.
    """
    candidates = _root_instruction_candidates(root, codex_config)
    for path in candidates:
        if path.is_file() and _read_text(path).strip():
            return path
    return core._safe(root, "AGENTS.md")


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
    counts = current.count(MANAGED_START), current.count(MANAGED_END)
    if counts == (0, 0):
        return None
    if counts == (1, 1):
        start, end_start = current.index(MANAGED_START), current.index(MANAGED_END)
        end = end_start + len(MANAGED_END)
    else:
        raise ValueError(f"{label} has duplicate or damaged managed markers")
    if start >= end_start:
        raise ValueError(f"{label} has duplicate or damaged managed markers")
    return start, end


def _managed_agents(current: str) -> str:
    span = _managed_span(current, "AGENTS.md")
    newline = "\r\n" if "\r\n" in current else "\n"
    block = MANAGED.replace("\n", newline)
    user_text = _strip_managed_agents(current) if span is not None else current
    return block if not user_text else block + user_text


def _role_pack_state(value: bytes) -> str:
    return "current" if value == ROLE_PACKS.encode("utf-8") else "user"


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


def _install_plan(root: Path) -> tuple[dict[str, bytes], list[str]]:
    """Plan Codex-owned files without taking a second lock or backup."""
    root = core._repo_root(root)
    codex_config = _codex_config()
    target_agents = _effective_root_instruction_path(root, codex_config)
    all_agents = _root_instruction_candidates(root, codex_config)
    for instruction in all_agents:
        if instruction.is_file():
            _managed_span(_read_text(instruction), instruction.name)
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
    for instruction in all_agents:
        if instruction == target_agents or not instruction.is_file():
            continue
        current = _read_text(instruction)
        stripped = _strip_managed_agents(current)
        if stripped != current:
            writes[instruction.relative_to(root).as_posix()] = stripped.encode("utf-8")
    role_packs = core._safe(root, "docs/thaliris-role-packs.md")
    if not role_packs.exists():
        writes["docs/thaliris-role-packs.md"] = ROLE_PACKS.encode("utf-8")
    elif _role_pack_state(role_packs.read_bytes()) == "user":
        manual.append("docs/thaliris-role-packs.md")
    for name, (model, effort, role) in _AGENT_PROFILES.items():
        relative = f".codex/agents/{name}"
        profile = core._safe(root, relative)
        rendered = _agent_profile(name.removesuffix(".toml"), role, model, effort)
        if not profile.exists():
            writes[relative] = rendered
        elif _agent_profile_state(profile.read_bytes(), name) == "user":
            manual.append(relative)
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
    # Explicit timeout_ms normalization controls managed waits in the current
    # native call. Do not create or depend on project config defaults.
    return writes, manual


def init(root: Path) -> dict[str, object]:
    resolved = core._repo_root(root)
    for instruction in _root_instruction_candidates(resolved):
        if instruction.is_file():
            _managed_span(_read_text(instruction), instruction.name)
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
    instruction_changed = any(path in {"AGENTS.md", "AGENTS.override.md"} for path in files)
    profile_changed = any(path.startswith(".codex/agents/") for path in files)
    return {"ok": True, "changed": bool(files), "backup": backup, "files": sorted(files), "manual_action_required": manual, "instruction_definition_changed": instruction_changed, "hook_definition_changed": hook_changed, "agent_profile_changed": profile_changed, "session_restart_required": instruction_changed or hook_changed or profile_changed, "hook_trust_required": hook_changed, "host_wait_mode": host_wait_mode(), **_activation_fields(root)}


def _adapter_uninstall_plan(root: Path) -> tuple[dict[str, bytes], list[str], list[str], list[str]]:
    agent_paths = _root_instruction_candidates(root)
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
        if _role_pack_state(packs.read_bytes()) == "current":
            deletes.append("docs/thaliris-role-packs.md")
        else:
            kept.append("docs/thaliris-role-packs.md")
    for name in _AGENT_PROFILES:
        relative = f".codex/agents/{name}"
        profile = core._safe(root, relative)
        if not profile.is_file():
            continue
        state = _agent_profile_state(profile.read_bytes(), name)
        if state == "current":
            deletes.append(relative)
        else:
            kept.append(relative)
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
    return {"ok": True, "changed": bool(writes or deletes), "backup": backup, "kept": sorted(set(generic_kept) | set(adapter[2])), "manual_action_required": sorted(set(generic_manual) | set(adapter[3]))}


def task_start(root: Path, goal: str, milestone: str | None, input_file: str | None) -> dict[str, object]:
    root = core._repo_root(root)
    mode = selected_continuation_mode(root)
    readiness = {
        "status": "PASS" if mode in {"EVENT_DRIVEN", "BLOCKING_WAIT"} else "MANAGED_CONTINUATION_UNAVAILABLE",
        "NATIVE_CHILD_COMPLETION_REENTERS_ROOT": native_child_completion_reenters_root(),
        "HOST_EXPLICIT_BLOCKING_WAIT": host_explicit_blocking_wait().get("status"),
        "selected_continuation_mode": mode,
    }
    if mode == "UNAVAILABLE":
        return {"ok": False, "status": "MANAGED_CONTINUATION_UNAVAILABLE", "managed_readiness": readiness}
    result = core.task_start(root, goal, milestone, input_file)
    # A task is a Core object.  Starting one cannot prove that this already
    # running Codex session reloaded project hooks, AGENTS, or agent profiles.
    result["managed_readiness"] = {**readiness, **_activation_fields(root)}
    return result


def task_close(root: Path, base_revision: int) -> dict[str, object]:
    state = core.task_show(root)["state"]
    task_id = str(state["task_id"])
    if not lifecycle.qualifying_child_completed(core._repo_root(root)):
        raise ValueError("task-close requires an authorized explicit handoff, a matching native SubagentStart/Stop identity, and no pending or active managed work")
    return core.task_close(root, base_revision, expected_task_id=task_id)


def audit_hook(root: Path, event: str, payload: object) -> str:
    result = handle_hook(root, event, payload)
    if result or event != "PreToolUse" or not isinstance(payload, dict):
        return result
    if payload.get("agent_id") is not None:
        return ""
    root = core._repo_root(root)
    tool = payload.get("tool_name") or payload.get("tool")
    if not isinstance(tool, str) or lifecycle._tool_basename(tool) != "wait_agent":
        return ""
    if (
        lifecycle._active_task_id(root) is None
        or selected_continuation_mode(root) != "BLOCKING_WAIT"
        or not lifecycle.managed_dependency_pending(root)
    ):
        return ""
    capability = host_explicit_blocking_wait()
    if capability.get("status") != "PASS":
        return ""
    original = payload.get("tool_input")
    if not isinstance(original, dict):
        return ""
    target = int(capability["max_wait_timeout_ms"])
    if original.get("timeout_ms") == target:
        return ""
    # Copy rather than reconstruct: future native arguments survive unchanged.
    updated = dict(original)
    updated["timeout_ms"] = target
    return json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "allow",
        "updatedInput": updated,
    }}, ensure_ascii=False, separators=(",", ":"))


def doctor(root: Path) -> dict[str, object]:
    from .doctor import report
    root = core._repo_root(root)
    result = report(root)
    observations: list[tuple[int, int, dict[str, object]]] = []
    events: set[str] = set()
    compatible_profile_observed = False
    orchestration = {"wait_calls": 0, "wait_timeouts": 0, "list_agents_calls": 0, "blocked_spawn_calls": 0, "reconciliation_attempts": 0, "reconciliation_successes": 0, "reviewer_rounds": 0, "implementer_rounds": 0}
    expected = lifecycle.managed_hook_spec_hash()
    for path in (root / ".context" / "audit").glob("*/runtime.json"):
        try:
            runtime = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        current = isinstance(runtime, dict) and runtime.get("managed_hook_spec_hash") == expected and runtime.get("adapter_protocol_version") == lifecycle.CODEX_ADAPTER_PROTOCOL_VERSION
        samples = runtime.get("execution_observations") if current else None
        if current and isinstance(runtime.get("events_observed"), dict):
            events.update(name for name, observed in runtime["events_observed"].items() if observed is True)
        if current and isinstance(runtime.get("subagent_start_agent_types"), list):
            compatible_profile_observed = compatible_profile_observed or any(
                isinstance(value, str) and value in _NATIVE_PROFILE_NAMES
                for value in runtime["subagent_start_agent_types"]
            )
        if isinstance(samples, list):
            observations.extend((int(runtime.get("observed_at_ns", 0)), int(runtime.get("observation_sequence", 0)), item) for item in samples if isinstance(item, dict))
        metrics = runtime.get("orchestration_metrics") if current else None
        if isinstance(metrics, dict):
            orchestration["wait_calls"] += int(metrics.get("wait_agent_calls", 0))
            orchestration["wait_timeouts"] += int(metrics.get("wait_timeouts", 0))
            orchestration["list_agents_calls"] += int(metrics.get("list_agents_calls", 0))
    latest = max(observations, default=None, key=lambda item: (item[0], item[1]))
    latest_item = latest[2] if latest is not None else None
    health = lifecycle.hooks_health(root)
    lifecycle_start = lifecycle_stop = lifecycle_reconciled = False
    reconciliation_attempts = reconciliation_successes = 0
    for path in (root / ".context" / "audit" / "lifecycle").glob("*.json"):
        try:
            lifecycle_state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(lifecycle_state, dict) or lifecycle_state.get("version") != lifecycle.LIFECYCLE_STATE_VERSION or lifecycle_state.get("managed_hook_spec_hash") != expected or lifecycle_state.get("adapter_protocol_version") != lifecycle.CODEX_ADAPTER_PROTOCOL_VERSION:
            continue
        for child in lifecycle_state.get("children", []):
            if isinstance(child, dict) and isinstance(child.get("started"), int):
                lifecycle_start = True
                lifecycle_stop = lifecycle_stop or isinstance(child.get("stopped"), int)
                lifecycle_reconciled = lifecycle_reconciled or child.get("terminal_state") == "NATIVE_TERMINAL_RECONCILED"
                if child.get("role") == "reviewer":
                    orchestration["reviewer_rounds"] += 1
                elif child.get("role") == "implementer":
                    orchestration["implementer_rounds"] += 1
        metrics = lifecycle_state.get("metrics")
        if isinstance(metrics, dict):
            reconciliation_attempts += int(metrics.get("reconciliation_attempts", 0))
            reconciliation_successes += int(metrics.get("reconciliation_successes", 0))
            orchestration["blocked_spawn_calls"] += int(metrics.get("blocked_spawn_calls", 0))
    result["verification_attestation"] = {
        "hook_definition_present": health["hooks_configured"],
        "hook_definition_current": health["hooks_configured"],
        # Stored observations are intentionally useful diagnostics, but they
        # cannot prove that the session asking for this doctor report loaded
        # the current project definitions.
        "current_session_observed": "UNKNOWN",
        "adapter_protocol_current": "YES" if events or latest is not None else "UNKNOWN",
        "verification_shell_surface": "Bash",
        "verification_terminal_status": "UNAVAILABLE",
        "observed_outcome": latest_item.get("outcome") if latest_item is not None else "UNKNOWN",
        "hook_trust": "UNKNOWN",
        "detail": "Codex 0.153.4 Bash output has no version-pinned terminal-status contract; no automatic PASSED attestation is emitted.",
    }
    result["managed_readiness"] = {
        "CORE_READY": "YES",
        "CODEX_DEFINITION_PRESENT": health["hooks_configured"],
        "CODEX_RUNTIME_OBSERVED": health["runtime_observed"],
        "CURRENT_SESSION_OBSERVED": "UNKNOWN",
        "CODEX_MANAGED_READY": "UNKNOWN",
        "spawn_pretool_observed": "YES" if "PreToolUse" in events else "UNKNOWN",
        "subagent_start_observed": "YES" if lifecycle_start else "UNKNOWN",
        "subagent_stop_observed": "YES" if lifecycle_stop else "UNKNOWN",
        "explicit_handoff_binding_observed": "YES" if lifecycle_start else "UNKNOWN",
        "controller_activation_bridge": "CODEX_NATIVE",
        "NATIVE_CHILD_COMPLETION_REENTERS_ROOT": native_child_completion_reenters_root(),
        "HOST_EXPLICIT_BLOCKING_WAIT": host_explicit_blocking_wait().get("status"),
        "BLOCKING_WAIT_MODE": "PASS" if selected_continuation_mode(root) == "BLOCKING_WAIT" else "FAIL",
        "selected_continuation_mode": selected_continuation_mode(root),
        **_activation_fields(
            root,
            profile_native_active="UNKNOWN",
            project_layer_activation="UNKNOWN",
            compatible_profile_observed="YES" if compatible_profile_observed else "UNKNOWN",
            compatible_project_hooks_observed="YES" if events else "UNKNOWN",
        ),
    }
    # Keep configuration discovery separate from live host observations.  A
    # local hooks.json or trusted project entry cannot stand in for a native
    # hook run, a deny, or a Reviewer sandbox observation.
    host = result.get("host_capability") if isinstance(result.get("host_capability"), dict) else {}
    host.update({
        "hook_runtime_observed": "YES" if events else "UNKNOWN",
        "controller_pretool_observed": "YES" if "PreToolUse" in events else "UNKNOWN",
        "subagent_lifecycle_observed": "YES" if lifecycle_start and lifecycle_stop else "UNKNOWN",
        "hook_hash_match": "YES" if events else host.get("hook_hash_match", "UNKNOWN"),
        "hook_trust_status": "UNKNOWN",
        "controller_deny_observed": "UNKNOWN",
        "controller_side_effect_prevented": "UNKNOWN",
        "reviewer_native_readonly_observed": "UNKNOWN",
        "trusted_runtime_isolation_observed": "UNKNOWN",
    })
    result["host_capability"] = host
    posttool_schema = "PASS" if host_wait_mode().get("status") == "PASS" else "UNKNOWN"
    result["lifecycle_reconciliation"] = {
        "subagent_stop_path": "PASS" if lifecycle_stop else "UNKNOWN",
        # 0.153.4 supplies these shapes in its version-pinned schemas, but a
        # project hook must observe a real payload before this is a live PASS.
        "native_terminal_reconciliation": "PASS" if lifecycle_reconciled else ("LIVE_NOT_OBSERVED" if posttool_schema == "PASS" else "UNKNOWN"),
        "PostToolUse_source_schema_support": posttool_schema,
        "PostToolUse_live_project_hook": "PASS" if events else "LIVE_NOT_OBSERVED",
        "reconciliation_attempts": reconciliation_attempts,
        "reconciliation_successes": reconciliation_successes,
    }
    orchestration["reconciliation_attempts"] = reconciliation_attempts
    orchestration["reconciliation_successes"] = reconciliation_successes
    result["cost_regression"] = {
        # This Hook surface has no model-turn/token/context counter.  Leaving
        # these unavailable is safer than deriving model cost from wait calls.
        "root_model_activations": "UNAVAILABLE",
        "child_model_activations": "UNAVAILABLE",
        "root_input_tokens": "UNAVAILABLE",
        "child_input_tokens": "UNAVAILABLE",
        "root_context_size_per_activation": "UNAVAILABLE",
        "ROOT_ACTIVATIONS_WITHOUT_NEW_INFORMATION": "UNAVAILABLE",
        "ROOT_MODEL_ACTIVATIONS_PER_CHILD": "UNAVAILABLE",
        **orchestration,
    }
    return result
