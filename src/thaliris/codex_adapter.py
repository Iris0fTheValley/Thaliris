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

_NATIVE_CODEX_ROLE_MAP = {
    "luna": "investigator", "luna-investigator": "investigator",
    "luna-curator": "curator", "sol-high": "reasoning-specialist",
    "terra-implementer": "implementer", "terra-reviewer": "reviewer",
    "thaliris-investigator": "investigator", "thaliris-curator": "curator",
    "thaliris-reasoning-specialist": "reasoning-specialist",
    "thaliris-implementer": "implementer", "thaliris-reviewer": "reviewer",
}
# This adapter-owned vocabulary is a CLI ingress contract. Core receives an
# opaque actor marker after this boundary has authorized the operation.
# This is the complete public CLI ingress vocabulary. Native identifiers are
# translated only at the native adapter boundary and never accepted as roles.
ROLE_CHOICES = (
    "controller", "investigator", "curator", "reasoning-specialist", "implementer", "reviewer",
)

# Authoritative defaults. Controller is the persistent root, not a sixth child
# profile; its default is emitted in the generated root instructions below.
_ROLE_MODEL_DEFAULTS = {
    "controller": ("gpt-5.6-sol", None),
    "investigator": ("gpt-5.6-luna", "medium"),
    "curator": ("gpt-5.6-luna", "medium"),
    "reasoning-specialist": ("gpt-5.6-sol", "xhigh"),
    "implementer": ("gpt-5.6-luna", "medium"),
    "reviewer": ("gpt-5.6-terra", "high"),
}
_AGENT_PROFILES = {
    f"thaliris-{role}.toml": (*_ROLE_MODEL_DEFAULTS[role], role)
    for role in ("investigator", "curator", "reasoning-specialist", "implementer", "reviewer")
}
_NATIVE_PROFILE_NAMES = frozenset(name.removesuffix(".toml") for name in _AGENT_PROFILES)
# Exact SHA-256 identities of bytes emitted by earlier Thaliris adapters.
# Role keying deliberately prevents cross-role ownership claims.
_KNOWN_GENERATED_AGENT_PROFILE_HASHES = {
    "thaliris-investigator.toml": frozenset("0720619c1d0b85b80a2981597fcd60086a1bddc7f03f48f88cc8f75c1128d872 199d7b9cb1fb8d1a3536df07395a420b9476ee66d13a4a9ca6d6442215d9e7b8 44781edb6a654db482adafdc20b16f75cdebded2e62e8d86376aefc577a3ae55 f5623ba40d585b1760511344488d71c53e8c08a8c0ad8cbd1b76b268ae02c70f 55ef42ac18d46ed5fe2c624ed0be2c16956ab4fe91dd1e64b6ef3a07bae01cb1 307a3e90b32cf7dcde3cac3c683b3e16f5e13c147191e82e45109a75a6984ff4 188e8cc62bfd8e1f37f3068193deb37431c5ea49356adc99b8873a47e817fbdd caa08fc96fdcff0a47fa05cb8ebba32d93a3336fec64b0a9c93d5467cc3009be c917f0b601dcd689afbb443b98c6b12733d5738ed908a112a5c7948f3321edf9".split()),
    "thaliris-curator.toml": frozenset("8026959290edeb86d66ee86f9b5db286e7fb31c28c95ec2c42ec8be7f2cda515 f6827c30074554b809b50414bde31146354ec6898fe8bd13a43402134c8b6476 a98489c08e6af01165629b6848667700956d749bf8a676a30ac479c729d916fa 64fece15a4e47b77641039abbf9f7c9a1daab4581b9faa0c066fd7d0c7cab4d4 d11534e931c1c17b51bd846a487ac6609b56db018f5abb6b5ed6991b5b6a71b3 b902b77ca7f0f77f6305cb8bec3e7bf1c8386805a312b816e2a99e1794e9a1f7".split()),
    "thaliris-reasoning-specialist.toml": frozenset("7e596a38e95606b684b17f25cc0eecb3163aef7d65d36110f6496b3ab7d53692 960190bb4b67b02e7616bcf6dbd71192bcc79327fb0ed72e6f23b3815819afd0 d2191d59621e2765ae7642ca1648d96b4dbfb1a82293a8a02bf8642328fb58a7 60a87a06e97602f10f7f3842061c6eba551e78f76a8fa99b17ba377f48d22117 13b3283ad629bb6d32fe3613462694be14fba3a24c547aa791e1e651c0b3106d 17616dddc351c20f5c98a30a0506253322d0cc5f6480d89690c7a08a70592557 5a22321413193d571a4a3b9189d45951ffda93cefde26f2f3999982233d17a01 813b16ca10985e8e602ee3295eb093115de4505db9cdc9cc6cbd9ef9ad192efd 708bee8d038cdd44bc8b75ee399ff8de09fa9a65e9d46f7060d75a82f04c19aa 1fa5af05b543d22efc20cc8eb7813da51e63a63c58b02bea6c2109918aa5d9d9 b7a6c8ae5655205dbb16a7d90af09a06a21daad78170cc8e55509304770d5b10".split()),
    "thaliris-implementer.toml": frozenset("a91e41c67930071db4d6eb45342526cbbf67af6d4fda13d1c847d18f28816a35 a1c7a46981512c7e8067dd5e40e193a0b54e34384aefc2b28950d5c6ccb5af9a d24ee0de8a22409bd5a3c9f1359079c4d6c7ccfbb14f65842e84f21ab0a5aa96 360d49c46afe280f85d6857575a12a9eeeff93d1f9aedb4b00ef2a2aa7c8b078 4028038b2153e56881140dabdc9165d2d1866fa737635e33599dc4d3cef0342f a463ea49f2cc308b6457ab63612a5f6b257f7462470118537961315b8e757ed1 fd0e28d2f1cce4f639a34b123bd647c9cd64d8b90fd5fb54a1e8353ecde924ad 7f85c22eb8ca508622b39bb8708e6bd617de3139f9de012ee29d166d4a3aad1e 3fcfcf2a04a8ef9e3a5c52f7414664b3a0d0fbc7f036c2558da1cb8baf955d95".split()),
    "thaliris-reviewer.toml": frozenset("ae56701985a1d27a2daea326819fa0e93b4350eb6e65d1a299daf198126a7a9a c43274a3f9cb3f93cd662b6477f1dfd07c170c24324c1364df5f59205851b17b d0f488e226888c6a8f6e39ab1deeb1125d3c0e9474dba47af47ec3eab2da45c2 ae51394874f0b35dc2b39577d471bf2f07533962363cdb7ad56e6e08a3860887 322534fb6f2b2abc312bd04a76e477e3e128cf6a194da5817ecaabd0678aa397 b038486edb2c381631e458adac2bff12fbcdc09233b5b1b8f59aeee9dc0e9774 720ef66c9f6023d961ddc1a3329ec4ae3fdf7fe2f6b1252034a7117f5990a125 4cec33fef9151d2ba60483a72b49ccd7dadd0b5c044a69f00f468e71c489fe07 8999980daf617644a36da7579626f122b6c279ad54e055bbaf8242daedbd36c2 b9b3b50f89b1dd7c5f5eaf2ee558b6881b014d66f6b30bc20244f361ebc721d7 e281f8c25451cbccb1509fa07814e4cfeaa8ae113402fc2db9a6c63a165bc1e6 96257cc1ed5c88b37de73e2c355c17c6b1ab26620210effe5b3283c776d0e4b9 357e9364404a2ab249c27ad3a2c93305f38db5afbbec1b56b58ee5e0817d5602 82b410c617589d410deb33f1ff4163d49b22d329ee517442a004965115a46124 fe082be2c5d05675b3ab9a69234851d505db3a3deddb509794b817f5b59a8ab8".split()),
}
_KNOWN_HOST_WAIT_CAPABILITIES = {
    # These are release-pinned observations, not a cross-version assumption.
    "0.153.4": {"min": 10_000, "default": 30_000, "max": 3_600_000, "explicit_timeout_supported": True, "native_completion_reenters_root": "UNSUPPORTED"},
    "0.154.0": {"min": 10_000, "default": 30_000, "max": 3_600_000, "explicit_timeout_supported": True, "native_completion_reenters_root": "UNSUPPORTED"},
    "0.155.1": {"min": 10_000, "default": 30_000, "max": 3_600_000, "explicit_timeout_supported": True, "native_completion_reenters_root": "UNSUPPORTED"},
}


