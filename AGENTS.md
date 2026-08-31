## Repository bootstrap

- Before substantial work in a Git repository, check whether the current repository has an initialized Thaliris control layer.
- If Thaliris is not initialized, run `context init` from the repository root before investigation, planning, delegation, or substantial edits, then verify it with `context doctor --pretty`.
- If an existing repository contains a pre-rename or otherwise legacy Thaliris control-layer layout, run `context migrate` instead and handle any reported manual migration requirements before relying on routed memory or task state.
- After bootstrap, use the repository's managed `AGENTS.md`, task state, memory, and milestone routing normally.
- Do not run `git init` merely to satisfy this rule. If the workspace is not already a Git repository, initialize Git only when the user explicitly requests it or the task clearly establishes that the workspace is intended to become a repository.

<!-- thaliris:begin -->
## Thaliris Router

Codex remains the runtime. Thaliris stores bounded task control and pointers; it has no worker, scheduler, polling loop, or authority to decide correctness.

Controller owns delegation and final acceptance, but does not investigate or edit. Use `context prepare --role controller` for a bounded status packet and `context task-show` only for explicit raw diagnostics. Register external handoffs with `context task-artifact`; keep their contents outside controller packets.

For Investigator, Curator, Reasoning Specialist, Implementer, and Reviewer dispatches, start a fresh isolated child: `fork_turns="none"`. A positive small fork is allowed only with an `Isolation reason:` line in its message. Missing or `all` is a routing failure reported after native dispatch; Codex has already created that child and remains authoritative.

Use one fresh Implementer for an obvious local microtask, then deterministic verification. For larger work, load `docs/thaliris-role-packs.md`. Use native completion/mailbox observation; do not invent task polling or a lifecycle runtime.

Project continuity is `.agent-memory/` and `.milestones/` through their INDEX files. Promote only explicit durable decisions, constraints, invariants, failure modes, or material milestone progress/verification. Raw findings, reviews, transcripts, and tool output stay out of controller packets and durable memory.
<!-- thaliris:end -->
