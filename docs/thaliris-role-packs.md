# Shared Thaliris Role Responsibilities

Core publishes host-neutral semantics, not native model profiles or child prompts.
The [routing protocol](thaliris-routing-protocol.md) owns the shared handoff,
mutation/evidence loop and Workstream endpoints. Adapters render the effective
native role instructions from their own canonical sources.

| Role | Responsibility and boundary |
| --- | --- |
| Controller | Own direction, scope, invariants, acceptance criteria, context selection, next routing and product acceptance; integrate the candidate, criterion-linked evidence and existing evidence, then decide whether the request is met. |
| Investigator | Broad facts and evidence with exact locations, covered/uncovered scope and unknowns; no architecture decisions. Scanner is its nested discovery pattern. |
| Implementer | Implement and verify stable accepted direction within the assigned boundary; report criterion-linked evidence and `UNKNOWN` through deterministic convergence and assigned local closure. |
| Focused Implementer | Full reasoning/implementation/runtime-feedback/revision loop across coupled invariants; verifies and reports criterion-linked evidence and `UNKNOWN`, then returns at semantic convergence before ordinary closure. |
| Reviewer | Optional fresh independent non-writing challenge of the candidate against selected criteria, invariants and cross-boundary evidence; supported critical closure, not absence of blockers, permits `READY` for that review. |
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

The Controller integrates the user's original objective and acceptance criteria,
the candidate, Implementer or Focused Implementer reports and existing evidence,
then decides product acceptance. It may request additional verification or route
repair when needed; no fixed closing handoff, lifecycle stage or new Agent is
required. Keep the outcomes
distinct: test `PASS` reports checks run, native child `Completed` reports execution
termination, Reviewer `READY` reports its selected review, and Core `DONE` records
mechanical closure. None alone decides product acceptance.