def _agent_profile(name: str, role: str, model: str, effort: str) -> bytes:
    shared = (
        "The Controller's explicit native spawn message is your sole task-specific input. "
        "Do not reconstruct task state from unselected durable material, and do not infer unselected "
        "memory, milestone, Artifact, finding, decision, or review content. Keep repository "
        "reads, tool output, test logs, and intermediate exploration in your private working "
        "set. Return a distilled result with Conclusion, Key findings, Decision-changing "
        "unknowns, Contradictions if any, Verification performed, and Artifact refs if detailed "
        "reusable material was retained. Do not delegate to another authorized native Codex role session. "
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
            "Implement only an implementation task packet containing Goal, confirmed facts, hard "
            "invariants, Controller-decided boundaries/contracts, decision-changing unknowns, "
            "non-binding recommendations/advice, and acceptance. Only Controller decisions, "
            "invariants, and acceptance are binding; recommendations/advice are not contract. "
            "Do not silently drop, guess, or freeze an unknown that changes direction. Prove Host "
            "protocol, serialization, identity, or native schema through an Investigator, source, "
            "or real-shaped fixture before implementation. Report verification as observations; "
            "Core does not supply semantic completion authority."
        ),
        "reviewer": (
            "Act as an independent non-writing checker of the candidate named in the handoff. "
            "After a real problem, understand its invariant and inspect adjacent legal states "
            "enough to return independent related blockers in one pass. Return findings and a "
            "distilled verdict; the Controller decides what follows."
        ),
    }[role]
    instructions = shared + role_instruction
    return (
        f'name = "{name}"\n'
        f'description = "Thaliris {role} execution role"\n'
        f'model = "{model}"\n'
        f'model_reasoning_effort = "{effort}"\n'
        + f'developer_instructions = "{instructions}"\n'
    ).encode("utf-8")


