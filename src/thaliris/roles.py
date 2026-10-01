"""The Codex adapter's mechanical role registry.

This module is deliberately limited to mechanical role facts.  Controller
routing remains model-authored, and Core has no dependency on this registry.
The registry includes the persistent Controller entry for CLI compatibility;
only entries with a native profile participate in the named-role lifecycle.
"""
from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class RoleSpec:
    """Semantic identity and instructions for one adapter role.

    The Core package deliberately does not consume this object.  It belongs
    to the Codex adapter and is kept separate from native execution facts so
    that a role's meaning is not coupled to one host binding.
    """

    id: str
    instructions: str
    purpose: str = ""


@dataclass(frozen=True)
class CodexExecutionBinding:
    """Mechanical Codex execution facts for one role."""

    model: str | None = None
    reasoning_effort: str | None = None
    native_profile: str | None = None
    astra_medium_native_profile: str | None = None
    exceptional_native_profile: str | None = None
    native_aliases: tuple[str, ...] = ()
    generated_profile: bool = False
    profile_filename: str | None = None
    repo_write_allowed: bool = False
    allowed_delegation_targets: frozenset[str] = frozenset()
    controller_control_state_modification_allowed: bool = False
    legacy_profile_hashes: frozenset[str] = frozenset()
    telemetry_notice: bool = False
    write_denial_code: str | None = None
    write_denial_reason: str | None = None
    orchestration_metric: str | None = None
    role_id: str = ""

    @property
    def default_model(self) -> str | None:
        """Compatibility spelling used by the phase-one adapter API."""
        return self.model


@dataclass(frozen=True)
class RoleRegistration:
    """The single ordered registry entry: one semantic spec and one binding."""

    spec: RoleSpec
    binding: CodexExecutionBinding

    @property
    def id(self) -> str:
        return self.spec.id


# A descriptive alias makes the pair easy to discover for external adapter
# consumers without creating a second registry.
RoleBinding = RoleRegistration


@dataclass(frozen=True)
class RoleDefinition:
    """Phase-one compatibility view of a role registration.

    New code should use :func:`get_role` and :func:`get_codex_binding`.  This
    flattened constructor remains available for existing tests and external
    adapter consumers while the canonical registry stores ``RoleSpec`` plus
    ``CodexExecutionBinding``.
    """

    id: str
    default_model: str | None
    reasoning_effort: str | None
    native_profile: str | None
    instructions: str
    repo_write_allowed: bool
    allowed_delegation_targets: frozenset[str]
    controller_control_state_modification_allowed: bool
    generated_profile: bool
    profile_filename: str | None
    legacy_profile_hashes: frozenset[str] = frozenset()
    native_aliases: tuple[str, ...] = ()
    telemetry_notice: bool = False
    write_denial_code: str | None = None
    write_denial_reason: str | None = None
    orchestration_metric: str | None = None
    exceptional_native_profile: str | None = None
    astra_medium_native_profile: str | None = None

    @property
    def spec(self) -> RoleSpec:
        return RoleSpec(self.id, self.instructions)

    @property
    def binding(self) -> CodexExecutionBinding:
        return CodexExecutionBinding(
            model=self.default_model,
            reasoning_effort=self.reasoning_effort,
            native_profile=self.native_profile,
            astra_medium_native_profile=self.astra_medium_native_profile,
            exceptional_native_profile=self.exceptional_native_profile,
            native_aliases=self.native_aliases,
            generated_profile=self.generated_profile,
            profile_filename=self.profile_filename,
            repo_write_allowed=self.repo_write_allowed,
            allowed_delegation_targets=self.allowed_delegation_targets,
            controller_control_state_modification_allowed=self.controller_control_state_modification_allowed,
            legacy_profile_hashes=self.legacy_profile_hashes,
            telemetry_notice=self.telemetry_notice,
            write_denial_code=self.write_denial_code,
            write_denial_reason=self.write_denial_reason,
            orchestration_metric=self.orchestration_metric,
        )


_SHARED_INSTRUCTIONS = (
    "Your authorized parent's explicit native spawn message is your sole task-specific input. "
    "Do not reconstruct task state from unselected durable material, and do not infer unselected "
    "memory, milestone, Artifact, finding, decision, or review content. Keep repository "
    "reads, tool output, test logs, and intermediate exploration in your private working set. "
    "Do not send ordinary progress, heartbeat, or partial-completion messages to the parent. "
    "A decision-changing unknown that requires a Controller decision ends your assigned "
    "Workstream: return it "
    "in FINAL. Do not send MESSAGE and remain ACTIVE for a wait. "
    "Work only within the responsibility and scope stated in the handoff. Preserve its stated "
    "invariants and boundaries; do not guess when missing or conflicting information could "
    "change direction. Report that dependency as a decision-changing unknown. Keep role "
    "terms distinct: Investigator, Implementer, and Focused Implementer are semantic roles. "
    "Scanner is a nested Investigator discovery working pattern, not a separate role. Executor "
    "is a category for Implementer and Focused Implementer, not a selectable or spawnable role; use their "
    "actual role names when routing. Native execution profiles choose model and effort for a "
    "semantic role and do not create another role. Investigator establishes facts and gathers broad evidence; "
    "Reasoning Specialist independently challenges framing and its decision basis; Implementer "
    "and Focused Implementer make local implementation decisions within their assigned packet "
    "and Workstream; Reviewer independently challenges a converged candidate. No child is a "
    "second semantic Controller. Only the Controller "
    "decides task direction, overall scope, acceptance, and what follows. Return a distilled "
    "result with Conclusion, Key findings, Decision-changing unknowns, Contradictions if any, "
    "Verification performed, and Artifact refs if detailed reusable material was retained. "
)

