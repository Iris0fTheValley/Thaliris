# Shared Thaliris Role Responsibilities

Core publishes host-neutral semantics, not native model profiles or child prompts.
The [routing protocol](thaliris-routing-protocol.md) owns the shared handoff,
mutation/evidence loop and Workstream endpoints. Adapters render the effective
native role instructions from their own canonical sources.

| Role | Responsibility and boundary |
| --- | --- |
| Controller | Direction, scope, invariants, acceptance, context selection, next routing; implementation methods belong to executor. |
| Investigator | Broad facts and evidence with exact locations, covered/uncovered scope and unknowns; no architecture decisions. Scanner is its nested discovery pattern. |
| Implementer | Stable accepted direction through deterministic convergence and assigned local closure. |
| Focused Implementer | Full reasoning/implementation/runtime-feedback/revision loop across coupled invariants; returns at semantic convergence before ordinary closure. |
| Reviewer | Fresh independent non-writing challenge of original acceptance, invariants and cross-boundary evidence; supported critical closure, not absence of blockers, permits READY. |
| Reasoning Specialist | Independent challenge to selected framing and decision basis; no implementation, broad fact gathering or final decision. |
| Curator | Reconcile selected reusable knowledge and relevant semantic INDEX links with exact supplied sources; no automatic corpus scan or architecture decisions. |
| Verifier | Read-only compatibility role, not a mandatory stage or replacement for independent semantic review. |

Every child uses the authorized parent's selected handoff, keeps its private working
set private, and returns conclusion, key findings, decision-changing unknowns,
contradictions, verification observations and optional repo-relative Artifact refs.
Decision-changing dependencies end the Workstream in FINAL for Controller judgment.
Native delegation capability and isolation remain adapter-specific. See the
[Codex generated profiles](https://github.com/Iris0fTheValley/Thaliris-codex/blob/main/docs/thaliris-role-packs.md)
and DSH's editable role templates; they are not interchangeable Host contracts.
