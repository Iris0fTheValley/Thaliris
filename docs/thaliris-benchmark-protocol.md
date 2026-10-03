# Thaliris Benchmark Protocol

The runtime-neutral product rules are defined in
`docs/thaliris-routing-protocol.md`. This document only defines how a
benchmark observes, freezes, and scores those rules.

This document is an observation and scoring protocol. The product semantics
are authoritative only in `docs/thaliris-routing-protocol.md`; this document
does not add requirements to ordinary Thaliris tasks.

## Evidence lifecycle

Reusable evidence is required only when a result must cross a role boundary:

```text
need -> fresh Investigator -> bounded artifact -> Controller registration
     -> selected facts -> downstream Investigator, Curator, Reasoning Specialist, Implementer, or Reviewer -> decision/implementation/review
```

The Controller registers the artifact pointer before the dependent decision with
`context task-artifact --base-revision N --id ID --path repo/relative
--summary TEXT --producer-role investigator` (or the corresponding curator role).
Registration computes the artifact content identity. An artifact record must
identify its producer role, task and revision,
repo-relative path and content SHA-256, source references, affected
files/symbols, confirmed facts, inferences, unknowns, contradictions, and
verification performed. Registration must precede the dependent decision.
Selection and every downstream consumer must be recorded separately. Selecting
an artifact pointer is not consumption: selected-fact propagation must name at
least one evidence item, or a downstream native session must read the exact
pointer/content identity.

Formal collection accepts only a frozen source registry. Core/audit,
native-rollout, host-attestation, and evaluator-result streams have separate
allowlists and source identities; an arbitrary JSONL file is not a native fact.
Candidate identities are filesystem-grounded under an explicit frozen policy;
`.gitignore` and directory names do not decide the observable surface.

The benchmark records the actual producer, registration, selection, consumer,
and byte-identity events. It does not prescribe a particular file-writing tool.

The artifact pointer is selective access, not automatic full-text injection.
Content changes make the pointer stale. A replacement must explicitly name the
superseded artifact; stale or contradictory artifacts cannot remain silently
active. A fast path records `evidence_required=NOT_REQUIRED` when no reusable
cross-role evidence exists.

## Review convergence

Review is conditional on the Controller selecting an independent challenge.
When no Reviewer was selected, the benchmark records that absence and does
not require review attestations. Every selected fresh Reviewer returns either
a bounded READY verdict or a bounded Review
Packet. A Review Packet contains:

```text
finding_id
classification = MECHANICAL | LOCAL_SEMANTIC | ARCHITECTURAL
affected_surface
violated_invariant
verification_requirement
```

MECHANICAL and LOCAL_SEMANTIC findings require a fresh bounded Implementer
Correction Packet followed by a fresh targeted Reviewer. A distinct later
finding may continue the correction graph; an unchanged finding/candidate/
evidence state may not repeat the same cognitive cycle. The packet
contains only the finding, affected surface, invariant, and verification
requirement; it does not carry Reviewer conversation history. An
ARCHITECTURAL finding is the only classification that may reopen broad
investigation or reasoning. A source mutation after READY invalidates that
review and requires another fresh Reviewer. External interruption is
`EXTERNALLY_INCOMPLETE`, never PASS.

For each review round the host records `review-start`, the native fresh
Reviewer lifecycle, the verdict, native completion, and `review-end`. The
host-computed candidate identity at review-start must equal the identity at
review-end. A verdict from a changed or incomplete review transaction is not
accepted. Native sandbox mode is recorded as a host capability diagnostic;
review correctness is the unchanged-candidate transaction proof.

## Candidate and cost proof

The host harness computes an append-only stage attestation immediately at
runtime-final, review-start, review-end, verification-start, evaluator-start,
and seal.
The same immutable candidate identity must be observed at each applicable
stage; review-start and review-end apply only when Reviewer was selected. A
later mutation invalidates the chain. Reviewer sandbox mode is a native session fact,
not a candidate attestation field.

Telemetry reports observed-all invocations, including failed or orphaned child
sessions. Model identity and session token totals remain raw observations.
Raw usage, API-equivalent cost, benchmark validity, evaluator quality, and
routing/provenance validity have separate statuses. Missing or malformed cost
telemetry does not change benchmark correctness; malformed token counts make
the cost status `FAIL` and missing billing facts make it `NOT_OBSERVED`.

The [GPT-6 Standard pricing snapshot](../benchmarks/abcd/pricing_gpt6_standard_20260930.json)
records user-supplied official OpenAI API facts dated 2026-09-30 in USD per
million tokens. It is an API-equivalent metric, not observed Codex ChatGPT-plan
billing or allowance cost. Actual allowance cost remains `NOT_OBSERVED` without
direct billing telemetry. Standard rates apply through 272,000 prompt tokens;
above that threshold, input, cached-input, and cache-write rates double and
output rates increase by 1.5 for the entire request. Other tiers need their
own verified snapshot and are currently `NOT_OBSERVED`.

Exact GPT-6 cost requires every session's full request ledger, with each
request's model, tier, input, cached input, output, cache-write applicability
and count when applicable, prompt-size context fact, and captured event
provenance. Request totals must equal the observed session total. The current
Codex v0.155.1 normalized rollout supplies cumulative session usage but no
such complete billing ledger, so current formal GPT-6 cost is normally
`NOT_OBSERVED`. The collector preserves explicit billing request records only
when they occur in a frozen rollout source; it never reconstructs them from
cumulative usage. Historical GPT-5.6 replay uses its prior three-rate basis.
The old D6b/D10c dollar thresholds apply only to that historical basis; no
current GPT-6 cost threshold is asserted without a comparable current baseline.
Reasoning tokens are diagnostic only. Waiting is reported separately from
model-driven polling.

## Fast path

A simple task can use one fresh Implementer and deterministic verification.
The result records routing, sessions, calls, observed usage, cost status,
quality, and evidence requirement.

## Documentation consistency

The benchmark validator checks the authoritative routing-protocol identity,
generated project projections, and the effective native profile definitions as
separate facts. It identifies profiles by TOML `name` in both personal and
project agent directories. Equivalent definitions preserve both provenance
records; conflicting definitions with the same name fail closed. Project trust
configuration alone does not prove that a project-only definition is active.
Runtime observations are reported separately from supported behavior and host
limitations.
