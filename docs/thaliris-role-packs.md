# Thaliris Role Packs

Load this document when the compact managed router is insufficient for the task.

## Controller

The Controller routes work and accepts completion. It reads `context task-status`
for only task identity, active work, pending results, unresolved questions,
artifact pointers, and accepted constraints/decisions. It does not request raw
findings, review bodies, evidence records, Git status, or broad memory/milestone
bodies as part of normal routing. Use `context task-show` only for an explicit
diagnostic need.

Every active task starts with one fresh execution child using `fork_turns="none"`.
A positive fork is rewritten to `none`; an encrypted `Isolation reason:` never
creates an exception. The PreToolUse hook also guards root shell investigation,
source mutation, and task-close-before-child. PostToolUse keeps native dispatch
evidence auditable.

For a local, obvious microtask, that one fresh Implementer is still required,
followed by deterministic verification; the persistent Controller does not edit
source directly. Larger work adds only the roles needed by risk and unknowns.
Wait for native completion or mailbox updates; Thaliris has no polling, worker,
retry, or scheduling runtime.

## Evidence Roles

Investigators append bounded findings and evidence references. Curators receive a
current snapshot and uncovered suffix only, then may replace the compact snapshot.
Reasoning Specialists receive accepted Decision Context rather than raw
investigation or review history. Implementers receive the explicit Modification
Boundary, including out-of-scope exclusions and required verification. If bounded
findings contain an unresolved architecture, provenance, or cross-module decision,
route only that Decision Context to `sol-high` rather than investigating at root.
Reviewers receive intent, changed surface, constraints, and decisions;
their findings are independent evidence, not an automatic implementation loop.

Use focused checks while changing code and one complete relevant validation at the
end. Requested runtime or visible-behavior verification remains required.

## State And Retention

`active_work` and `pending_results` are short controller-visible labels. Use
`context task-artifact --base-revision N --id ID --path repo/relative --summary TEXT`
to append a path-safe pointer to external work. The artifact contents remain
outside the status packet. Raw task state remains diagnostic-only in
`.context/state.json`.

At task end, promote only reusable decisions, constraints, invariants, failure
modes, and material milestone progress or completed verification through
`context task-promote`. Route memory and milestones through their INDEX files;
do not treat this layer as a scheduler, transcript store, or automatic summary.
