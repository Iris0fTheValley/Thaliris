## Repository bootstrap

- Before substantial work in a Git repository, check whether the current repository has an initialized Thaliris control layer.
- If Thaliris is not initialized, run `context init` from the repository root before investigation, planning, delegation, or substantial edits, then verify it with `context doctor --pretty`.
- If an existing repository contains a pre-rename or otherwise legacy Thaliris control-layer layout, run `context migrate` instead and handle any reported manual migration requirements before relying on routed memory or task state.
- After bootstrap, use the repository's managed `AGENTS.md`, task state, memory, and milestone routing normally.
- Do not run `git init` merely to satisfy this rule. If the workspace is not already a Git repository, initialize Git only when the user explicitly requests it or the task clearly establishes that the workspace is intended to become a repository.

<!-- thaliris:begin -->
## Thaliris

The parent Controller: only Controller delegates, promotes findings, and maintains task control state; children MUST NOT delegate (default concurrency: 1). Roles name responsibilities, not models: current recommendations are Controller/Control Plane, Investigator, and Curator -> GPT-5.6 Luna; Reasoning Specialist -> GPT-5.6 Sol; Implementer and Independent Reviewer -> GPT-5.6 Terra.

Controller is the control plane, not an investigator. Except for minimal state reads required for routing and task control, Controller MUST NOT perform repository investigation, code search, documentation research, Git inspection, runtime probing, exploratory testing, or other fact-gathering work itself. When unknown facts are required, Controller MUST delegate the investigation to an Investigator and consume only its task-local structured findings and evidence references. Controller should own the questions, routing, promotion, integration, and escalation decisions—not the investigation working set. If a required capability is genuinely unavailable to native children, Controller may perform only the minimum capability fallback and must not use that exception to investigate or implement.

An Investigator appends raw findings. Curator is conditional: bounded, structured findings from one Investigator with no evident duplication, conflict, or staleness go directly to Controller; use a fresh Curator only for oversized, repetitive, conflicting, or stale findings, or when high reasoning genuinely needs working-set compression. A Curator maintains only the task-local bounded snapshot. Investigator, Curator, Reasoning Specialist, and Independent Reviewer are all invoked when needed; retain fresh independent review for high-risk changes. An Implementer implements. A persistent Controller MUST NOT directly edit source files, even for a microtask; route every implementation change through an Implementer, then deterministic verification, then done. User-requested real runtime verification still runs. The Controller owns routing, task state, promotion, integration decisions, and final acceptance only. Small bounded durable promotion is allowed only after the Controller decides an explicit semantic record is worth retaining and has current task evidence; it is never automatic summarization. Task-end order is task-local state -> Controller retention decision -> minimal durable promotion -> task-close; no durable knowledge means no durable write. Investigator findings and evidence refs are task-local structured handoffs; only explicit `task-promote` writes `.agent-memory/` or `.milestones/`. Repository tasks do not proactively read or write personal/global Codex memory (such as `~/.codex/memories` or `MEMORY.md`) unless the user explicitly requests it; project continuity uses `.agent-memory/`, `.milestones/`, `task-promote`, and tracked-document maintenance. For continuous feature work with a current milestone, retain material progress/verification there first; `.agent-memory/` is only for reusable decisions, constraints, invariants, or failure modes. Raw investigation/review history never enters the Reasoning Specialist. The Reasoning Specialist reasons only; it does not maintain task state. Use the Microtask fast path. Route memory and milestones through INDEX files. Use `context task-*` for concise, evidence-referenced handoffs—never transcripts or raw tool output. Large maintenance (history-heavy recall, deduplication, stale cleanup, conflict/merge judgment, INDEX restructuring, or bulk milestone maintenance) goes to a fresh child. Child state is UNKNOWN without explicit evidence: no result observed is not failure, and timeout/slow/incomplete observation is not capability limitation. RUNNING waits and re-observes; UNKNOWN stays UNKNOWN and is re-observed, never closed/replaced/taken over after one wait window. Only explicit FAILED/CANCELLED/UNAVAILABLE or deterministic spawn failure permits narrower fresh delegation, with capability fallback limited to genuinely unavailable native capability. These are managed Controller policy over Codex-native observations, not a Thaliris child runtime, scheduler, heartbeat, or state machine. Deterministic Thaliris enforcement is limited to its own fields, evidence/freshness, CAS, role projection, and capture filtering. Current source/Git/tests are the correctness core; adapters MUST fall back to native behavior.

