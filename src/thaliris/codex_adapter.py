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
from .protocol import ROUTING_PROTOCOL_VERSION
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
    "0.153.4": {"min": 10_000, "default": 30_000, "max": 3_600_000, "explicit_timeout_supported": True, "project_config_supported": True, "native_completion_reenters_root": "UNSUPPORTED"},
}
_WAIT_CONFIG_MARKER = "# thaliris:managed-blocking-wait"
_KNOWN_GENERATED_AGENT_PROFILE_HASHES = frozenset({
    "0720619c1d0b85b80a2981597fcd60086a1bddc7f03f48f88cc8f75c1128d872",
    "8026959290edeb86d66ee86f9b5db286e7fb31c28c95ec2c42ec8be7f2cda515",
    "7e596a38e95606b684b17f25cc0eecb3163aef7d65d36110f6496b3ab7d53692",
    "a91e41c67930071db4d6eb45342526cbbf67af6d4fda13d1c847d18f28816a35",
    "ae56701985a1d27a2daea326819fa0e93b4350eb6e65d1a299daf198126a7a9a",
    # Exact profile bytes emitted before the dedicated Sol Decision Context
    # instruction was added.
    "960190bb4b67b02e7616bcf6dbd71192bcc79327fb0ed72e6f23b3815819afd0",
    # Exact profile bytes emitted by the first dedicated Decision Context
    # profile before the current boundary instruction was added.
    "d2191d59621e2765ae7642ca1648d96b4dbfb1a82293a8a02bf8642328fb58a7",
    # Exact profile bytes emitted before bounded-decision/evidence-request
    # instructions were added.
    "60a87a06e97602f10f7f3842061c6eba551e78f76a8fa99b17ba377f48d22117",
    # Exact profile bytes emitted before the explicit contradictory-evidence
    # outcome was added.
    "13b3283ad629bb6d32fe3613462694be14fba3a24c547aa791e1e651c0b3106d",
    # Exact investigator profile bytes before artifact-first handoff guidance.
    "199d7b9cb1fb8d1a3536df07395a420b9476ee66d13a4a9ca6d6442215d9e7b8",
    # Exact reviewer profile bytes before the explicit read-only boundary.
    "c43274a3f9cb3f93cd662b6477f1dfd07c170c24324c1364df5f59205851b17b",
    # Exact profile bytes emitted by adapter 0896fe3 before native reviewer
    # sandbox_mode was added.
    "d0f488e226888c6a8f6e39ab1deeb1125d3c0e9474dba47af47ec3eab2da45c2",
    # Historical generated profile bytes retained for conservative migration.
    "ae51394874f0b35dc2b39577d471bf2f07533962363cdb7ad56e6e08a3860887",
    "a1c7a46981512c7e8067dd5e40e193a0b54e34384aefc2b28950d5c6ccb5af9a",
    # Exact profile bytes emitted before direct-write guidance was removed
    # from the runtime-neutral role contract.
    "44781edb6a654db482adafdc20b16f75cdebded2e62e8d86376aefc577a3ae55",
    "f6827c30074554b809b50414bde31146354ec6898fe8bd13a43402134c8b6476",
    "17616dddc351c20f5c98a30a0506253322d0cc5f6480d89690c7a08a70592557",
    "d24ee0de8a22409bd5a3c9f1359079c4d6c7ccfbb14f65842e84f21ab0a5aa96",
    "322534fb6f2b2abc312bd04a76e477e3e128cf6a194da5817ecaabd0678aa397",
    # Exact Reviewer/Implementer profile bytes emitted before the review
    # transaction-integrity wording was added.
    "b038486edb2c381631e458adac2bff12fbcdc09233b5b1b8f59aeee9dc0e9774",
    "360d49c46afe280f85d6857575a12a9eeeff93d1f9aedb4b00ef2a2aa7c8b078",
    # Exact reviewer profile emitted before the bounded Review Packet fields
    # were added. Retained for conservative profile migration.
    "720ef66c9f6023d961ddc1a3329ec4ae3fdf7fe2f6b1252034a7117f5990a125",
})


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
    if value == expected:
        return "current"
    return "legacy" if hashlib.sha256(value).hexdigest() in _KNOWN_GENERATED_AGENT_PROFILE_HASHES else "user"


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