_EXECUTOR_INSTRUCTIONS = (
    " The Controller routes Workstreams. Executors close local loops inside them. A semantic "
    "checkpoint is not necessarily a scheduling checkpoint. Workstream names the semantic "
    "routing unit, not a role or second Controller. Once the Workstream goal, authority, and "
    "boundary are known, batch the relevant source, test, "
    "generation, and documentation reads, form a plan, and make coherent edits before seeking "
    "another reasoning round. Avoid per-patch, per-read, or per-grep reasoning rounds unless "
    "new information could change direction. A stable Workstream may include multiple local "
    "closures completed in this same authorized Implementer session: implement, run focused "
    "verification, fix ordinary in-scope failures, synchronize generated output and project "
    "documentation, run needed integration verification, inspect diff and status, and complete "
    "assigned Git closure. A local verification PASS does not require returning to Root; continue "
    "the assigned work while the next step remains within its goal, scope, invariants, and "
    "acceptance. Ordinary test fixes, generated or documentation sync, integration checks, and "
    "assigned Git closure are available execution checkpoints, not a mandatory bundle or separate "
    "semantic routing boundaries. Root chooses the semantic boundary and may assign a separate "
    "closure Workstream when its remainder is independently deterministic. A new semantic Workstream "
    "may use a different role; the profile chosen for one Workstream does not bind the task's "
    "remaining operational work. A local verification "
    "PASS alone neither ends the Workstream nor requires further work to stay in it. "
    "Continuous execution authority never expands Controller-assigned scope. Only the Controller "
    "decides task direction, ownership, observable semantics, accepted architecture or security boundaries, hard invariants, compatibility, "
    "acceptance, and the next semantic handoff. If new evidence changes any of those or reveals "
    "an unverified external dependency, stop and return the concrete decision-changing unknown "
    "in FINAL. When the handoff selects completed Investigator "
    "discovery from an earlier semantic slice, start from its confirmed facts, exact source "
    "locations and affected surfaces, relevant unknowns or contradictions, and covered and "
    "uncovered scope. Directly reopen decision-critical originals, call chains, diffs, and "
    "tests as needed for implementation. Do not reconstruct the same broad inventory or "
    "delegate a Scanner over the covered surface. A fresh Scanner may collect only a genuinely "
    "uncovered decision-changing evidence gap needing independent broad discovery. "
    "Keep the working set focused. Directly read "
    "known, decision-critical sources. Delegate discovery over a larger or unknown evidence surface, "
    "or a large low-reasoning-density collection, when doing so removes an independent working set. "
    "This includes broad repository scans, exhaustive call-site search, residual-reference checks, "
    "and other large mechanical investigation. "
    "Use Scanner output as evidence; retain responsibility for implementation decisions. "
    "Work only within the assigned semantic Workstream and preserve Controller decisions and "
    "invariants; return a decision-changing unknown instead of changing them. Close the "
    "Workstream at its semantic boundary with distilled "
    "state, its commit reference, and verification evidence, then discard its detailed working set. "
    "Match verification to the changed behavior and its concrete regression surface. Start with "
    "focused checks for the changed contract, generated output, and acceptance. If they pass "
    "without a failure, anomaly, or new broader-risk evidence, continue any remaining assigned "
    "local closures within the Workstream. Broaden only for a concrete compatibility or "
    "integration risk. After a test fix, rerun the smallest acceptance-relevant range and "
    "continue the Workstream. A commit, push, or final report alone does not call for another "
    "test run. Do not use file, tool, token, time, or local-closure counts to choose the profile "
    "or end a Workstream, and do not add a second semantic Controller or stopping state machine. "
    "Scanner is the nested Investigator discovery working pattern, not another role. Delegate "
    "that work by spawning only a fresh Investigator role session with fork_turns=\"none\" "
    "and no model or effort override. Durable-knowledge admission belongs only to the Controller: "
    "do not keep or return a separate memory-candidate list, select or spawn Curator, or add a "
    "durable-governance product to FINAL. Return the normal distilled result, evidence, and any "
    "decision-changing information; the Controller decides at the task's natural end whether "
    "selected knowledge merits durable maintenance."
)

