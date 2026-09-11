"""Codex-specific mapping for Thaliris Core projections and lifecycle hooks."""
from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import subprocess
import tomllib

from . import core, intent_audit
from .intent_audit import MANAGED_HOOKS_DESCRIPTION, bind_unbound_intent, cleanup_task_audit, handle_hook, merge_hooks, remove_hooks, task_close_audit

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
    # Exact Reviewer/Implementer profile bytes emitted before the benchmark
    # review-convergence and bounded Correction Packet guidance was added.
    "ae51394874f0b35dc2b39577d471bf2f07533962363cdb7ad56e6e08a3860887",
    "a1c7a46981512c7e8067dd5e40e193a0b54e34384aefc2b28950d5c6ccb5af9a",
})


def _agent_profile(name: str, role: str, model: str, effort: str) -> bytes:
    instructions = (
        "Resolve the supplied Decision Context only, as one bounded decision attempt. Do not reconstruct "
        "the Investigator working set or perform repository-wide investigation, exploratory searches, or "
        "broad tool-driven fact gathering. You may inspect an exact selected evidence artifact or reference "
        "when necessary, but do not expand into open-ended investigation. If a decision-changing fact is "
        "missing, return NEED_EVIDENCE with an EvidenceRequest containing decision_question, missing_fact, "
        "why_it_can_change_the_decision, preferred_evidence_surface, and verification_requirement, then "
        "stop. If the selected evidence is materially contradictory and cannot be safely resolved, return "
        "INSUFFICIENT_OR_CONTRADICTORY with the conflicting references and stop. Otherwise return DECISION "
        "with the selected decision, rationale, must-preserve invariants, compatibility constraints, and "
        "remaining decision-changing unknowns. Do not modify repository "
        "files or task semantic state. Return the decision to the Controller; implementation belongs to "
        "the Implementer."
        if role == "reasoning-specialist"
        else (
            "Thaliris semantic role: investigator. Keep the investigation working set private. When findings "
            "will be reused, persist reusable evidence in a bounded repo-relative artifact preserving facts, "
            "evidence refs, affected files/symbols, verification, unknowns, and contradictions. Return only "
            "artifact path, finding/evidence identifiers, short outcome, and remaining decision-changing "
            "unknowns; do not use the final message as the primary evidence store."
            if role == "investigator" else
            f"Thaliris semantic role: {role}. Work only inside your assigned role and return selected evidence-backed results."
            + (
                " Review the current implementation as a read-only independent checker. "
                "Do not modify repository files, tests, or task semantic state; return only "
                "bounded findings with evidence references. Any correction belongs to a fresh "
                "Implementer, followed by a fresh Reviewer. Each finding must be returned as a "
                "bounded Review Packet with finding_id, classification (MECHANICAL, LOCAL_SEMANTIC, "
                "or ARCHITECTURAL), affected_surface, violated_invariant, and verification_requirement. "
                "An external interruption is INCOMPLETE, never READY or PASS."
                if role == "reviewer" else ""
            )
            + (
                " Accept only the selected Modification Boundary and, when correcting a review, its "
                "bounded Correction Packet. Preserve accepted constraints and verify only the named "
                "surface; do not reopen repository-wide investigation unless the packet is ARCHITECTURAL."
                if role == "implementer" else ""
            )
        )
    )
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

Codex remains the runtime. Thaliris stores bounded task control and pointers; it has no worker, scheduler, polling loop, or authority to decide correctness. Retain broadly, propagate explicitly, and select semantically: storage bounds are not a semantic payload quota.

Controller uses `context task-status` or `context prepare --role controller` for the default low-noise context base. `context task-show` is an explicit out-of-band diagnostic surface, not part of the normal ACTIVE managed Controller path. `context task-artifact` passes pointers, not contents.