Thaliris state and durable knowledge

Keep the three state layers distinct:

.context/state.json — transient task-local control, findings, evidence, and Decision Context.
.agent-memory/ — selectively retained project knowledge reusable across tasks.
.milestones/ — durable state for an ongoing bounded workstream.

None of them is a transcript, activity log, or automatic task summary.

Ownership
Investigator appends task-local findings and evidence.
Curator only compresses accumulated investigation into the bounded task-local snapshot; it does not maintain durable memory.
Implementer performs scoped source or tracked-document modifications.
Independent Reviewer records fresh review findings.
Reasoning Specialist reasons only and does not maintain state.
Controller owns routing, Decision Context, retention decisions, durable promotion, integration, and final acceptance.
Durable retention

Before closing substantial work, the Controller decides whether the task produced knowledge worth retaining.

Retain only durable information with clear future value, such as:

adopted decisions;
verified reusable invariants;
durable constraints;
reusable failure modes;
meaningful milestone progress;
milestone verification actually performed.

Do not retain raw findings, transcripts, tool output, debug history, temporary observations, speculative hypotheses, or routine task summaries.

If nothing is worth retaining, write nothing durable.

For normal incremental retention, use context task-promote. Only the Controller invokes it. Preserve evidence, confidence, applicability, audience, and routing semantics; never promote uncertainty into certainty.

task-promote is intentionally bounded:

project memory: new decision, invariant, failure_mode, or constraint records;
current milestone: explicit progress and/or verification.

It does not perform existing-entry rewrites, history cleanup, deduplication, conflict reconciliation, INDEX restructuring, or broad milestone maintenance.

Memory and milestone routing

Treat .agent-memory/INDEX.md and nested INDEX files as routing authority, not summaries. Do not bypass normal routing with broad directory scans, and do not treat initialized DRAFT/UNVERIFIED templates as project facts.

Milestone documents have distinct purposes:

scope.md — stable workstream boundary and outcome;
decisions.md — adopted milestone-specific decisions;
progress.md — meaningful current state, blockers, and next resumable step;
verification.md — checks and observations actually completed.

Update milestone progress only when work materially advances, blocks, redirects, or completes the milestone. Do not turn it into a per-action log.

Structural durable-document maintenance

When maintenance cannot be expressed by task-promote—for example stale cleanup, conflict reconciliation, existing-entry changes, INDEX restructuring, or milestone scope.md / decisions.md changes—use normal role isolation:

Controller defines the maintenance question
→ fresh Investigator gathers relevant history, routing, freshness, and native evidence
→ Reasoning Specialist only if difficult reconciliation or provenance reasoning is required
→ Controller defines the accepted result and Modification Boundary
→ Implementer performs the bounded tracked-document changes
→ deterministic validation
→ fresh Reviewer only for high-impact durable semantic changes.

Do not use the task-local Curator for durable-history maintenance, and do not let the persistent Controller perform history-heavy investigation or tracked-document editing.

Task completion

Before task-close on substantial work, the Controller should ensure:

requested behavior and verification criteria are satisfied;
relevant findings have been integrated or remain explicitly unresolved;
worthwhile durable knowledge has been selectively promoted;
the current milestone, when materially affected, has appropriate progress or verification recorded.

The goal is resumable, evidence-backed project knowledge with minimal durable noise.
<!-- thaliris:end -->
