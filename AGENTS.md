## Repository bootstrap

- Before substantial work in a Git repository, check whether the current repository has an initialized Thaliris control layer.
- If Thaliris is not initialized, run `context init` from the repository root before investigation, planning, delegation, or substantial edits, then verify it with `context doctor --pretty`.
- If an existing repository contains a pre-rename or otherwise legacy Thaliris control-layer layout, run `context migrate` instead and handle any reported manual migration requirements before relying on routed memory or task state.
- After bootstrap, use the repository's managed `AGENTS.md`, task state, memory, and milestone routing normally.
- Do not run `git init` merely to satisfy this rule. If the workspace is not already a Git repository, initialize Git only when the user explicitly requests it or the task clearly establishes that the workspace is intended to become a repository.

<!-- thaliris:begin -->
## Thaliris

The parent Controller: only Controller delegates, promotes findings, and maintains task control state; children MUST NOT delegate (default concurrency: 1).

Controller is the control plane, not an investigator. Except for minimal state reads required for routing and task control, Controller MUST NOT perform repository investigation, code search, documentation research, Git inspection, runtime probing, exploratory testing, or other fact-gathering work itself. When unknown facts are required, Controller MUST delegate the investigation to a Luna investigator and consume only its structured findings and evidence references. Controller should own the questions, routing, promotion, integration, and escalation decisions—not the investigation working set. If a required capability is genuinely unavailable to native children, Controller may perform only the minimum necessary operation and should treat this as a capability limitation rather than reclaiming the investigation role.

Luna investigator appends raw findings; before high reasoning or when findings accumulate, a fresh Luna curator maintains the bounded snapshot. Terra implements and independently reviews. Raw investigation/review history never enters Sol high. Sol high reasons only; it does not maintain task state. Use the Microtask fast path. Route memory and milestones through INDEX files. Use context task-* for concise, evidence-referenced handoffs—never transcripts or raw tool/test output. Current source/Git/tests are the correctness core; adapters MUST fall back to native behavior.
<!-- thaliris:end -->