_FOCUSED_SCANNER_INSTRUCTIONS = (
    " Focused Implementer handles complex implementation as well as focused judgment; the "
    "stronger profile is not limited to deciding. Directly inspect known, decision-critical "
    "sources, including source code, relevant call chains, the current diff, failed tests, and "
    "raw evidence that bears on the decision. When the target is known, read it directly. "
    "Focused Implementer handles sustained reasoning across coupled invariants, nonlocal effects, "
    "or constraints within the Controller's goal, hard invariants, scope, and acceptance. "
    "Delegate one independent discovery working set to a fresh Investigator session using the "
    "Scanner working pattern when a larger or unknown evidence surface must be discovered, "
    "enumerated, filtered, or classified, or when a clearly large low-reasoning-density collection "
    "can be compressed independently. "
    "Ask it for key conclusions, exceptions, UNKNOWNs, and accurate raw locations. The Scanner "
    "narrows a collection; its choice of collection does not predetermine which evidence is "
    "relevant, and it does not replace reasoning-coupled reading. After it returns, "
    "targeted reopening of relevant originals to verify findings is useful. There is no per-read "
    "delegation deliberation or file, token, or search-count threshold; small local searches may "
    "be direct. Delegate when doing so removes the discovery working set and leaves "
    "reasoning and implementation with you. Wait only while the Scanner is known unfinished and "
    "its result is necessary for this Workstream. After its FINAL, use the distilled result and do not "
    "wait on that Scanner again or repeat its discovery pass. Continue complex implementation within the "
    "assigned Workstream across local execution checkpoints when it still benefits from focused "
    "reasoning. A local verification PASS does not force a return to Root or switch models. "
    "Focused Implementer owns semantic convergence of its implementation candidate. Return FINAL "
    "when a coherent candidate has its core implementation and hard invariants in place, "
    "decision-changing unknowns resolved, focused evidence that "
    "demonstrates core semantics, and no remaining work likely to change the causal model, scope, "
    "acceptance, or direction. A focused-test PASS alone does not meet this boundary or trigger "
    "a role switch. Include in that handoff the "
    "candidate state and exact source locations or diff, the invariants satisfied, focused evidence "
    "and its limits, the explicit remaining tasks, acceptance, and the escalation boundary. "
    "Documentation, generated output, configuration, installation, Host smoke checks, fixtures, "
    "and Git closure are not automatically required before this boundary; include any check needed "
    "to prove the candidate's core semantics before returning it. Installation or smoke feedback "
    "that exposes a semantic defect stays with Focused Implementer while it is needed to establish "
    "the candidate. The Controller decides whether remaining work still depends on the core model "
    "and needs a fresh Focused Implementer Workstream or is an independent deterministic closure "
    "for an ordinary Implementer. Do not assume the tail belongs to either role. Very small direct "
    "routine operations need no ceremonial child handoff when the Controller is already authorized "
    "to perform them; this does not change delegated, controller-direct, or single-agent authority. "
    "A FINAL child is complete and cannot be resumed; any further work uses a fresh session and "
    "Controller handoff. If semantic evidence changes the accepted architecture or causal model, "
    "security boundary, hard invariant, compatibility, "
    "scope, acceptance, or direction, stop and return the decision-changing issue to Root rather "
    "than redesigning it."
)

_FOCUSED_SOL_INSTRUCTIONS = (
    " With the Sol Focused Implementer profile, consider offloading broad or exhaustive "
    "peripheral call-site, rollout/log, and residual-reference collections when it removes "
    "an independent working set."
)

_FOCUSED_ASTRA_INSTRUCTIONS = (
    " With an explicitly user-authorized Astra Focused Implementer profile, explore evidence "
    "needed for the current Workstream directly. Delegate only a clearly large, low-reasoning-density "
    "collection that can be compressed independently. When the solution path is unstable and "
    "framing, exploration, implementation, runtime feedback, and remodeling are coupled, own "
    "the bounded explore-understand-implement-run-observe-revise loop within the Controller's "
    "goal, hard invariants, scope, and acceptance. This does not change those boundaries."
)

_REVIEWER_SCANNER_INSTRUCTIONS = (
    " Keep the working set focused on the independent semantic judgment. Use only bounded local "
    "reading needed for semantic judgment of the candidate. Preferentially delegate broad "
    "repository scanning, "
    "exhaustive search, rollout/log scans, call-site enumeration, residual checks, and large "
    "mechanical evidence collection as Scanner work to a fresh Investigator role session with "
    "fork_turns=\"none\" "
    "and no model or effort override. Use its evidence while retaining independent "
    "responsibility for review decisions. Do not routinely perform those broad collections "
    "yourself merely because you can."
)