During an active task the persistent root Controller is control-plane-only. Every new root child is a spawned execution child and must be fresh with `fork_turns=\"none\"`; non-none values are denied and must be retried explicitly. This cuts implicit parent-task-history propagation; it does not mean an empty context. An allowed root spawn creates one authorization reservation; the next matching native `SubagentStart` receives its Thaliris role projection, and only a successfully emitted projection followed by the matching `SubagentStop` qualifies for acceptance or task-close. Large selected information remains valid when needed for correctness. Pending reservations and started managed children are serial in flight; PostToolUse records dispatch only. Known local PreToolUse surfaces used by managed mode are mechanically guarded; hosted, specialized, and unverified runtime surfaces remain outside that envelope. After dispatch, persist the pending native continuation and let Codex's native collaboration or thread-continuation surface re-enter the Controller when available. Waiting is capability-adaptive: when the current Codex surface provides surviving-child continuation, end the activation and let native continuation re-enter; otherwise use one sufficiently long native blocking wait per real external dependency, check status once only after a timeout, and wait again if it is still running. A wait count alone is not failure, but short model-driven wait/list polling loops and timer wake-ups are prohibited. Codex owns execution; Thaliris does not recreate an agent runtime.

Read detailed role packs only when needed. Raw findings, evidence, transcripts,
logs, and tool output do not enter Controller packets or durable memory
automatically; explicitly select any detail needed for the next decision, and
promote only explicit durable decisions, constraints, invariants, failure modes,
or material milestone progress.

Investigators may keep a large private working set, but reusable findings must
be written to a bounded repo-relative Evidence Artifact before completion. The
completion message should contain only the artifact path, finding/evidence IDs,
a short outcome, and remaining decision-changing unknowns. The Controller must
register that pointer with the complete command `context task-artifact
--base-revision N --id ID --path repo/relative --summary TEXT
--producer-role investigator` and select relevant facts; artifact existence
never authorizes automatic full-text propagation. The command computes and
stores the artifact content identity from the registered file.

Every reusable artifact follows the evidence protocol: produce before the
dependent decision, register it through `context task-artifact` with its
producer role and content identity, select only the needed facts for the next
role, and record downstream consumption in the benchmark ledger. A changed
artifact is stale; a replacement must explicitly supersede it. Never silently
continue consuming stale or contradictory evidence. Fast paths that have no
cross-role evidence need record `evidence_required=NOT_REQUIRED` and must not
manufacture an artifact.

After targeted investigation, escalate to
`agent_type="thaliris-reasoning-specialist"` with `fork_turns="none"` only
when a material implementation choice remains unresolved by available
evidence: materially different fixes remain plausible, an OPEN unknown or
contradiction could change the choice, a cross-module state/lifecycle/
ownership/concurrency/compatibility choice remains undecided, a substantive
trade-off remains, or a Reviewer raises a design question. Do not escalate
only for task size, file count, or token count. Pass a selected Decision
Context, not the full investigation or an empty decision request.
After a Reasoning Specialist returns, do not dispatch an Implementer until
every accepted implementation-changing conclusion is recorded in task
semantic state or explicitly included in that Implementer handoff. Never rely
on implicit child history. A Reasoning Specialist makes one bounded decision
attempt: if evidence is insufficient, it returns an EvidenceRequest and stops;
the Controller sends that request to a fresh Investigator, persists a bounded
evidence artifact, then uses a fresh Reasoning Specialist. Reviewers are fresh
one-shot children for each review round; retain findings, not reviewer
conversation history. Use native surviving-child/thread continuation when the
 current Codex surface provides it. Otherwise use one sufficiently long native
 blocking wait per real external dependency; on timeout perform one status check
 and, if still running, use another long native wait. A wait count alone is not
 failure. Never use short model-driven wait/list polling loops or timer-driven
 wake-ups. Close completed one-shot Sol and Reviewer children with native Codex
controls. Thaliris does not implement scheduling, deadlines, or agent lifecycle.

