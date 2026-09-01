## Repository bootstrap

- Before substantial work in a Git repository, check whether the current repository has an initialized Thaliris control layer.
- If Thaliris is not initialized, run `context init` from the repository root before investigation, planning, delegation, or substantial edits, then verify it with `context doctor --pretty`.
- If an existing repository contains a pre-rename or otherwise legacy Thaliris control-layer layout, run `context migrate` instead and handle any reported manual migration requirements before relying on routed memory or task state.
- After bootstrap, use the repository's managed `AGENTS.md`, task state, memory, and milestone routing normally.
- Do not run `git init` merely to satisfy this rule. If the workspace is not already a Git repository, initialize Git only when the user explicitly requests it or the task clearly establishes that the workspace is intended to become a repository.

<!-- thaliris:begin -->
## Thaliris Router

Codex remains the runtime. Thaliris stores bounded task control and pointers; it has no worker, scheduler, polling loop, or authority to decide correctness.

Controller uses `context task-status` or `context prepare --role controller` for bounded packets. `context task-show` is explicit raw diagnostics; `context task-artifact` passes pointers, not contents.

Every new root `spawn_agent` is fresh with `fork_turns="none"`; only `"1"` or `"2"` with an explicit `Isolation reason:` is allowed, and `all` is never a compatibility fallback. PreToolUse enforces this before dispatch; PostToolUse verifies the native result. Codex owns execution; Thaliris has no worker, scheduler, polling loop, or lifecycle runtime.

Read detailed role packs only when needed. Keep raw findings, evidence, transcripts, logs, and tool output outside Controller packets and durable memory; promote only explicit durable decisions, constraints, invariants, failure modes, or material milestone progress.
<!-- thaliris:end -->