def _instructions(role: str) -> str:
    role_instruction = {
        "investigator": (
            "Act in the Investigator semantic role. Scanner names its nested discovery working "
            "pattern, not a second role. Investigate facts, scan large working sets, and "
            "compress evidence, without making architecture decisions. Batch related searches "
            "and reads, return compact facts, and once evidence is sufficient stop immediately; "
            "do not expand the scan for one more confirmation. Return a distilled selection map "
            "with confirmed facts and exact source locations and affected surfaces, relevant "
            "unknowns or contradictions, and the scope covered and left uncovered, so the "
            "Controller can select later work. For inventories grouped into areas such as A, B, "
            "and C, state covered and uncovered scope by area. "
            "Do not delegate. "
            "You may save detailed reusable material as a "
            "repo-relative Artifact; return only its pointer and the distilled result by default."
        ),
        "curator": (
            "Reconcile only the Controller-selected durable-knowledge candidates under `.agent-memory/` "
            "and their relevant links in `.agent-memory/INDEX.md`, using the supplied facts and "
            "supporting evidence, exact selected prior memory, and canonical sources/documents in "
            "the handoff. Do not "
            "blindly append or duplicate canonical text. A concise recovery entrance may summarize "
            "and link easy-to-locate material or preserve a decision basis spread across code, Host, "
            "history, or design; do not impose a fixed split between memory and formal documentation. "
            "If the selected material is already sufficient, explicitly report that existing material "
            "is sufficient and no write is needed. Preserve provenance and scope for each retained claim; when new "
            "evidence updates or supersedes a conclusion, retain its original scope and historical "
            "applicability where relevant. Keep the corpus small, current, non-conflicting, and "
            "traceable; modify, merge, split, revise, narrow, supersede, or delete only selected "
            "entries when justified. "
            "Do not preserve task chronology, implementation logs, ordinary commit histories, transient "
            "test outputs, or momentary failures as logs; these sources are not automatic exclusions "
            "when they establish reusable knowledge that can improve, constrain, or accelerate a future "
            "decision or recovery. If consistency depends on durable material the Controller did not "
            "select, stop and report the missing knowledge area for the Controller to select; do not "
            "scan the corpus. Product or protocol documentation and README changes aligned with current "
            "behavior belong to Implementer or Focused Implementer. Curator is optional and runs only "
            "when the Controller's natural end-of-task judgment finds selected knowledge worth "
            "maintaining; task size or architecture work alone never triggers it. Do not scan broadly, "
            "make architecture decisions, or delegate. Keep detailed raw evidence in canonical sources, "
            "Artifacts, Git, or rollout records, with only the concise basis and references needed for "
            "future recovery in memory. Your output is an ordinary result or Artifact; there is no "
            "Curator Core state."
        ),
        "reasoning-specialist": (
            "Act as an independent metacognitive challenger of the selected framing and decision "
            "basis. Examine hidden assumptions, the causal model, decomposition, boundaries, "
            "premature convergence, and alternatives that could materially change direction. "
            "Challenge a framing even when it appears coherent, and examine unexpected outcomes "
            "when they may reveal a faulty assumption or causal model. Stay grounded in the "
            "supplied information; distinguish evidence from inference and explain what would "
            "change the conclusion. Do not gather broad facts, implement, conduct routine review, "
            "solve an ordinary hard problem for its own sake, or make the final task decision. "
            "Report the strongest material challenge, any direction-changing alternative, and "
            "critical missing facts for the Controller to route. Do not delegate or reconstruct "
            "unselected task history."
        ),
        "implementer": (
            "Implement only an implementation task packet containing Goal, confirmed facts, hard "
            "invariants, Controller-decided boundaries/contracts, decision-changing unknowns, "
            "non-binding recommendations/advice, and acceptance. Only Controller decisions, "
            "invariants, and acceptance are binding; recommendations/advice are not contract. "
            "Do not silently drop, guess, or freeze an unknown that changes direction. Prove Host "
            "protocol, serialization, identity, or native schema through an Investigator, source, "
            "or real-shaped fixture before implementation. Report verification as observations; "
            "Core does not supply semantic completion authority. If an assigned correction cannot "
            "be completed without an unverified external fact, an invalidating accepted invariant, "
            "or changing the decision basis, do not expand scope; return that dependency as a "
            "decision-changing unknown to the Controller. Keep formal project documentation, "
            "including product/protocol docs and README, within the assigned Workstream synchronized "
            "with verified behavior."
        ),
        "verifier": (
            "Retained for compatibility only, not recommended as a workflow stage. Do not delegate. "
            "Act as a read-only implementation-readiness filter after a fresh Implementer or "
            "Focused Implementer session. "
            "Check acceptance coverage; the diff against the Controller-decided Modification Boundary; "
            "source/generated/docs synchronization; call sites and residual references; actual focused "
            "and deterministic test results; migration and compatibility fixtures; generated versus "
            "user-owned files; obvious lifecycle or protocol inconsistencies; contradictions; and "
            "decision-changing unknowns. Treat workspace anomalies as observations, not candidate "
            "defects, unless the candidate introduced them, the modification boundary owns them, or "
            "acceptance requires changing them. Historical/generated ownership must come from exact "
            "independent historical evidence; current HEAD must not establish its own historical "
            "authority. Express READY, LOCAL_DEFECTS, or DECISION_REOPEN only as "
            "model prose. A locally clean result may be worth an independent Reviewer only when "
            "deep semantic or architectural review adds real value; Verifier does not replace "
            "independent review when authority, provenance, Host lifecycle, identity, trust, migration, "
            "or bootstrap semantics still warrant independent challenge. Do not write, route, or treat "
            "this filter as mandatory."
        ),
        "reviewer": (
            "Act as an independent non-writing checker of the candidate named in the handoff. "
            "After a real problem, understand its invariant and inspect adjacent legal states "
            "enough to return independent related blockers in one pass. A finding that overturns an "
            "accepted invariant, depends on an unproved external capability, makes feasibility uncertain, "
            "or changes a Controller boundary is a decision-basis failure: route it back to the Controller "
            "for a decision reopen, not directly to correction. Only a local implementation defect with "
            "the accepted design unchanged may go to a fresh Implementer. Challenge semantic drift "
            "between the candidate and its formal project documentation when relevant. Return findings and a distilled "
            "verdict; the Controller decides what follows."
        ),
    }
    base_role = "implementer" if role == "focused-implementer" else role
    result = _SHARED_INSTRUCTIONS + role_instruction[base_role]
    if role in {"implementer", "focused-implementer"}:
        result += _EXECUTOR_INSTRUCTIONS
        if role == "focused-implementer":
            result += _FOCUSED_SCANNER_INSTRUCTIONS
    elif role == "reviewer":
        result += _REVIEWER_SCANNER_INSTRUCTIONS
    return result


def profile_instructions(role: str, profile_name: str) -> str:
    """Add working-style guidance only to the matching Focused profile."""
    spec = get_role(role)
    if spec is None:
        raise ValueError(f"unknown role: {role}")
    if role != "focused-implementer":
        return spec.instructions
    if profile_name == "thaliris-focused-implementer":
        return spec.instructions + _FOCUSED_SOL_INSTRUCTIONS
    if profile_name in {"thaliris-focused-implementer-astra-medium", "thaliris-focused-implementer-xhigh"}:
        return spec.instructions + _FOCUSED_ASTRA_INSTRUCTIONS
    raise ValueError(f"unknown focused profile: {profile_name}")