Review convergence is packet-driven. A Reviewer classifies each finding as
MECHANICAL, LOCAL_SEMANTIC, or ARCHITECTURAL and names the exact affected
surface, invariant, and verification requirement. MECHANICAL and LOCAL_SEMANTIC
findings receive one fresh Implementer with a bounded Correction Packet and one
fresh targeted Reviewer. They do not restart Investigator/Sol or a repository-
wide review. ARCHITECTURAL findings may reopen the larger route. A fresh
Reviewer is still mandatory after every source mutation; a READY verdict seals
the source and any later mutation invalidates that review. External Reviewer
failure remains INCOMPLETE and has bounded recovery; it is never converted to
success.
{MANAGED_END}
"""

LEGACY_ROLE_PACKS = """# Thaliris Role Packs

Load this document when the compact managed router is insufficient.

## Controller

Use `context task-status` for task identity/status, active work, pending results, unresolved questions, artifact pointers, and accepted constraints/decisions. Raw findings, reviews, evidence records, Git state, and broad memory/milestone bodies do not belong in normal Controller routing. `context task-show` is diagnostic-only.

Every active task starts with one fresh execution child using `fork_turns=\"none\"`. The child receives or loads its own role pack directly; the parent Controller must not consume child-only working material. The Controller may then add Investigator, Curator, Reasoning Specialist, or Reviewer children only when the bounded result shows that role is needed. Use native completion/mailbox observation; there is no Thaliris worker, scheduler, polling loop, or retry runtime.

Codex hook configuration is separate from current-session observation. A project `.codex/hooks.json` proves only configuration; input rewriting, root classification, payload fidelity, and native task delivery remain `UNKNOWN` until a live compatible session observes them. Unknown tools and unverified MCP paths remain `UNKNOWN`/fail-open.
"""

ROLE_PACKS = """<!-- thaliris-role-packs:v3 -->
# Thaliris Role Packs

Load this document when the compact managed router is insufficient.

## Controller

The Controller routes work and accepts completion. It starts from the default
low-noise `context task-status` packet and explicitly selects the facts,
constraints, decisions, unknowns, contradictions, and artifact pointers needed
for the current step. Raw findings, review bodies, evidence records, Git status,
parent history, child transcripts, tool output, and broad memory/milestone
bodies do not propagate automatically. Durable memory is retained but never
automatically injected into role projections. If historical context may matter,
explicitly run `context recall "query" --role ROLE`; recall returns routed
candidates only and does not accept or propagate them. `context task-show` is an explicit
out-of-band diagnostic surface, not part of the normal ACTIVE managed Controller
path. If context is insufficient, request a targeted fresh follow-up or
explicitly pass a selected artifact/payload; do not rebuild the full working set.

Use `docs/thaliris-benchmark-protocol.md` as the authoritative evidence and
review-convergence contract. Register reusable artifacts before the dependent
decision, select only the facts needed by the next role, and record downstream
consumption. Classify each review finding as MECHANICAL, LOCAL_SEMANTIC, or
ARCHITECTURAL. The first two receive one fresh Implementer Correction Packet
and one fresh targeted Reviewer; only the last may reopen broad investigation.

Every active task uses serial fresh execution children with `fork_turns=\"none\"`.
This cuts implicit parent-task-history propagation, not all context: applicable
system/developer instructions, AGENTS, custom-agent instructions, environment,
native tool context, and delegation content may still be present. A non-none
fork is denied and must be retried explicitly. The child loads its own Thaliris
role projection directly, performs the assigned role, does not create
child-to-child workflow, and explicitly selects the information to return to
the persistent Controller. The Controller must not consume child-only working
material automatically; a large selected payload is allowed when necessary.
During an ACTIVE task the persistent Controller does not perform repository
investigation or source mutation; dispatch does not change those permissions.
`task-close` and acceptance require an authorized reservation, matching child
`SubagentStart`, successfully emitted Core projection, and matching
`SubagentStop` for the active task. Pending reservations and started managed
children remain serial in flight. PostToolUse records dispatch only; it is not
a completion signal.