def blocking_wait_configured(root: Path, executable: str | None = None) -> dict[str, object]:
    """Validate only the project-file part of blocking-wait readiness.

    A TOML file is not evidence that the running Codex process loaded it. In
    particular, a desktop session may predate the write or the project may not
    be trusted. Keep this deliberately separate from ``blocking_wait_active``.
    """
    capability = host_wait_mode(executable)
    if capability.get("status") != "PASS" or capability.get("project_config_supported") is not True:
        return {"status": "UNSUPPORTED", "reason": capability.get("reason", "project configuration is unsupported"), "host": capability}
    path = core._safe(core._repo_root(root), ".codex/config.toml")
    try:
        parsed = tomllib.loads(_read_text(path))
        configured = parsed["features"]["multi_agent_v2"]["default_wait_timeout_ms"]
    except (OSError, KeyError, TypeError, tomllib.TOMLDecodeError):
        return {"status": "FAIL", "reason": "managed project blocking-wait default is absent", "host": capability}
    if not isinstance(configured, int) or not capability["min"] <= configured <= capability["max"]:
        return {"status": "FAIL", "reason": "project default is outside the host-supported wait range", "host": capability}
    if configured != capability["max"]:
        return {"status": "FAIL", "reason": "project default is not the Thaliris host-bounded long wait", "host": capability}
    return {"status": "PASS", "default_wait_timeout_ms": configured, "host": capability}


def blocking_wait_active(root: Path, executable: str | None = None) -> dict[str, object]:
    """Return runtime evidence for the effective project default, never a guess.

    Codex 0.153.4 exposes no effective-config value to a project hook. Until a
    trusted fresh-process probe records such an observation, configuration is
    merely configured, not active.
    """
    configured = blocking_wait_configured(root, executable)
    if configured.get("status") != "PASS":
        return {"status": configured.get("status"), "reason": configured.get("reason"), "configured": configured}
    return {
        "status": "UNKNOWN",
        "reason": "no trusted fresh Codex session has exposed the effective project wait default",
        "configured": configured,
    }


def blocking_wait_mode(root: Path, executable: str | None = None) -> dict[str, object]:
    """Compatibility alias for callers that need the *active* readiness only."""
    return blocking_wait_active(root, executable)


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
LEGACY_MANAGED_START = "<!-- codex-context:begin -->"
LEGACY_MANAGED_END = "<!-- codex-context:end -->"
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