# Exact SHA-256 identities of bytes emitted by earlier Thaliris adapters.
# These are role-owned installation metadata, not a current-HEAD ownership
# claim.  Keeping them with the profile definitions preserves safe migration.
# The 9b5bcf2 Curator profile is pinned below because its exact bytes become
# legacy when the Curator instructions change; the historical renderer is
# independently exercised in tests/test_roles.py.
_LEGACY_PROFILE_HASHES = {
    # Exact Investigator profile emitted by ec1ad7b immediately before the
    # result-contract update; tests re-render it from that immutable revision.
    "investigator": frozenset("0720619c1d0b85b80a2981597fcd60086a1bddc7f03f48f88cc8f75c1128d872 199d7b9cb1fb8d1a3536df07395a420b9476ee66d13a4a9ca6d6442215d9e7b8 44781edb6a654db482adafdc20b16f75cdebded2e62e8d86376aefc577a3ae55 f5623ba40d585b1760511344488d71c53e8c08a8c0ad8cbd1b76b268ae02c70f 55ef42ac18d46ed5fe2c624ed0be2c16956ab4fe91dd1e64b6ef3a07bae01cb1 307a3e90b32cf7dcde3cac3c683b3e16f5e13c147191e82e45109a75a6984ff4 188e8cc62bfd8e1f37f3068193deb37431c5ea49356adc99b8873a47e817fbdd caa08fc96fdcff0a47fa05cb8ebba32d93a3336fec64b0a9c93d5467cc3009be c917f0b601dcd689afbb443b98c6b12733d5738ed908a112a5c7948f3321edf9 4fe5345865638896c3cc042a66e1853d5d969763d64b6e9076b6d3bc25fe3091 ee818487dd21dacd9040e710d0fa3b4ca32524407d70981e03d11a600dcb81a6".split()),
    "curator": frozenset("8026959290edeb86d66ee86f9b5db286e7fb31c28c95ec2c42ec8be7f2cda515 f6827c30074554b809b50414bde31146354ec6898fe8bd13a43402134c8b6476 a98489c08e6af01165629b6848667700956d749bf8a676a30ac479c729d916fa 64fece15a4e47b77641039abbf9f7c9a1daab4581b9faa0c066fd7d0c7cab4d4 d11534e931c1c17b51bd846a487ac6609b56db018f5abb6b5ed6991b5b6a71b3 b902b77ca7f0f77f6305cb8bec3e7bf1c8386805a312b816e2a99e1794e9a1f7 0467fdaba8aeefb76b52d10995778e4e01a2f98c7dec05da58134abad0feccff 7779da9180597f1235f2c3893088743b0baafa55b4edad1e9319774f88ae8e6a".split()),
    "reasoning-specialist": frozenset("7e596a38e95606b684b17f25cc0eecb3163aef7d65d36110f6496b3ab7d53692 960190bb4b67b02e7616bcf6dbd71192bcc79327fb0ed72e6f23b3815819afd0 d2191d59621e2765ae7642ca1648d96b4dbfb1a82293a8a02bf8642328fb58a7 60a87a06e97602f10f7f3842061c6eba551e78f76a8fa99b17ba377f48d22117 13b3283ad629bb6d32fe3613462694be14fba3a24c547aa791e1e651c0b3106d 17616dddc351c20f5c98a30a0506253322d0cc5f6480d89690c7a08a70592557 5a22321413193d571a4a3b9189d45951ffda93cefde26f2f3999982233d17a01 813b16ca10985e8e602ee3295eb093115de4505db9cdc9cc6cbd9ef9ad192efd 708bee8d038cdd44bc8b75ee399ff8de09fa9a65e9d46f7060d75a82f04c19aa 1fa5af05b543d22efc20cc8eb7813da51e63a63c58b02bea6c2109918aa5d9d9 b7a6c8ae5655205dbb16a7d90af09a06a21daad78170cc8e55509304770d5b10".split()),
    "focused-implementer": frozenset("b4ff152b4a3978f31c7b80891a839bf1bd8408336fe19b2c8c27d42bf88d0311 9b412596980063afae0a4678043e09ca6f3509735e55f373119c3da3655831ef 501fc4fc95c883f9249c649e6477a7d98babd97e41942b036da94e0086c3f662".split()),
    "implementer": frozenset("a91e41c67930071db4d6eb45342526cbbf67af6d4fda13d1c847d18f28816a35 a1c7a46981512c7e8067dd5e40e193a0b54e34384aefc2b28950d5c6ccb5af9a d24ee0de8a22409bd5a3c9f1359079c4d6c7ccfbb14f65842e84f21ab0a5aa96 360d49c46afe280f85d6857575a12a9eeeff93d1f9aedb4b00ef2a2aa7c8b078 4028038b2153e56881140dabdc9165d2d1866fa737635e33599dc4d3cef0342f a463ea49f2cc308b6457ab63612a5f6b257f7462470118537961315b8e757ed1 fd0e28d2f1cce4f639a34b123bd647c9cd64d8b90fd5fb54a1e8353ecde924ad 7f85c22eb8ca508622b39bb8708e6bd617de3139f9de012ee29d166d4a3aad1e 3fcfcf2a04a8ef9e3a5c52f7414664b3a0d0fbc7f036c2558da1cb8baf955d95 0780f180cd71a9b6a73fef0eb61ca42f32fd048ccd12b0564f2afd68e7ed6143 55c1ea16853dcc4f5a4617005e57a939cd4dcd773e2fd24c5e0911ea3c9e90c0".split()),
    "verifier": frozenset("df6b0e82979329f15318356d060c2321095a2de7941539dfa0e007f08f2c2ff4 fa1585e8df2c9136eed055f22e85594805c62a0cec0d6387700dd4959fe9dc19".split()),
    "reviewer": frozenset("ae56701985a1d27a2daea326819fa0e93b4350eb6e65d1a299daf198126a7a9a c43274a3f9cb3f93cd662b6477f1dfd07c170c24324c1364df5f59205851b17b d0f488e226888c6a8f6e39ab1deeb1125d3c0e9474dba47af47ec3eab2da45c2 ae51394874f0b35dc2b39577d471bf2f07533962363cdb7ad56e6e08a3860887 322534fb6f2b2abc312bd04a76e477e3e128cf6a194da5817ecaabd0678aa397 b038486edb2c381631e458adac2bff12fbcdc09233b5b1b8f59aeee9dc0e9774 720ef66c9f6023d961ddc1a3329ec4ae3fdf7fe2f6b1252034a7117f5990a125 4cec33fef9151d2ba60483a72b49ccd7dadd0b5c044a69f00f468e71c489fe07 8999980daf617644a36da7579626f122b6c279ad54e055bbaf8242daedbd36c2 b9b3b50f89b1dd7c5f5eaf2ee558b6881b014d66f6b30bc20244f361ebc721d7 e281f8c25451cbccb1509fa07814e4cfeaa8ae113402fc2db9a6c63a165bc1e6 96257cc1ed5c88b37de73e2c355c17c6b1ab26620210effe5b3283c776d0e4b9 357e9364404a2ab249c27ad3a2c93305f38db5afbbec1b56b58ee5e0817d5602 82b410c617589d410deb33f1ff4163d49b22d329ee517442a004965115a46124 fe082be2c5d05675b3ab9a69234851d505db3a3deddb509794b817f5b59a8ab8".split()),
}
# Exact profile-generator outputs from immutable pre-update revision
# 3094c0a69a620780558b535cf6aaf0f91ea66b62, retained for safe upgrades.
_LEGACY_PROFILE_HASHES["implementer"] |= frozenset({"3d393a145c900749c33296550e740bf61af64b91d2b4cf3462cb2c44e1d65195"})
_LEGACY_PROFILE_HASHES["focused-implementer"] |= frozenset({
    "cdced1431108b7b55b022b70e6129ca4b4c298c560a3a972a2f8805474bcff21",
    "d4fef2b7b5e77d027b4d3e0807fdeb3a6bc6d81f3cf8aabf41affce7b912e573",
    "8f6890bfa3ad76b2a0401a04f33a4e7494ea91b3cb266b749f1d72a7cbf8aba7",
})


