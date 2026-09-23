"""The Codex adapter's mechanical role registry.

This module is deliberately limited to mechanical role facts.  Controller
routing remains model-authored, and Core has no dependency on this registry.
The registry includes the persistent Controller entry for CLI compatibility;
only entries with a native profile participate in the named-role lifecycle.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RoleDefinition:
    """Mechanical facts used by the Codex adapter for one role."""

    id: str
    default_model: str
    reasoning_effort: str | None
    native_profile: str | None
    instructions: str
    repo_write_allowed: bool
    delegation_allowed: bool
    controller_control_state_modification_allowed: bool
    generated_profile: bool
    profile_filename: str | None
    legacy_profile_hashes: frozenset[str] = frozenset()
    native_aliases: tuple[str, ...] = ()
    telemetry_notice: bool = False
    write_denial_code: str | None = None
    write_denial_reason: str | None = None
    orchestration_metric: str | None = None


_SHARED_INSTRUCTIONS = (
    "The Controller's explicit native spawn message is your sole task-specific input. "
    "Do not reconstruct task state from unselected durable material, and do not infer unselected "
    "memory, milestone, Artifact, finding, decision, or review content. Keep repository "
    "reads, tool output, test logs, and intermediate exploration in your private working "
    "set. Return a distilled result with Conclusion, Key findings, Decision-changing "
    "unknowns, Contradictions if any, Verification performed, and Artifact refs if detailed "
    "reusable material was retained. Do not delegate to another authorized native Codex role session. "
    "Facts unknown route to Investigator; facts known but the decision is difficult, the decision "
    "basis is invalidated, or a hard boundary must be revised route to Reasoning Specialist; a "
    "decided packet routes to Implementer; an independent challenge routes to Reviewer. Difficulty "
    "alone is not a Reasoning Specialist trigger. "
)


def _instructions(role: str) -> str:
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
            "Core does not supply semantic completion authority. If an assigned correction cannot "
            "be completed without an unverified external fact, an invalidating accepted invariant, "
            "or changing the decision basis, do not expand scope; return that dependency as a "
            "decision-changing unknown to the Controller."
        ),
        "verifier": (
            "Act as an optional read-only implementation-readiness filter after a fresh Implementer. "
            "Check acceptance coverage; the diff against the Controller-decided Modification Boundary; "
            "source/generated/docs synchronization; call sites and residual references; actual focused "
            "and deterministic test results; migration and compatibility fixtures; generated versus "
            "user-owned files; obvious lifecycle or protocol inconsistencies; contradictions; and "
            "decision-changing unknowns. Treat workspace anomalies as observations, not candidate "
            "defects, unless the candidate introduced them, the modification boundary owns them, or "
            "acceptance requires changing them. Historical/generated ownership must come from exact "
            "independent historical evidence; current HEAD must not establish its own historical "
            "authority. Express READY, LOCAL_DEFECTS, or DECISION_REOPEN only as "
            "model prose. A locally clean result may be worth an independent Terra Reviewer only when "
            "deep semantic or architectural review adds real value; Luna Verifier does not replace "
            "deep Terra review when authority, provenance, Host lifecycle, identity, trust, migration, "
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
            "the accepted design unchanged may go to a fresh Implementer. Return findings and a distilled "
            "verdict; the Controller decides what follows."
        ),
    }
    return _SHARED_INSTRUCTIONS + role_instruction[role]


# Exact SHA-256 identities of bytes emitted by earlier Thaliris adapters.
# These are role-owned installation metadata, not a current-HEAD ownership
# claim.  Keeping them with the profile definitions preserves safe migration.
_LEGACY_PROFILE_HASHES = {
    "investigator": frozenset("0720619c1d0b85b80a2981597fcd60086a1bddc7f03f48f88cc8f75c1128d872 199d7b9cb1fb8d1a3536df07395a420b9476ee66d13a4a9ca6d6442215d9e7b8 44781edb6a654db482adafdc20b16f75cdebded2e62e8d86376aefc577a3ae55 f5623ba40d585b1760511344488d71c53e8c08a8c0ad8cbd1b76b268ae02c70f 55ef42ac18d46ed5fe2c624ed0be2c16956ab4fe91dd1e64b6ef3a07bae01cb1 307a3e90b32cf7dcde3cac3c683b3e16f5e13c147191e82e45109a75a6984ff4 188e8cc62bfd8e1f37f3068193deb37431c5ea49356adc99b8873a47e817fbdd caa08fc96fdcff0a47fa05cb8ebba32d93a3336fec64b0a9c93d5467cc3009be c917f0b601dcd689afbb443b98c6b12733d5738ed908a112a5c7948f3321edf9 4fe5345865638896c3cc042a66e1853d5d969763d64b6e9076b6d3bc25fe3091".split()),
    "curator": frozenset("8026959290edeb86d66ee86f9b5db286e7fb31c28c95ec2c42ec8be7f2cda515 f6827c30074554b809b50414bde31146354ec6898fe8bd13a43402134c8b6476 a98489c08e6af01165629b6848667700956d749bf8a676a30ac479c729d916fa 64fece15a4e47b77641039abbf9f7c9a1daab4581b9faa0c066fd7d0c7cab4d4 d11534e931c1c17b51bd846a487ac6609b56db018f5abb6b5ed6991b5b6a71b3 b902b77ca7f0f77f6305cb8bec3e7bf1c8386805a312b816e2a99e1794e9a1f7 0467fdaba8aeefb76b52d10995778e4e01a2f98c7dec05da58134abad0feccff".split()),
    "reasoning-specialist": frozenset("7e596a38e95606b684b17f25cc0eecb3163aef7d65d36110f6496b3ab7d53692 960190bb4b67b02e7616bcf6dbd71192bcc79327fb0ed72e6f23b3815819afd0 d2191d59621e2765ae7642ca1648d96b4dbfb1a82293a8a02bf8642328fb58a7 60a87a06e97602f10f7f3842061c6eba551e78f76a8fa99b17ba377f48d22117 13b3283ad629bb6d32fe3613462694be14fba3a24c547aa791e1e651c0b3106d 17616dddc351c20f5c98a30a0506253322d0cc5f6480d89690c7a08a70592557 5a22321413193d571a4a3b9189d45951ffda93cefde26f2f3999982233d17a01 813b16ca10985e8e602ee3295eb093115de4505db9cdc9cc6cbd9ef9ad192efd 708bee8d038cdd44bc8b75ee399ff8de09fa9a65e9d46f7060d75a82f04c19aa 1fa5af05b543d22efc20cc8eb7813da51e63a63c58b02bea6c2109918aa5d9d9 b7a6c8ae5655205dbb16a7d90af09a06a21daad78170cc8e55509304770d5b10".split()),
    "implementer": frozenset("a91e41c67930071db4d6eb45342526cbbf67af6d4fda13d1c847d18f28816a35 a1c7a46981512c7e8067dd5e40e193a0b54e34384aefc2b28950d5c6ccb5af9a d24ee0de8a22409bd5a3c9f1359079c4d6c7ccfbb14f65842e84f21ab0a5aa96 360d49c46afe280f85d6857575a12a9eeeff93d1f9aedb4b00ef2a2aa7c8b078 4028038b2153e56881140dabdc9165d2d1866fa737635e33599dc4d3cef0342f a463ea49f2cc308b6457ab63612a5f6b257f7462470118537961315b8e757ed1 fd0e28d2f1cce4f639a34b123bd647c9cd64d8b90fd5fb54a1e8353ecde924ad 7f85c22eb8ca508622b39bb8708e6bd617de3139f9de012ee29d166d4a3aad1e 3fcfcf2a04a8ef9e3a5c52f7414664b3a0d0fbc7f036c2558da1cb8baf955d95 0780f180cd71a9b6a73fef0eb61ca42f32fd048ccd12b0564f2afd68e7ed6143 55c1ea16853dcc4f5a4617005e57a939cd4dcd773e2fd24c5e0911ea3c9e90c0".split()),
    "verifier": frozenset("df6b0e82979329f15318356d060c2321095a2de7941539dfa0e007f08f2c2ff4 fa1585e8df2c9136eed055f22e85594805c62a0cec0d6387700dd4959fe9dc19".split()),
    "reviewer": frozenset("ae56701985a1d27a2daea326819fa0e93b4350eb6e65d1a299daf198126a7a9a c43274a3f9cb3f93cd662b6477f1dfd07c170c24324c1364df5f59205851b17b d0f488e226888c6a8f6e39ab1deeb1125d3c0e9474dba47af47ec3eab2da45c2 ae51394874f0b35dc2b39577d471bf2f07533962363cdb7ad56e6e08a3860887 322534fb6f2b2abc312bd04a76e477e3e128cf6a194da5817ecaabd0678aa397 b038486edb2c381631e458adac2bff12fbcdc09233b5b1b8f59aeee9dc0e9774 720ef66c9f6023d961ddc1a3329ec4ae3fdf7fe2f6b1252034a7117f5990a125 4cec33fef9151d2ba60483a72b49ccd7dadd0b5c044a69f00f468e71c489fe07 8999980daf617644a36da7579626f122b6c279ad54e055bbaf8242daedbd36c2 b9b3b50f89b1dd7c5f5eaf2ee558b6881b014d66f6b30bc20244f361ebc721d7 e281f8c25451cbccb1509fa07814e4cfeaa8ae113402fc2db9a6c63a165bc1e6 96257cc1ed5c88b37de73e2c355c17c6b1ab26620210effe5b3283c776d0e4b9 357e9364404a2ab249c27ad3a2c93305f38db5afbbec1b56b58ee5e0817d5602 82b410c617589d410deb33f1ff4163d49b22d329ee517442a004965115a46124 fe082be2c5d05675b3ab9a69234851d505db3a3deddb509794b817f5b59a8ab8".split()),
}


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
) -> RoleDefinition:
    return RoleDefinition(
        id=role,
        default_model=model,
        reasoning_effort=effort,
        native_profile=f"thaliris-{role}",
        instructions=_instructions(role),
        repo_write_allowed=repo_write,
        delegation_allowed=False,
        controller_control_state_modification_allowed=False,
        generated_profile=True,
        profile_filename=f"thaliris-{role}.toml",
        legacy_profile_hashes=_LEGACY_PROFILE_HASHES[role],
        native_aliases=aliases,
        telemetry_notice=notices,
        write_denial_code=write_denial_code,
        write_denial_reason=write_denial_reason,
        orchestration_metric=orchestration_metric,
    )


# This insertion order is the public CLI order.  Native role consumers derive
# their inventories from the values instead of maintaining another role set.
ROLE_REGISTRY: dict[str, RoleDefinition] = {
    "controller": RoleDefinition(
        id="controller",
        default_model="gpt-5.6-sol",
        reasoning_effort=None,
        native_profile=None,
        instructions="",
        repo_write_allowed=False,
        delegation_allowed=True,
        controller_control_state_modification_allowed=True,
        generated_profile=False,
        profile_filename=None,
    ),
    "investigator": _native_role("investigator", "gpt-5.6-luna", "xhigh", aliases=("luna", "luna-investigator")),
    "curator": _native_role("curator", "gpt-5.6-luna", "xhigh", aliases=("luna-curator",), notices=True),
    "reasoning-specialist": _native_role("reasoning-specialist", "gpt-5.6-sol", "xhigh", aliases=("sol-high", "reasoning-specialist-sol"), notices=True),
    "implementer": _native_role("implementer", "gpt-5.6-luna", "xhigh", aliases=("terra-implementer",), orchestration_metric="implementer_rounds"),
    "verifier": _native_role(
        "verifier", "gpt-5.6-luna", "xhigh", repo_write=False, notices=True,
        write_denial_code="THALIRIS_VERIFIER_WRITE_BLOCKED",
        write_denial_reason="Verifier must remain an independent non-writing checker.",
    ),
    "reviewer": _native_role(
        "reviewer", "gpt-5.6-terra", "high", aliases=("terra-reviewer",), repo_write=False, notices=True,
        write_denial_code="THALIRIS_REVIEWER_WRITE_BLOCKED",
        write_denial_reason="Reviewer must remain an independent non-writing checker.",
        orchestration_metric="reviewer_rounds",
    ),
}


def role_definition(role: str) -> RoleDefinition | None:
    """Return a semantic role definition without accepting native aliases."""
    return ROLE_REGISTRY.get(role)


def role_choices() -> tuple[str, ...]:
    return tuple(ROLE_REGISTRY)


def native_role_definitions() -> tuple[RoleDefinition, ...]:
    return tuple(definition for definition in ROLE_REGISTRY.values() if definition.native_profile is not None)


def native_agent_roles() -> dict[str, str]:
    return {definition.native_profile: definition.id for definition in native_role_definitions() if definition.native_profile}


def native_codex_role_map() -> dict[str, str]:
    values = native_agent_roles()
    for definition in native_role_definitions():
        values.update({alias: definition.id for alias in definition.native_aliases})
    return values


def native_profile_names() -> frozenset[str]:
    return frozenset(native_agent_roles())


def agent_profiles() -> dict[str, tuple[str, str | None, str]]:
    return {
        definition.profile_filename: (definition.default_model, definition.reasoning_effort, definition.id)
        for definition in native_role_definitions()
        if definition.generated_profile and definition.profile_filename is not None
    }


def role_aliases() -> dict[str, str]:
    return native_codex_role_map()


def notice_roles() -> frozenset[str]:
    return frozenset(definition.id for definition in native_role_definitions() if definition.telemetry_notice)


def repo_write_allowed(role: str) -> bool:
    definition = role_definition(role)
    return definition is not None and definition.repo_write_allowed


def delegation_allowed(role: str) -> bool:
    definition = role_definition(role)
    return definition is not None and definition.delegation_allowed


def control_state_modification_allowed(role: str) -> bool:
    definition = role_definition(role)
    return definition is not None and definition.controller_control_state_modification_allowed


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
    for definition in ROLE_REGISTRY.values():
        profile = definition.native_profile or "(root)"
        effort = definition.reasoning_effort or "(host/task)"
        install = definition.profile_filename or "(not generated)"
        writes = "YES" if definition.repo_write_allowed else "NO"
        delegation = "YES" if definition.delegation_allowed else "NO"
        control = "YES" if definition.controller_control_state_modification_allowed else "NO"
        lines.append(f"| `{definition.id}` | `{definition.default_model}` | `{effort}` | `{profile}` | {writes} | {delegation} | {control} | `{install}` |")
    return ("\n".join(lines) + "\n").encode("utf-8")