KNOWN_GENERATED_ROLE_PACK_HASHES = frozenset({
    "242d1c6420139434425a2d6883011c2c44e34f1f3280267cb09243bdc0155f09",
    "75f6c6804db80995c32cf4902247ae0d78762a15f37b35b677219813c8d17e6a",
    "4ff409d7aa3d5f2ad2eb0c82b317d9af54426dde7765d8101939dcc578a460c0",
    "6e49df8985c52309a6966c5ddd8b6b3b6a2b6bce326c55f327cb999bb6b46e4c",
    # Exact role-pack bytes emitted before the current escalation/handoff text.
    "8822c992b91d6cf0cc03a4f7c56b2c4ee48050d76d4e3b07654fa0acef36bbce",
    # Exact generated bytes from intermediate published adapter releases.
    "28498b36a46a631d0421a445d391ddffa61244bb56ebba4f6cac20a144a37ad3",
    "28a56dd1dce4d41ab6d310510348c78d386b42954015006419a76e0c8f4c1213",
    "52383be5756d7593a1c41c8b48e89e0efcec54fd94f8ba4908b3380708a15baa",
    "0d679ca45a0de42d31197970bd976fddba104fbd6c66b1e153062fa6a94769ed",
    "ca2570778106e2a0a72683a8ceef79c1828a5e0b43b370ae9a8e95e09a59eb01",
    "655a67a933d96273c594a4276c6126ada61832b9031c06e4e235e9686c350742",
    "a0abab298e8eda6312511761f891c0286cc3ffd6732aef09d9eab3f04dcd6d03",
    # Exact role-pack bytes published with the current Sol handoff revisions.
    "2c19646856d4ad930059e8e9a3fc026a08951e622c12c025a5b1bdcc20b0250c",
    "8822e1aaa5a56f78cd9f044e329aa73c324bfd63df841fefd8f02b0008edfa0e",
    # Exact role-pack bytes before artifact-first handoff guidance.
    "865944fad8b854952422d741787fbbcfa292948fbfb11e31c6f9a0e9452b6df7",
    # Exact bytes immediately before event-driven Controller suspension.
    "432f122986f11e28568674e06d509ac22636f0eed4e86fbdffd46d4ab79d8fa6",
    # Exact role-pack bytes emitted by the supervisor-era 645a40e release.
    "30213f6b50822047e691673b3e1f27718e795ce450989bf74c53c08f8f98921d",
    # Exact role-pack bytes before the review-convergence protocol reference.
    "7fd54f2f8c7e97ab54aefa31bb3f53f7864f2d00e4d2e9b1d27309f115945d3d",
    # Exact role-pack bytes emitted before the product-protocol split.
    "fb9aa6827d9aba1ff0a03295f007b46c7e03c72894c20a78438eb35fdfd5cc5b",
    # Exact role-pack bytes before benchmark terminology was removed from the
    # product router.
    "a9d8d947339c5d57c8fb9ca06ca07df4a1c5f1b37a42100482b2f913cd8ab6a6",
})


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


def _effective_agents_path(root: Path) -> Path:
    """Compatibility alias for root-instruction callers."""
    return _effective_root_instruction_path(root)


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
    # Earlier prefix rendering inserted a second separator after MANAGED's
    # own trailing newline. Collapse that known generated separator on move.
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
    return block if not user_text else block + user_text