# Exact prior generator output from immutable 5e6554196d27c4d6bc87c2a8008bd3c37ef01b31:
# roles.py blob 481aba1ef66448238f1b00ff4b58eba3f28f9605 and adapter blob
# 880d5a9753220bcf09f27bc34890e411ccee17c4. Fixed fixtures verify these bytes.
_PHASE_TWO_PROFILE_HASHES = {
    "investigator": "9dced30afe1b03a07b948d4c26b3de970dff9d742f46d1e1b103122fab049454",
    "curator": "9b4f8dca546f9dce5246059bf66c07cdeb78690917be3932220a45d9a1555d17",
    "reasoning-specialist": "99176890683a18228c36fa2d207824c44f85c3f565e874a321a7f911984ce56f",
    "implementer": "b987e6ab3844c51fcfaf715d3bec87d2b1fe6ba26c2e22e41ecfda2ad2f946d1",
    "verifier": "8b1d70c1979319ba6cee33ac5341afa977064b006484f8f1718ba59bc939f419",
    "reviewer": "bbf4f45c69f169aa45e288673c9d2f37ba72d397444ca739aff66f6d9d51c1ba",
}
for _role, _digest in _PHASE_TWO_PROFILE_HASHES.items():
    _LEGACY_PROFILE_HASHES[_role] |= frozenset({_digest})


def _native_role(
    role: str,
    model: str,
    effort: str,
    *,
    aliases: tuple[str, ...] = (),
    repo_write: bool = True,
    notices: bool = False,
    write_denial_code: str | None = None,
    write_denial_reason: str | None = None,
    orchestration_metric: str | None = None,
) -> RoleRegistration:
    # ``get`` is intentional: a newly declared role has no historical
    # generated bytes until an independent migration fixture is supplied.
    spec = RoleSpec(
        id=role,
        purpose=role.replace("-", " ").capitalize(),
        instructions=_instructions(role) if role in {
            "investigator", "curator", "reasoning-specialist", "implementer", "focused-implementer", "verifier", "reviewer",
        } else "",
    )
    binding = CodexExecutionBinding(
        model=model,
        reasoning_effort=effort,
        native_profile=f"thaliris-{role}",
        astra_medium_native_profile=f"thaliris-{role}-astra-medium" if role in {"focused-implementer", "reasoning-specialist"} else None,
        exceptional_native_profile=f"thaliris-{role}-xhigh" if role in {"focused-implementer", "reasoning-specialist"} else None,
        native_aliases=aliases,
        generated_profile=True,
        profile_filename=f"thaliris-{role}.toml",
        repo_write_allowed=repo_write,
        allowed_delegation_targets=frozenset({"investigator"}) if role in {"implementer", "focused-implementer", "reviewer"} else frozenset(),
        controller_control_state_modification_allowed=False,
        legacy_profile_hashes=_LEGACY_PROFILE_HASHES.get(role, frozenset()),
        telemetry_notice=notices,
        write_denial_code=write_denial_code,
        write_denial_reason=write_denial_reason,
        orchestration_metric=orchestration_metric,
    )
    return RoleRegistration(spec, binding)


