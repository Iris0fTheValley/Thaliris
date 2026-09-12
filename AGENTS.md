<!-- thaliris:begin -->
## Thaliris Router

Codex remains the runtime. Thaliris stores bounded task control and pointers; it has no worker, scheduler, polling loop, or authority to decide correctness. Retain broadly, propagate explicitly, and select semantically: storage bounds are not a semantic payload quota.

Controller uses `context task-status` or `context prepare --role controller` for the default low-noise context base. `context task-show` is an explicit out-of-band diagnostic surface, not part of the normal ACTIVE managed Controller path. `context task-artifact` passes pointers, not contents.

During an active task the persistent root Controller is control-plane-only. Every new root child is a spawned execution child and must be fresh with `fork_turns="none"`; non-none values are denied and must be retried explicitly. This cuts implicit parent-task-history propagation; it does not mean an empty context. An allowed root spawn creates one authorization reservation; the next matching native `SubagentStart` receives its Thaliris role projection, and only a successfully emitted projection followed by the matching `SubagentStop` qualifies for acceptance or task-close. Large selected information remains valid when needed for correctness. Pending reservations and started managed children are serial in flight; PostToolUse records dispatch only. Known local PreToolUse surfaces used by managed mode are mechanically guarded; hosted, specialized, and unverified runtime surfaces remain outside this enforcement envelope. `NATIVE_CHILD_COMPLETION_REENTERS_ROOT` is a probe-bound Host capability: only `PASS` permits EVENT_DRIVEN mode. For `UNSUPPORTED` or `UNKNOWN`, use configured BLOCKING_WAIT mode: one host-bounded native wait per dependency, then after a timeout one status observation and another long wait only if the child is still running. A wait count alone is not failure, but short model-driven wait/list polling loops and timer wake-ups are prohibited. Codex owns execution; Thaliris does not recreate an agent runtime.

Read detailed role packs only when needed. Raw findings, evidence, transcripts,
logs, and tool output do not enter Controller packets or durable memory
automatically; explicitly select any detail needed for the next decision, and
promote only explicit durable decisions, constraints, invariants, failure modes,
or material milestone progress.

Investigators may keep a large private working set, but reusable findings must
be written to a bounded repo-relative Evidence Artifact before completion. The
completion message should contain only the artifact path, finding/evidence IDs,
a short outcome, and remaining decision-changing unknowns. The Controller must
register that pointer with the complete command `context task-artifact
--base-revision N --id ID --path repo/relative --summary TEXT
--producer-role investigator` and select relevant facts; artifact existence
never authorizes automatic full-text propagation. The command computes and
stores the artifact content identity from the registered file.

Every reusable artifact follows the evidence protocol: produce before the
dependent decision, register it through `context task-artifact` with its
producer role and content identity, select only the needed facts for the next
role, and record downstream consumption provenance. A changed artifact is
stale; a replacement must explicitly supersede it. Never silently continue
consuming stale or contradictory evidence. When no reusable cross-role
evidence exists, no Evidence Artifact is required and none should be
manufactured.

After targeted investigation, escalate to
`agent_type="thaliris-reasoning-specialist"` with `fork_turns="none"` only
when a material implementation choice remains unresolved by available
evidence: materially different fixes remain plausible, an OPEN unknown or
contradiction could change the choice, a cross-module state/lifecycle/
ownership/concurrency/compatibility choice remains undecided, a substantive
trade-off remains, or a Reviewer raises a design question. Do not escalate
only for task size, file count, or token count. Pass a selected Decision
Context, not the full investigation or an empty decision request.
After a Reasoning Specialist returns, do not dispatch an Implementer until
every accepted implementation-changing conclusion is recorded in task
semantic state or explicitly included in that Implementer handoff. Never rely
on implicit child history. A Reasoning Specialist makes one bounded decision
attempt: if evidence is insufficient, it returns an EvidenceRequest and stops;
the Controller sends that request to a fresh Investigator, persists a bounded
evidence artifact, then uses a fresh Reasoning Specialist. Reviewers are fresh
one-shot children for each review round; retain findings, not reviewer
conversation history. Use EVENT_DRIVEN mode only when the probe-bound native
continuation capability is `PASS`; otherwise use configured host-bounded
BLOCKING_WAIT mode. On timeout perform one status check and, if still running,
use another long wait. A wait count alone is not
 failure. Never use short model-driven wait/list polling loops or timer-driven
 wake-ups. Close completed one-shot Sol and Reviewer children with native Codex
controls. Thaliris does not implement scheduling, deadlines, or agent lifecycle.

Review convergence is packet-driven. A Reviewer returns the complete currently observable blocker set in one response and classifies each finding as
MECHANICAL, LOCAL_SEMANTIC, or ARCHITECTURAL and names the exact affected
surface, invariant, and verification requirement. MECHANICAL and LOCAL_SEMANTIC
findings receive one fresh Implementer with a bounded Correction Packet and one
fresh targeted Reviewer. They do not restart Investigator/Sol or a repository-
wide review. ARCHITECTURAL findings may reopen the larger route. A fresh
Reviewer is still mandatory after every source mutation; a READY verdict seals
the source and any later mutation invalidates that review. External Reviewer
failure remains INCOMPLETE and has bounded recovery; it is never converted to
success.
<!-- thaliris:end -->
## Thaliris Core

This repository contains the runtime-neutral Thaliris Core. Keep task state,
evidence, projections, artifacts, memory, milestones, and durable promotion
bounded and evidence-backed.

Working set is not handoff set. Retained information is not automatically
propagated. Use `context task-status` for bounded Controller routing and
`context task-show` only for explicit diagnostics. Artifact contents are
external to normal role packs.

Runtime-specific lifecycle and agent instructions belong in adapter branches,
not in this Core instruction file.