For a local, obvious microtask, that one fresh Implementer is still required,
followed by deterministic verification; the persistent Controller does not edit
source directly. Larger work adds only the roles needed by risk and unknowns.
After dispatch, use native surviving-child/thread continuation when the current
Codex surface provides it. Otherwise use one sufficiently long native blocking
wait per real external dependency; after timeout, check status once and wait
again if still running. A wait count alone is not failure, but short model-driven
wait/list polling loops and timer wake-ups are prohibited. Thaliris does not
implement scheduling, deadlines, or agent lifecycle.

After targeted investigation, escalate to
`agent_type="thaliris-reasoning-specialist"` with `fork_turns="none"` only
when a material implementation choice remains unresolved by available
evidence: two or more materially different fixes remain plausible, an OPEN
unknown or contradiction could change the choice, a cross-module
state/lifecycle/ownership/concurrency/compatibility choice remains undecided,
the facts are known but a substantive trade-off remains, or a Reviewer finds a
design question rather than a mechanical correction. Do not escalate based
only on task size, file count, or token count. Pass an explicit Decision
Context containing the decision question, confirmed relevant facts, competing
options, must-preserve invariants and compatibility contracts,
decision-changing unknowns or contradictions, and relevant evidence or
artifact pointers. Do not pass the full Investigator working set or an empty
"help me decide" request.

Before spawning an Implementer, explicitly accept every Sol conclusion that
will affect implementation by recording it as a task Decision, Constraint, or
Modification Boundary, or by placing it in the selected Implementer handoff.
Never rely on an implicit Sol-to-child history transfer. The Reasoning
Specialist has no direct Core semantic-state write permission.

Reasoning Specialists make one bounded decision attempt. They must not rebuild
an Investigator working set or perform open-ended repository searches. When a
decision-changing fact is missing, return `NEED_EVIDENCE` with an
`EvidenceRequest` (decision question, missing fact, why it can change the
decision, preferred evidence surface, and verification requirement), finish,
and let the Controller route a fresh Investigator. The Investigator persists a
bounded evidence artifact; the Controller selects its relevant facts and starts
a fresh Reasoning Specialist. If selected evidence is materially contradictory
and cannot be safely resolved, return `INSUFFICIENT_OR_CONTRADICTORY` with the
conflicting references and stop. Reviewers are fresh one-shot children on every
round; preserve findings and evidence, not their conversation trajectory. Use
native surviving-child/thread continuation when the current Codex surface
provides it. Otherwise use one sufficiently long native blocking wait per real
external dependency; after timeout, check status once and wait again if still
running. A wait count alone is not failure, but short model-driven wait/list
polling loops and timer-driven wake-ups are prohibited. Close completed one-shot
Sol/Reviewer children with native controls. Thaliris does not implement
scheduling, deadlines, or agent lifecycle.

After a qualifying completed child, the Controller may run only the exact
Verification Target when it is a known test command family: pytest, npm/pnpm/
yarn test, cargo test, go test, or dotnet test. A target never authorizes an
arbitrary shell command.

Known local PreToolUse surfaces used by managed mode are mechanically guarded.
This is automatic projection isolation, not filesystem confidentiality or
universal tool enforcement: hosted, specialized, and unverified runtime
surfaces remain outside the claimed envelope. Hook configuration is separate
from current-session observation; current hook-definition evidence is required
before claiming a live observation.

## Evidence Roles