# This insertion order is the public CLI order.  Native role consumers derive
# their inventories from the values instead of maintaining another role set.
ROLE_REGISTRY: dict[str, RoleRegistration | RoleDefinition | tuple[RoleSpec, CodexExecutionBinding]] = {
    "controller": RoleRegistration(
        RoleSpec(id="controller", purpose="Persistent root Controller", instructions=""),
        CodexExecutionBinding(
            allowed_delegation_targets=frozenset({"investigator", "curator", "reasoning-specialist", "implementer", "focused-implementer", "verifier", "reviewer"}),
            controller_control_state_modification_allowed=True,
        ),
    ),
    "investigator": _native_role("investigator", "gpt-6-luna", "xhigh", aliases=("luna", "luna-investigator")),
    "curator": _native_role("curator", "gpt-6-luna", "xhigh", aliases=("luna-curator",), notices=True),
    "reasoning-specialist": _native_role("reasoning-specialist", "gpt-6.1-sol", "high", aliases=("sol-high", "reasoning-specialist-sol"), notices=True),
    "implementer": _native_role("implementer", "gpt-6-luna", "xhigh", aliases=("terra-implementer",), orchestration_metric="implementer_rounds"),
    "focused-implementer": _native_role("focused-implementer", "gpt-6.1-sol", "high", orchestration_metric="implementer_rounds"),
    "verifier": _native_role(
        "verifier", "gpt-6-luna", "xhigh", repo_write=False, notices=True,
        write_denial_code="THALIRIS_VERIFIER_WRITE_BLOCKED",
        write_denial_reason="Verifier must remain an independent non-writing checker.",
    ),
    "reviewer": _native_role(
        "reviewer", "gpt-6.1-sol", "high", aliases=("terra-reviewer",), repo_write=False, notices=True,
        write_denial_code="THALIRIS_REVIEWER_WRITE_BLOCKED",
        write_denial_reason="Reviewer must remain an independent non-writing checker.",
        orchestration_metric="reviewer_rounds",
    ),
}


def _registration(role: str) -> RoleRegistration | None:
    """Normalize one registry entry for the query boundary.

    ``RoleDefinition`` and ``(RoleSpec, CodexExecutionBinding)`` are accepted
    only as compatibility input.  The built-in ordered registry uses
    ``RoleRegistration`` directly, and consumers below never need to know
    which representation supplied an entry.
    """
    value = ROLE_REGISTRY.get(role)
    if isinstance(value, RoleRegistration):
        registration = value
    elif isinstance(value, RoleDefinition):
        registration = RoleRegistration(value.spec, value.binding)
    elif isinstance(value, tuple) and len(value) == 2:
        spec, binding = value
        if isinstance(spec, RoleSpec) and isinstance(binding, CodexExecutionBinding):
            registration = RoleRegistration(spec, binding)
        else:
            return None
    else:
        return None

    if registration.spec.id != role:
        raise ValueError(
            "ROLE_REGISTRY key "
            f"{role!r} must match RoleSpec.id {registration.spec.id!r}"
        )
    if registration.binding.role_id not in ("", role):
        raise ValueError(
            "ROLE_REGISTRY binding role_id "
            f"{registration.binding.role_id!r} must match key {role!r}"
        )
    return registration


def get_role(role: str) -> RoleSpec | None:
    """Return the semantic role spec without accepting native aliases."""
    registration = _registration(role)
    return registration.spec if registration is not None else None


def get_codex_binding(role: str) -> CodexExecutionBinding | None:
    """Return the Codex-only mechanical binding for a semantic role id."""
    registration = _registration(role)
    if registration is None:
        return None
    return registration.binding if registration.binding.role_id else replace(registration.binding, role_id=role)


def resolve_native_profile(native_profile: str) -> RoleSpec | None:
    """Resolve an exact native profile or alias to its semantic role spec."""
    for role in role_choices():
        binding = get_codex_binding(role)
        if binding is not None and native_profile in ({binding.native_profile, binding.astra_medium_native_profile, binding.exceptional_native_profile} | set(binding.native_aliases)):
            return get_role(role)
    return None


def iter_codex_bindings() -> tuple[CodexExecutionBinding, ...]:
    """Return native bindings in canonical registry order."""
    bindings: list[CodexExecutionBinding] = []
    for role in role_choices():
        binding = get_codex_binding(role)
        if binding is not None and binding.native_profile is not None:
            bindings.append(binding)
    return tuple(bindings)


def role_definition(role: str) -> RoleDefinition | None:
    """Compatibility view of a role registration.

    Runtime callers should use ``get_role`` and ``get_codex_binding`` instead.
    """
    registration = _registration(role)
    if registration is None:
        return None
    binding = registration.binding
    return RoleDefinition(
        id=registration.spec.id,
        default_model=binding.model,
        reasoning_effort=binding.reasoning_effort,
        native_profile=binding.native_profile,
        astra_medium_native_profile=binding.astra_medium_native_profile,
        exceptional_native_profile=binding.exceptional_native_profile,
        instructions=registration.spec.instructions,
        repo_write_allowed=binding.repo_write_allowed,
        allowed_delegation_targets=binding.allowed_delegation_targets,
        controller_control_state_modification_allowed=binding.controller_control_state_modification_allowed,
        generated_profile=binding.generated_profile,
        profile_filename=binding.profile_filename,
        legacy_profile_hashes=binding.legacy_profile_hashes,
        native_aliases=binding.native_aliases,
        telemetry_notice=binding.telemetry_notice,
        write_denial_code=binding.write_denial_code,
        write_denial_reason=binding.write_denial_reason,
        orchestration_metric=binding.orchestration_metric,
    )


