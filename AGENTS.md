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

### Controller orchestration economy

- `task-start` already returns a bounded packet; do not immediately repeat `task-status`.
- After a spawn, use one bounded native `wait_agent` observation; avoid polling loops and re-observe only when native state changes or recovery is needed.
- Do not call `list_agents` on the normal single-child path. Use it only for topology checks or recovery after an unexpected wait/result.
- Query `task-status` only after a known task mutation, a state/revision change, or recovery is required; do not repeat an unchanged revision.
- Use `send_message` only for a new constraint, correction, or material evidence. Do not use it to ask for progress or to say “continue”.

During an ACTIVE task, the persistent Controller NEVER performs repository investigation or source mutation before or after child dispatch. A successful child dispatch does not change those permissions. `task-close` requires a successful child dispatch. Every new root child uses `fork_turns="none"`; root shell investigation/mutation is mechanically guarded at PreToolUse; PostToolUse records dispatch evidence; bounded context commands and deterministic acceptance checks remain available. Codex owns execution; Thaliris has no worker, scheduler, polling loop, or lifecycle runtime.

Read detailed role packs only when needed. Keep raw findings, evidence, transcripts, logs, and tool output outside Controller packets and durable memory; promote only explicit durable decisions, constraints, invariants, failure modes, or material milestone progress.
<!-- thaliris:end -->