def _agent_profile_state(value: bytes, name: str) -> str:
    profile = _AGENT_PROFILES.get(name)
    if profile is None:
        return "user"
    expected = _agent_profile(name.removesuffix(".toml"), profile[2], profile[0], profile[1])
    if value == expected:
        return "current"
    return "legacy" if hashlib.sha256(value).hexdigest() in _KNOWN_GENERATED_AGENT_PROFILE_HASHES.get(name, frozenset()) else "user"


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
    if runtime_role in ROLE_CHOICES:
        return runtime_role
    raise ValueError(f"unknown Thaliris role: {runtime_role}")


def controller_actor(runtime_role: str) -> str:
    """Authorize a Controller-only adapter operation and return its marker."""
    actor = semantic_role(runtime_role)
    if actor != "controller":
        raise ValueError("only Controller may perform this operation")
    return actor


@lru_cache(maxsize=8)
def _host_wait_mode_cached(runner: str) -> dict[str, object]:
    """Return a conservative, version-bound wait capability for this host."""
    try:
        completed = subprocess.run([runner, "--version"], capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return {"status": "UNSUPPORTED", "version": "UNKNOWN", "reason": "Codex executable is unavailable"}
    # A release pin is useful only when the executable identifies itself as
    # that exact release.  Do not extract a numeric prefix from prerelease or
    # decorated output: those builds have no recorded capability contract.
    match = re.fullmatch(
        r"(?:codex(?:-cli)?\s+)?(\d+\.\d+\.\d+)",
        ((completed.stdout or "") + (completed.stderr or "")).strip(),
        flags=re.IGNORECASE,
    )
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
        # This release pin is a hard contract bound, not proof that the
        # current hook session accepts that value.  No config file is an
        # effective-session observation.
        "release_hard_max_wait_timeout_ms": host["max"],
        "effective_max_wait_timeout_ms": "UNAVAILABLE",
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

The Controller is the sole task-specific semantic router. For every task,
whether ACTIVE or degraded, it selects the minimum necessary fresh roles.
Roles are capabilities, not mandatory workflow stages. A straightforward,
bounded, low-risk task with confirmed facts may follow Controller -> fresh
Implementer -> done. That Implementer may perform the bounded local reading,
implementation, and deterministic verification needed to complete the task.
Use an Investigator only when missing facts could change the implementation
direction. Use a Reviewer only when independent semantic review adds real
value; it is not a default gate. Curator and Reasoning Specialist remain
optional and are selected only when they add actual value.

Fresh Investigator, Curator, Reasoning Specialist, Implementer, and Reviewer sessions use `fork_turns="none"`
and receive their tasks plus selected information in
the Controller's native spawn message. `SubagentStart` validates authorization,
identity, role, and session and binds lifecycle metadata; it never calls Core to
construct or inject task context. Task state, memory, milestones, prior reviews,
and Artifact bodies never enter an Investigator, Curator, Reasoning Specialist, Implementer, or Reviewer automatically.

Persistent root Controller model default: `gpt-5.6-sol`. Reasoning effort is
selected by Host, task, or user policy and is not forced by Thaliris. This is
root instruction metadata, not a native Codex child profile and does not change
a current task model automatically.

An implementation handoff states Goal, confirmed facts, hard invariants,
Controller-decided boundaries/contracts, decision-changing unknowns,
non-binding recommendations/advice, and acceptance. Decisions, invariants, and
acceptance are contract; recommendations/advice are not. An unknown that can
change direction cannot be silently dropped, guessed, or frozen: prove Host
protocol, serialization, identity, and native-schema contracts first.

Each Investigator, Curator, Reasoning Specialist, Implementer, and Reviewer keeps
its private working set private. By default it returns a distilled conclusion, key findings,
decision-changing unknowns or contradictions, verification performed, and
optional Artifact pointers. Detailed reusable material may be saved in a
repo-relative Artifact. The Controller decides whether to register or retrieve
it and whether any selected content belongs in a later handoff. Artifact
registration stores address, producer, revision, hash, provenance, and optional
supersession only; it does not interpret the body.

Memory and milestones are ordinary explicit storage. Search results are ordinary explicit inputs.
Status is a bounded mechanical record label. Legacy durable Markdown Status metadata remains readable
as opaque compatibility data, never routing authority. Freshness reports only FRESH, PARTIAL, RECORDED, CHANGED, MISSING, or
UNKNOWN mechanical facts. `.agent-memory/INDEX.md` and
`.milestones/INDEX.md` are model-maintained thin global maps of the durable
tree; Core does not reconstruct a second catalog by recursively scanning the
filesystem or impose a taxonomy. SessionStart only points to these maps; before
`task-start`, the Controller explicitly reads the root navigation, and if a map
is missing it establishes a minimal thin INDEX first. During an active task,
navigation is not reread automatically; the Controller may reread it when the
map changed, is insufficient, freshness is invalid, or work is resumed after
compaction. The Controller explicitly uses `catalog` or
`document-get` to retrieve selected durable material. A single bounded
`document-get` may name up to eight explicit paths; it never searches, ranks,
or supplements the selection.
When a promotion changes durable navigation, the Controller should include its
own optional `index_update` in the same `task-promote` call. Core does not
generate INDEX content; it validates the CAS, references, and atomic commit.

With NO_TASK, Thaliris leaves ordinary Codex tool use and spawn behavior
transparent. During an ACTIVE managed task the persistent Controller uses only
native spawn/wait/list/interrupt operations and an explicit allow-set of
trusted direct `thaliris` runtime commands. `init`, `uninstall`, `rollback`, a
second `task-start`, and `task-show` are blocked for ACTIVE Root. `task-status`
is bounded; `task-get`, `artifact-get`, `catalog`, and `document-get`
retrieve explicitly selected objects.
If `task-start` was attempted but managed enforcement is unavailable or
rejected, label the run unmanaged/degraded. Diagnose only the bootstrap cause:
Codex version, host capability, task schema, git/worktree identity,
hook/profile presence, and the `task-start` error are allowed reads. Use only
the direct canonical `thaliris` command or an absolute executable with an
explicit exact SHA-256 pin; never recommend or use a shell-wrapper fallback.
If neither trusted direct route is available, check canonical availability, the
explicit executable SHA-256 pin, and hook/install state, then report bootstrap
unavailable. Once the cause is known, do not read user-task repository source,
tests, docs, or search results. If work continues, apply the same minimum-role
routing policy defined above; degraded mode does not define a separate role
sequence. The Controller must not take over repository
investigation, implementation, or testing merely because NO_TASK applies. The
final report must not claim managed enforcement was verified.
If Codex reports a native spawn failure before `SubagentStart`, the Controller
may explicitly run `thaliris recover-pending-spawn <handoff-id>` for that exact
reservation. Core never infers failure from a missing event, timeout, or retry.
Decision-changing investigation belongs to Investigator. Bounded local reading
needed for implementation may stay inside Implementer. Execution, mutation,
and testing belong to fresh Implementer sessions. Existing native Codex child sessions are never resumed with follow-up/send tools.
An Investigator's or Implementer's obvious direct control-context retrieval is allowed and recorded.
Investigator and Implementer reads remain telemetry-only; Curator, Reasoning
Specialist, and Reviewer extra reads produce at most one bounded aggregate
Controller notice per pending batch. Obvious attempts to mutate
Controller-owned task or lifecycle state are denied, recorded, and included in
that aggregate notice. Reviewer independence is a
developer-instruction plus obvious-write hook guard, not a claimed native
read-only sandbox. Starting managed mode requires a current-session,
current-hook, one-shot PreToolUse attestation.

Managed native Codex child lifecycles are serial. Spawn authorization, native identity binding,
SubagentStart/Stop, missing-stop reconciliation, and explicit blocking waits are
mechanical. SubagentStop alone is not success; only an explicitly observed
native Completed status can satisfy lifecycle completion. A short native wait
is normalized only while an authorized reservation or managed native Codex child is pending
and the current-session effective maximum is mechanically verified; otherwise
no automatic long-wait normalization occurs. The Controller interprets Investigator, Curator, Reasoning Specialist, Implementer, and Reviewer results,
verification observations, review findings, and task surface deltas and decides
the next handoff and when work is complete.
{MANAGED_END}
"""

ROLE_PACKS = """<!-- thaliris-role-packs:v4 -->
# Thaliris Role Profiles

These profiles are working-style defaults, not routing rules or semantic
permissions. The Controller's explicit native spawn message is the sole
task-specific input to every Investigator, Curator, Reasoning Specialist, Implementer, and Reviewer.

## Role Defaults

The persistent root Controller model default is `gpt-5.6-sol`; its reasoning
effort is selected by Host, task, or user policy and is not forced by Thaliris.
It is root instruction metadata, not a native Codex child profile and does not
mutate a current task model. The five child profiles are Investigator (`gpt-5.6-luna`,
`medium`), Curator (`gpt-5.6-luna`, `medium`), Reasoning Specialist
(`gpt-5.6-sol`, `xhigh`), Implementer (`gpt-5.6-luna`, `medium`), and Reviewer
(`gpt-5.6-terra`, `high`).

## Shared Role Result

Return a distilled result by default:

- Conclusion
- Key findings
- Decision-changing unknowns
- Contradictions, if any
- Verification performed
- Artifact refs, if detailed reusable material was retained

Keep repository reads, tool output, test logs, and intermediate exploration in
the role session's private working set. Do not copy an Artifact body into the result
unless the Controller explicitly requested that content.

## Investigator

Investigate the bounded task in the handoff. Save detailed reusable evidence as
an optional repo-relative Artifact and return its pointer with a short result.

## Curator

Use only when the Controller identifies genuinely reusable knowledge and
explicitly supplies the material to curate. Do not automatically summarize a
task, select a next role, or route a result. Curator output is an ordinary
result or Artifact; Core has no Curator state machine.

Knowledge derived from current implementation correctness defaults to curation
only after Reviewer PASS and the Controller's reuse judgment. Independently
verified stable facts unrelated to current implementation correctness may be
curated earlier when the Controller explicitly selects them.

## Durable knowledge loop

At task start, the Controller reads the root INDEX map and then makes an exact
`document-get` request for the selected linked entries. At task end it decides
whether any knowledge is genuinely reusable; a Curator is optional, never an
automatic step. If the Controller promotes a selected record that changes the
durable architecture, it supplies the model-authored INDEX CAS update in that
same promotion. Otherwise it leaves INDEX bytes unchanged. A fresh later task
recovers only by reading INDEX and exact selected documents, not by broad
reinvention or recursive scanning.

## Reasoning Specialist

Use only when resolving the decision in the handoff adds actual value beyond
the selected roles' work. Resolve it from the selected information. If a
decision-changing fact is missing, say what is missing. Do not reconstruct
unselected task history.

## Implementer

An implementation task packet contains Goal, confirmed facts, hard invariants,
Controller-decided boundaries/contracts, decision-changing unknowns,
non-binding recommendations/advice, and acceptance. Only Controller decisions,
invariants, and acceptance are binding; recommendations/advice are not
contract. Do not silently drop, guess, or freeze an unknown that changes
direction. Before implementation, prove Host protocol, serialization, identity,
or native schema through an Investigator, source, or real-shaped fixture.
For a straightforward, bounded task with confirmed facts, perform necessary
bounded local reading, implementation, and deterministic verification in this
fresh session; an Investigator is needed only when missing facts could change
how to implement. Preserve stated constraints and report verification as
observations. Do not infer additional task state from Core.

## Reviewer

Use when the Controller selects independent review because it adds value; it is
not a mechanical post-implementation gate. Independently inspect the candidate
identified in the handoff. Return findings
and a distilled verdict. After finding a real problem, understand its invariant
and inspect adjacent legal states enough to return independent related blockers
in one pass. Finding classifications are model-authored labels; the Controller
decides what workflow, if any, follows.
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
        elif _agent_profile_state(profile.read_bytes(), name) == "legacy":
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
    hooks = lifecycle.hooks_health(root)
    stale_runtime_hook_spec = (
        hooks["installed_hook_spec"] == "CURRENT"
        and hooks["current_hook_hash_observed"] == "STALE"
    )
    executable_unavailable = hooks["canonical_executable_available"] == "NO"
    if stale_runtime_hook_spec:
        # The installed definition is current, but this host's observed runtime
        # hook identity is stale.  Init cannot re-attest an already-running
        # session, so require an explicit restart and re-attestation.
        manual = sorted(set(manual) | {"stale_runtime_hook_re_attestation_required"})
    if executable_unavailable:
        # The installed portable hook invokes the canonical PATH command. Init
        # cannot make that command available to Codex's already-running host,
        # so make the required host repair and subsequent re-attestation
        # explicit even when the hook definition itself is unchanged.
        manual = sorted(set(manual) | {"canonical_executable_unavailable"})
    if hooks["legacy_managed_handler_cleanup"] == "MANUAL_CLEANUP_REQUIRED":
        manual = sorted(set(manual) | {"legacy_managed_handler_manual_cleanup_required"})
    return {"ok": True, "changed": bool(files), "backup": backup, "files": sorted(files), "manual_action_required": manual, "instruction_definition_changed": instruction_changed, "hook_definition_changed": hook_changed, "agent_profile_changed": profile_changed, "canonical_executable_available": hooks["canonical_executable_available"], "canonical_executable_identity": hooks["canonical_executable_identity"], "session_restart_required": instruction_changed or hook_changed or profile_changed or stale_runtime_hook_spec or executable_unavailable, "hook_trust_required": hook_changed or stale_runtime_hook_spec or executable_unavailable, "host_wait_mode": host_wait_mode(), **_activation_fields(root)}


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


def task_start(
    root: Path,
    goal: str,
    milestone: str | None,
    input_file: str | None,
    hook_attestation: str | None = None,
) -> dict[str, object]:
    root = core._repo_root(root)
    lifecycle.consume_task_start_attestation(root, hook_attestation)
    mode = selected_continuation_mode(root)
    readiness = {
        "status": "PASS" if mode in {"EVENT_DRIVEN", "BLOCKING_WAIT"} else "MANAGED_CONTINUATION_UNAVAILABLE",
        "NATIVE_CHILD_COMPLETION_REENTERS_ROOT": native_child_completion_reenters_root(),
        "HOST_EXPLICIT_BLOCKING_WAIT": host_explicit_blocking_wait().get("status"),
        "selected_continuation_mode": mode,
    }
    if mode == "UNAVAILABLE":
        return {"ok": False, "status": "MANAGED_CONTINUATION_UNAVAILABLE", "managed_readiness": readiness}
    result = core.task_start(root, goal, milestone, input_file, actor="controller")
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
    target = capability.get("effective_max_wait_timeout_ms")
    if not isinstance(target, int) or isinstance(target, bool) or target < 0:
        return ""
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
    result["durable_index_integrity"] = core.durable_index_check(root)
    result["managed_task_state"] = lifecycle.managed_task_state(root)[0]
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
        "task_start_attestation": "CURRENT_SESSION_REQUIRED",
        "adapter_protocol_current": "YES" if events or latest is not None else "UNKNOWN",
        "verification_shell_surface": "Bash",
        "verification_terminal_status": "UNAVAILABLE",
        "observed_outcome": latest_item.get("outcome") if latest_item is not None else "UNKNOWN",
        "hook_trust": "UNKNOWN",
        "detail": "No version-pinned terminal-status attestation is recorded; no automatic PASSED attestation is emitted.",
    }
    result["managed_readiness"] = {
        "CORE_READY": "YES",
        "CODEX_DEFINITION_PRESENT": health["hooks_configured"],
        "CODEX_RUNTIME_OBSERVED": health["runtime_observed"],
        "CURRENT_SESSION_OBSERVED": "UNKNOWN",
        "TASK_START_ATTESTATION": "CURRENT_SESSION_REQUIRED",
        "CODEX_MANAGED_READY": "UNKNOWN",
        "spawn_pretool_observed": "YES" if "PreToolUse" in events else "UNKNOWN",
        "subagent_start_observed": "YES" if lifecycle_start else "UNKNOWN",
        "subagent_stop_observed": "YES" if lifecycle_stop else "UNKNOWN",
        "explicit_handoff_binding_observed": "YES" if lifecycle_start else "UNKNOWN",
        "controller_activation_bridge": "CODEX_NATIVE",
        "NATIVE_CHILD_COMPLETION_REENTERS_ROOT": native_child_completion_reenters_root(),
        "HOST_EXPLICIT_BLOCKING_WAIT": host_explicit_blocking_wait().get("status"),
        "EFFECTIVE_WAIT_MAXIMUM": host_explicit_blocking_wait().get("effective_max_wait_timeout_ms", "UNAVAILABLE"),
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
        "effective_wait_maximum": host_explicit_blocking_wait().get("effective_max_wait_timeout_ms", "UNAVAILABLE"),
    })
    result["host_capability"] = host
    posttool_schema = "PASS" if host_wait_mode().get("status") == "PASS" else "UNKNOWN"
    result["lifecycle_reconciliation"] = {
        "subagent_stop_path": "PASS" if lifecycle_stop else "UNKNOWN",
        # The pinned source supplies these shapes, but a
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