def _role_pack_state(value: bytes) -> str:
    if value == ROLE_PACKS.encode("utf-8"):
        return "current"
    if hashlib.sha256(value).hexdigest() in KNOWN_GENERATED_ROLE_PACK_HASHES:
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
            return {"ok": True, "changed": False, "backup": None, "files": [], "manual_migration_required": manual, "instruction_definition_changed": False, "hook_definition_changed": False, "agent_profile_changed": False, "session_restart_required": False, "hook_trust_required": False, "host_wait_mode": host_wait_mode(), **_activation_fields(root)}
        hook_changed = ".codex/hooks.json" in writes
        instruction_changed = any(path in {"AGENTS.md", "AGENTS.override.md"} for path in writes)
        profile_changed = any(path.startswith(".codex/agents/") for path in writes)
        return {"ok": True, "changed": True, "backup": core._apply_with_backup(root, writes, [], "codex-init"), "files": sorted(writes), "manual_migration_required": manual, "instruction_definition_changed": instruction_changed, "hook_definition_changed": hook_changed, "agent_profile_changed": profile_changed, "session_restart_required": instruction_changed or hook_changed or profile_changed or ".codex/config.toml" in writes, "hook_trust_required": hook_changed, "host_wait_mode": host_wait_mode(), **_activation_fields(root)}


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
    elif _role_pack_state(role_packs.read_bytes()) == "legacy":
        writes["docs/thaliris-role-packs.md"] = ROLE_PACKS.encode("utf-8")
    elif _role_pack_state(role_packs.read_bytes()) == "user":
        manual.append("docs/thaliris-role-packs.md")
    for name, (model, effort, role) in _AGENT_PROFILES.items():
        relative = f".codex/agents/{name}"
        profile = core._safe(root, relative)
        rendered = _agent_profile(name.removesuffix(".toml"), role, model, effort)
        if not profile.exists() or _agent_profile_state(profile.read_bytes(), name) == "legacy":
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
    return {"ok": True, "changed": bool(files), "backup": backup, "files": sorted(files), "manual_migration_required": manual, "instruction_definition_changed": instruction_changed, "hook_definition_changed": hook_changed, "agent_profile_changed": profile_changed, "session_restart_required": instruction_changed or hook_changed or profile_changed or ".codex/config.toml" in files, "hook_trust_required": hook_changed, "host_wait_mode": host_wait_mode(), **_activation_fields(root)}


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
    instruction_changed = any(path in {"AGENTS.md", "AGENTS.override.md"} for path in files)
    profile_changed = any(path.startswith(".codex/agents/") for path in files)
    return {"ok": True, "changed": bool(files), "backup": backup, "files": sorted(files), "migration": "v2", "migrated": migrated, "manual_migration_required": manual, "migration_backup": backup, "instruction_definition_changed": instruction_changed, "hook_definition_changed": hook_changed, "agent_profile_changed": profile_changed, "session_restart_required": instruction_changed or hook_changed or profile_changed or ".codex/config.toml" in files, "hook_trust_required": hook_changed, "host_wait_mode": host_wait_mode(), **_activation_fields(root)}


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
        if _role_pack_state(packs.read_bytes()) in {"current", "legacy"}:
            deletes.append("docs/thaliris-role-packs.md")
        else:
            kept.append("docs/thaliris-role-packs.md")
    for name in _AGENT_PROFILES:
        relative = f".codex/agents/{name}"
        profile = core._safe(root, relative)
        if not profile.is_file():
            continue
        state = _agent_profile_state(profile.read_bytes(), name)
        if state in {"current", "legacy"}:
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
    config = core._safe(root, ".codex/config.toml")
    if config.is_file():
        current = _read_text(config)
        capability = host_wait_mode()
        expected = capability.get("max") if capability.get("status") == "PASS" else None
        # Own only the exact marker and immediately following generated value.
        # Anything else may be user TOML and is deliberately left untouched.
        owned = re.compile(
            rf"(?m)^[ \t]*{re.escape(_WAIT_CONFIG_MARKER)}[ \t]*\r?\n"
            rf"^[ \t]*default_wait_timeout_ms[ \t]*=[ \t]*{re.escape(str(expected))}[ \t]*(?:#.*)?\r?\n?"
        ) if isinstance(expected, int) else None
        marker_present = _WAIT_CONFIG_MARKER in current
        if owned is not None and owned.search(current):
            rendered = owned.sub("", current, count=1)
            # Remove an otherwise empty table we can prove was created solely
            # for this marker. Do not delete comments or neighbouring tables.
            empty_table = re.compile(r"(?m)^\[features\.multi_agent_v2\][ \t]*\r?\n(?=(?:\s*\r?\n)*(?:\Z|\[))")
            rendered = empty_table.sub("", rendered, count=1)
            if rendered.strip():
                writes[".codex/config.toml"] = rendered.encode("utf-8")
            else:
                deletes.append(".codex/config.toml")
        elif marker_present:
            manual.append(".codex/config.toml")
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


def task_start(root: Path, goal: str, milestone: str | None, input_file: str | None) -> dict[str, object]:
    root = core._repo_root(root)
    configured = blocking_wait_configured(root)
    active = blocking_wait_active(root)
    mode = selected_continuation_mode(root)
    readiness = {
        "status": "PASS" if mode in {"EVENT_DRIVEN", "BLOCKING_WAIT"} else "MANAGED_CONTINUATION_UNAVAILABLE",
        "NATIVE_CHILD_COMPLETION_REENTERS_ROOT": native_child_completion_reenters_root(),
        "HOST_EXPLICIT_BLOCKING_WAIT": host_explicit_blocking_wait().get("status"),
        "BLOCKING_WAIT_CONFIGURED": configured.get("status"),
        "BLOCKING_WAIT_ACTIVE": active.get("status"),
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
        "BLOCKING_WAIT_CONFIGURED": blocking_wait_configured(root).get("status"),
        "BLOCKING_WAIT_ACTIVE": blocking_wait_active(root).get("status"),
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
