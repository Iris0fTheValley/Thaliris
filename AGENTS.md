## Repository bootstrap

- Before substantial work in a Git repository, check whether the current repository has an initialized codex-context control layer.
- If codex-context is not initialized, run `context init` from the repository root before investigation, planning, delegation, or substantial edits, then verify it with `context doctor --pretty`.
- If an existing repository contains an older codex-context layout, run `context migrate` instead and handle any reported manual migration requirements before relying on routed memory or task state.
- After bootstrap, use the repository's managed `AGENTS.md`, task state, memory, and milestone routing normally.
- Do not run `git init` merely to satisfy this rule. If the workspace is not already a Git repository, initialize Git only when the user explicitly requests it or the task clearly establishes that the workspace is intended to become a repository.

<!-- codex-context:begin -->
## Codex context

Sol mid is Controller: only Controller delegates, promotes findings, and maintains task control state; children MUST NOT delegate (default concurrency: 1). Luna investigator appends raw findings; before high reasoning or when findings accumulate, a fresh Luna curator maintains the bounded snapshot. Terra implements and independently reviews. Raw investigation/review history never enters Sol high. Sol high reasons only; it does not maintain task state. Use the Microtask fast path. Route memory and milestones through INDEX files. Use `context task-*` for concise, evidence-referenced handoffs—never transcripts or raw tool/test output. Current source/Git/tests are the correctness core; adapters MUST fall back to native behavior.
<!-- codex-context:end -->
