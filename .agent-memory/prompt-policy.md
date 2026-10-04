---
Evidence: Core docs/thaliris-role-packs.md and docs/thaliris-routing-protocol.md at 99ff867; Thaliris-Codex src/thaliris_codex/roles.py and src/thaliris_codex/codex_adapter.py at 9cce14c
Revision: 2
Status: CURRENT
Applicability: PROJECT
Confidence: SOURCE_VERIFIED
Kind: HARD_CONSTRAINT
Audience: ["controller", "implementer", "reviewer"]
Topics: ["executor-boundaries", "handoff", "semantic-review"]
Symbols: ["Focused Implementer", "Reviewer", "Workstream"]
---

# Prompt policy

This note summarizes current, source-verified role and handoff boundaries. The Core documents and Codex adapter source agree; this source check does not establish native installation or activation.

## Focused Implementer endpoint

Focused Implementer returns FINAL after the candidate is semantically coherent, hard invariants hold, decision-changing unknowns are resolved, and focused evidence demonstrates the core semantics, with no remaining work likely to change the causal model, architecture, contract, scope, acceptance, or direction. It continues only checks or repairs that could still change the core solution; a focused-test PASS alone does not establish the endpoint. Afterward, ordinary regression, lint, build, generated or documentation sync, mechanical compatibility, deterministic fixes, installation, and Git closure belong to a fresh ordinary Implementer Workstream when assigned. This role-specific endpoint controls over shared same-session closure guidance. Installation feedback that reveals a semantic defect remains in the Focused Workstream while it could change the core solution.

## Controller handoff

Before an ordinary implementation handoff, the Controller resolves ambiguity that the request and confirmed facts can settle. Include the goal, confirmed facts and source of truth, starting state and modification boundary, original acceptance and semantic stopping condition, hard invariants, decided boundaries or contracts, direction-changing unknowns, and material known execution-path constraints. State recommendations as non-binding and leave implementation methods to the assigned role. Bound open-ended cleanup, documentation, synchronization, or migration by its specific discrepancy or transformation; stop when original acceptance is met.

## Independent review and repair

Reviewer is optional, independent, and non-writing. Review the original acceptance, hard invariants, and affected cross-boundary behavior, not only the internal diff. Treat unverified critical acceptance as UNKNOWN or insufficient evidence. Tie findings to accepted criteria. For a bounded defect with accepted semantics unchanged, a fresh ordinary correction handoff carries the finding, invariant, affected surface, and needed validation; omit review history, transcripts, and private working material. A changed decision basis returns to the Controller. Reviewer does not repair.

This current wording supersedes the earlier weaker Focused Implementer endpoint that could leave deterministic operational closure inside the same focused session. Earlier wording remains historical in repository history; this refinement does not change role definitions, model/profile selection, or memory authority.

Canonical detail: [Implementer and Focused Implementer](../docs/thaliris-role-packs.md#implementer-and-focused-implementer) and the [routing protocol](../docs/thaliris-routing-protocol.md).