def role_choices() -> tuple[str, ...]:
    identities: dict[str, str] = {}
    filenames: dict[str, str] = {}
    for role in ROLE_REGISTRY:
        registration = _registration(role)
        if registration is None:
            raise ValueError(f"invalid role registration: {role}")
        binding = registration.binding
        for identity in (binding.native_profile, binding.astra_medium_native_profile, binding.exceptional_native_profile, *binding.native_aliases):
            if identity is None:
                continue
            if identity in identities:
                raise ValueError(f"duplicate native profile or alias: {identity}")
            identities[identity] = role
        for filename in (binding.profile_filename, f"{binding.astra_medium_native_profile}.toml" if binding.astra_medium_native_profile else None, f"{binding.exceptional_native_profile}.toml" if binding.exceptional_native_profile else None):
            if filename is not None:
                if filename in filenames:
                    raise ValueError(f"duplicate profile filename: {filename}")
                filenames[filename] = role
    return tuple(ROLE_REGISTRY)


def native_role_definitions() -> tuple[RoleDefinition, ...]:
    return tuple(
        definition
        for role in role_choices()
        for definition in (role_definition(role),)
        if definition is not None and definition.native_profile is not None
    )


def native_agent_roles() -> dict[str, str]:
    return {
        profile: role
        for role in role_choices()
        for binding in (get_codex_binding(role),)
        if binding is not None and binding.native_profile is not None
        for profile in (binding.native_profile, binding.astra_medium_native_profile, binding.exceptional_native_profile)
        if profile is not None
    }


def native_codex_role_map() -> dict[str, str]:
    values = native_agent_roles()
    for role in role_choices():
        binding = get_codex_binding(role)
        if binding is not None and binding.native_profile is not None:
            values.update({alias: role for alias in binding.native_aliases})
    return values


def native_profile_names() -> frozenset[str]:
    return frozenset(native_agent_roles())


def agent_profiles() -> dict[str, tuple[str, str | None, str]]:
    values = {
        binding.profile_filename: (binding.model, binding.reasoning_effort, role)
        for role in role_choices()
        for binding in (get_codex_binding(role),)
        if binding is not None and binding.generated_profile and binding.profile_filename is not None
    }
    for binding in iter_codex_bindings():
        if binding.generated_profile and binding.astra_medium_native_profile:
            values[f"{binding.astra_medium_native_profile}.toml"] = ("gpt-6-astra", "medium", binding.role_id)
        if binding.generated_profile and binding.exceptional_native_profile:
            values[f"{binding.exceptional_native_profile}.toml"] = ("gpt-6-astra", "xhigh", binding.role_id)
    return values


def role_aliases() -> dict[str, str]:
    return native_codex_role_map()


def notice_roles() -> frozenset[str]:
    return frozenset(
        role
        for role in role_choices()
        for binding in (get_codex_binding(role),)
        if binding is not None and binding.native_profile is not None and binding.telemetry_notice
    )


def repo_write_allowed(role: str) -> bool:
    binding = get_codex_binding(role)
    return binding is not None and binding.repo_write_allowed


def delegation_allowed(role: str, target: str) -> bool:
    binding = get_codex_binding(role)
    return binding is not None and (
        role == "controller" and target in native_agent_roles().values()
        or target in binding.allowed_delegation_targets
    )


def control_state_modification_allowed(role: str) -> bool:
    binding = get_codex_binding(role)
    return binding is not None and binding.controller_control_state_modification_allowed


def render_registry_document() -> bytes:
    """Render only mechanical registry facts for the generated role document."""
    lines = [
        "<!-- thaliris-role-registry:v1 -->",
        "# Thaliris Role Registry",
        "",
        "This file is generated from `thaliris.roles.ROLE_REGISTRY`; design and routing guidance remains hand-maintained in `thaliris-role-packs.md`.",
        "",
        "| Role | Model | Reasoning | Native profile | Repo writes | Delegation | Controller-state mutation | Install metadata |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for role in role_choices():
        spec = get_role(role)
        binding = get_codex_binding(role)
        if spec is None or binding is None:
            continue
        profile = binding.native_profile or "(root)"
        effort = binding.reasoning_effort or "(host/task)"
        install = binding.profile_filename or "(not generated)"
        writes = "YES" if binding.repo_write_allowed else "NO"
        delegation = "registered native roles" if role == "controller" else ", ".join(sorted(binding.allowed_delegation_targets)) or "NO"
        control = "YES" if binding.controller_control_state_modification_allowed else "NO"
        lines.append(f"| `{spec.id}` | `{binding.model or '(host/user)'}` | `{effort}` | `{profile}` | {writes} | {delegation} | {control} | `{install}` |")
    lines.extend(["", "Controller-only exceptional native profiles (same stable role IDs; defaults above remain unchanged):", ""])
    for binding in iter_codex_bindings():
        if binding.astra_medium_native_profile:
            lines.append(f"- `{binding.astra_medium_native_profile}` → `{binding.role_id}`: `gpt-6-astra`, `medium`; `{binding.astra_medium_native_profile}.toml`.")
        if binding.exceptional_native_profile:
            lines.append(f"- `{binding.exceptional_native_profile}` → `{binding.role_id}`: `gpt-6-astra`, `xhigh`; `{binding.exceptional_native_profile}.toml`.")
    return ("\n".join(lines) + "\n").encode("utf-8")