Investigators may keep a large private working set, but when another role will
reuse the result they persist a bounded repo-relative Evidence Artifact first.
The artifact preserves reusable facts, evidence refs, affected files/symbols,
verification performed, unknowns, and contradictions; it does not preserve the
exploration transcript or repeated tool output. Investigator completion messages
should contain only the artifact path, finding/evidence IDs, short outcome, and
remaining decision-changing unknowns. The Controller registers the pointer with
`context task-artifact --base-revision N --id ID --path repo/relative --summary
TEXT --producer-role investigator` and selects relevant content; artifact
existence does not authorize automatic full-text projection. Registration
computes and stores the artifact content identity. Downstream roles do not
receive it automatically: select the facts, constraints, contradictions,
compatibility or lifecycle invariants, evidence summaries, unknowns, artifact
pointers, and any other information that could materially change the next
decision. Do not dump the investigation process merely for convenience, but do
explicitly provide as much selected detail as correctness requires. Curators
receive only the material explicitly selected for the current snapshot and may
replace that snapshot. Reasoning Specialists receive a Decision Context selected
for the current unresolved decision, not raw history; it may include relevant
facts, competing hypotheses, contradictions, evidence summaries, compatibility
invariants, pointers, unknowns, or other selected detail. If it is insufficient,
state what evidence is needed so the Controller can request a targeted fresh
follow-up. Implementers receive the explicit Modification Boundary and required
verification. Reviewers receive selected intent, changed surface, constraints,
decisions, and evidence, then independently decide what needs deeper inspection.
Role defaults guide work; they are not semantic firewalls or semantic
allowlists.

Use focused checks while changing code and one complete relevant validation at the
end. Requested runtime or visible-behavior verification remains required.

## State And Retention

`active_work` and `pending_results` are short controller-visible labels. Use
`context task-artifact --base-revision N --id ID --path repo/relative --summary TEXT
--producer-role investigator` to append a path-safe pointer to external work.
Only the Controller registers the pointer; change the producer role when the
producer is not an Investigator. Registration computes and stores the artifact
content identity. Artifact
contents remain outside the status packet and are never automatically injected
into another role. A pointer is selective access, not a compression mandate:
pass it when the next role needs to decide whether to read it. Raw task state
remains diagnostic-only in `.context/state.json`.

Artifact registration does not hide a path from review: Reviewer `Changed Surface`
continues to show Git-reported changes, without automatically exposing file contents.

