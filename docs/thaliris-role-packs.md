<!-- thaliris-role-packs:v2 -->
# Thaliris Role Packs

Load this document when the compact managed router is insufficient.

## Controller

The Controller routes work and accepts completion. It starts from the bounded
`context task-status` packet and selects the facts, constraints, decisions,
unknowns, contradictions, and artifact pointers needed for the current step.
Raw findings, review bodies, evidence records, Git status, and broad
memory/milestone bodies do not propagate automatically; use `context task-show`
only when a specific diagnostic detail is needed.

Every active task uses serial fresh execution children with `fork_turns="none"`.
This means no parent-thread history, not an empty Codex context: applicable
system/developer instructions, AGENTS, custom-agent instructions, environment,
native tool context, and delegation content may still be present. A non-none
fork is denied and must be retried explicitly. The child loads its own Thaliris
role projection directly, performs the assigned role, does not create
child-to-child workflow, and returns a bounded result to the persistent
Controller. The Controller must not consume child-only working material.
During an ACTIVE task the persistent Controller does not perform repository
investigation or source mutation; successful child dispatch does not change
those permissions. `task-close` requires a qualifying successful child
dispatch. PostToolUse keeps native dispatch evidence auditable.

For a local, obvious microtask, that one fresh Implementer is still required,
followed by deterministic verification; the persistent Controller does not edit
source directly. Larger work adds only the roles needed by risk and unknowns.
Wait for native completion or mailbox updates; Thaliris has no polling, worker,
retry, or scheduling runtime.

After a qualifying child dispatch, the Controller may run only the exact
Verification Target when it is a known test command family: pytest, npm/pnpm/
yarn test, cargo test, go test, or dotnet test. A target never authorizes an
arbitrary shell command.

Known local PreToolUse surfaces used by managed mode are mechanically guarded.
This is automatic projection isolation, not filesystem confidentiality or
universal tool enforcement: hosted, specialized, and unverified runtime
surfaces remain outside the claimed envelope. Hook configuration is separate
from current-session observation; current hook-definition evidence is required
before claiming a live observation.

## Evidence Roles

Investigators may keep a large private working set, but their handoff is bounded
and model-selected: surface facts, constraints, contradictions, compatibility or
lifecycle invariants, evidence summaries, unknowns, and artifact pointers that
could materially change the next decision. Do not dump the investigation process.
Curators receive only the bounded material selected for the current snapshot and
may replace that compact snapshot. Reasoning Specialists receive a bounded
Decision Context selected for the current unresolved decision, not raw history;
it may include relevant facts, competing hypotheses, contradictions, evidence
summaries, compatibility invariants, pointers, and unknowns. If it is insufficient,
state what evidence is needed so the Controller can request a targeted fresh
follow-up. Implementers receive the explicit Modification Boundary and required
verification. Reviewers receive bounded intent, changed surface, constraints,
decisions, and selected evidence, then independently decide what needs deeper
inspection. Role defaults guide work; they are not semantic firewalls.

Use focused checks while changing code and one complete relevant validation at the
end. Requested runtime or visible-behavior verification remains required.

## State And Retention

`active_work` and `pending_results` are short controller-visible labels. Use
`context task-artifact --base-revision N --id ID --path repo/relative --summary TEXT`
to append a path-safe pointer to external work. Only the Controller registers
the pointer; pass `--producer-role` to record which child produced it. Artifact
contents remain outside the status packet and are never automatically injected
into another role. Raw task state remains diagnostic-only in `.context/state.json`.

Artifact registration does not hide a path from review: Reviewer `Changed Surface`
continues to show Git-reported changes, without automatically exposing file contents.

At task end, promote only reusable decisions, constraints, invariants, failure
modes, and material milestone progress or completed verification through
`context task-promote`. Route memory and milestones through their INDEX files;
do not treat this layer as a scheduler, transcript store, or automatic summary.