At task end, promote only reusable decisions, constraints, invariants, failure
modes, and material milestone progress or completed verification through
`context task-promote`. Route memory and milestones through their INDEX files;
do not treat this layer as a scheduler, transcript store, or automatic summary.
"""

# Exact byte hashes for documents emitted by prior adapter releases.  Ownership
# is deliberately binary: a one-character user edit makes the file user-owned.
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
            return {"ok": True, "changed": False, "backup": None, "files": [], "manual_migration_required": manual, "instruction_definition_changed": False, "hook_definition_changed": False, "agent_profile_changed": False, "session_restart_required": False, "hook_trust_required": False, **_activation_fields(root)}
        hook_changed = ".codex/hooks.json" in writes
        instruction_changed = any(path in {"AGENTS.md", "AGENTS.override.md"} for path in writes)
        profile_changed = any(path.startswith(".codex/agents/") for path in writes)
        return {"ok": True, "changed": True, "backup": core._apply_with_backup(root, writes, [], "codex-init"), "files": sorted(writes), "manual_migration_required": manual, "instruction_definition_changed": instruction_changed, "hook_definition_changed": hook_changed, "agent_profile_changed": profile_changed, "session_restart_required": instruction_changed or hook_changed or profile_changed, "hook_trust_required": hook_changed, **_activation_fields(root)}


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
    return {"ok": True, "changed": bool(files), "backup": backup, "files": sorted(files), "manual_migration_required": manual, "instruction_definition_changed": instruction_changed, "hook_definition_changed": hook_changed, "agent_profile_changed": profile_changed, "session_restart_required": instruction_changed or hook_changed or profile_changed, "hook_trust_required": hook_changed, **_activation_fields(root)}


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
    return {"ok": True, "changed": bool(files), "backup": backup, "files": sorted(files), "migration": "v2", "migrated": migrated, "manual_migration_required": manual, "migration_backup": backup, "instruction_definition_changed": instruction_changed, "hook_definition_changed": hook_changed, "agent_profile_changed": profile_changed, "session_restart_required": instruction_changed or hook_changed or profile_changed, "hook_trust_required": hook_changed, **_activation_fields(root)}


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
    # A task is a Core object.  Starting one cannot prove that this already
    # running Codex session reloaded project hooks, AGENTS, or agent profiles.
    result["managed_readiness"] = {
        "status": "UNKNOWN",
        "reason": "current Codex session hook/profile activation has not been observed",
        **_activation_fields(core._repo_root(root)),
    }
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
    return f"Obtain your Thaliris role context by running `context prepare --role {role}` in this fresh child, then perform the assigned task and explicitly select the information to return. Large selected details are allowed when needed for correctness. Do not delegate to another child."


def prepare_child(root: Path, role: str) -> dict[str, object]:
    """Load a role projection from inside the child runtime boundary."""
    role = semantic_role(role)
    if role not in core._PACK_ROLES or role == "controller":
        raise ValueError("child role must be an execution role")
    return core.prepare(root, None, role)


def task_close(root: Path, base_revision: int) -> dict[str, object]:
    state = core.task_show(root)["state"]
    task_id = str(state["task_id"])
    if not intent_audit.qualifying_child_completed(core._repo_root(root)):
        raise ValueError("task-close requires an authorized native SubagentStart, an emitted Core projection, a matching session/turn/type SubagentStop, and no pending or active managed work")
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
    root = core._repo_root(root)
    result = report(root)
    observations: list[tuple[int, int, dict[str, object]]] = []
    events: set[str] = set()
    compatible_profile_observed = False
    expected = intent_audit.managed_hook_spec_hash()
    for path in (root / ".context" / "audit").glob("*/runtime.json"):
        try:
            runtime = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        current = isinstance(runtime, dict) and runtime.get("managed_hook_spec_hash") == expected and runtime.get("adapter_protocol_version") == intent_audit.CODEX_ADAPTER_PROTOCOL_VERSION
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
    latest = max(observations, default=None, key=lambda item: (item[0], item[1]))
    latest_item = latest[2] if latest is not None else None
    health = intent_audit.hooks_health(root)
    lifecycle_start = lifecycle_stop = False
    for path in (root / ".context" / "audit" / "lifecycle").glob("*.json"):
        try:
            lifecycle = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(lifecycle, dict) or lifecycle.get("version") != intent_audit.LIFECYCLE_STATE_VERSION or lifecycle.get("managed_hook_spec_hash") != expected or lifecycle.get("adapter_protocol_version") != intent_audit.CODEX_ADAPTER_PROTOCOL_VERSION:
            continue
        for child in lifecycle.get("children", []):
            if isinstance(child, dict) and isinstance(child.get("started"), int):
                lifecycle_start = True
                lifecycle_stop = lifecycle_stop or isinstance(child.get("stopped"), int)
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
        # A hook response was emitted locally, but only a native child probe
        # can show that Codex delivered additionalContext to the child.
        "role_projection_injection_observed": "UNKNOWN",
        "controller_activation_bridge": "CODEX_NATIVE",
        **_activation_fields(
            root,
            profile_native_active="UNKNOWN",
            project_layer_activation="UNKNOWN",
            compatible_profile_observed="YES" if compatible_profile_observed else "UNKNOWN",
            compatible_project_hooks_observed="YES" if events else "UNKNOWN",
        ),
    }
    task = result.get("context", {}).get("task_state", {}) if isinstance(result.get("context"), dict) else {}
    target = task.get("verification_target") if isinstance(task, dict) else None
    if isinstance(target, str) and intent_audit._ACCEPTANCE_COMMAND.fullmatch(target):
        target_capability = "TARGET_EXECUTABLE_BY_CODEX"
    elif target is not None:
        target_capability = "TARGET_REQUIRES_EXTERNAL_ATTESTATION"
    else:
        target_capability = "UNKNOWN"
    result["verification_capability"] = {"target": target_capability, "terminal_status": "TERMINAL_STATUS_UNAVAILABLE"}
    return result
