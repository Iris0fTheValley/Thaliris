# Design

## Boundary

Thaliris is a deterministic file and routing layer around Codex. It does not execute agents, decide correctness, or replace the repository. The source tree, Git, compiler/type checker, tests, runtime, and freshly verified repo-owned memory are authoritative in that order.

The system has three deliberately small layers:

1. **Correctness core:** tracked Markdown, current source and Git, deterministic hashes, tests, and runtime evidence.
2. **Transient task state:** one ignored, revision-checked `.context/state.json` carrying structured claims and evidence references, never transcripts or raw exploration.
3. **Optimization layer:** Serena navigation, cachebro read deltas, agentmemory episodic recall, and role-specific projections.

An independent, optional **Intent Audit / Capture Plane** sits beside these layers. It is not part of the correctness core or control plane: ignored `.context/audit/` files contain only root prompts and actual delegation instructions needed to compare framing. They never enter task state, memory, milestones, or role projections.

Deleting every optimization cache or losing every adapter must leave a correct native workflow. The acceptable degradation is additional reads and tokens, never weaker validation.

## Compact router and isolation

The former generated router repeated detailed role and lifecycle policy in every
Controller context. That made a file-level instruction block an avoidable token
cost, and it did not make Codex's native `spawn_agent` default of
`fork_turns="all"` visible at the routing boundary. The managed block is now a
small router in `core.py:MANAGED`; the detailed policy is on demand in
`docs/thaliris-role-packs.md`.

The capture adapter in `intent_audit.py:_capture_delegation` classifies completed
`spawn_agent` calls for isolation-required roles. `fork_turns="none"` is PASS;
missing, `all`, and positive one/two-turn forks are FAIL. PreToolUse rewrites
every non-`none` fork before dispatch and no longer treats an encrypted reason as
an exception. Codex remains the runtime and native completion/mailbox mechanisms
remain the only lifecycle mechanisms.

The same PreToolUse surface exposes Codex 0.146 root shell execution as
`Bash`. The adapter mechanically denies only recognized root broad investigation,
source mutation, and `task-close` without a successful child dispatch. The
persistent Controller never investigates or mutates source before or after
dispatch; successful child dispatch does not change those permissions. Bounded
`context` commands and deterministic acceptance checks remain allowed. Unknown
scripts, non-shell tools, and child events that do not expose the documented root
topology remain fail-open/`UNKNOWN`; the adapter does not claim a universal
permission system.

`core.py:_controller_packet` emits the normal Controller control plane: task
identity/status, active work, pending results, unresolved questions, external
artifact pointers, accepted constraints/decisions, and the bounded Modification
Boundary. It does not calculate or return raw investigation/review material,
evidence records, Git status, or memory/milestone bodies. Raw state is
diagnostic-only through `task-show`. `task-artifact` appends a bounded normalized
repo-relative pointer; its contents are external to the packet. The Controller
registers the pointer and may record the producing child separately; artifacts
are not automatically projected to later roles. `task-start`
returns this bounded packet once so a Controller can dispatch without an
extra status round trip.

Reviewer `Changed Surface` remains Git truth even when a changed path is also
registered as an artifact; registration isolates contents, not repository
state visibility.

`doctor.py:report` reports routing readiness independently from command success.
The A/B fixture and reporter (`tests/fixtures/workflow_ab.json` and
`tools/workflow_ab.py`) specify the comparison protocol but report native
measurements as `UNAVAILABLE` until a real native run is deliberately supplied.

## Decisions

### Git-owned Markdown over a database

Project memory and milestones are reviewable, diffable, portable, and available offline. Small INDEX files route reads to relevant entries. A database, graph store, and default vector retrieval would add operational state and could silently omit required facts.

### Evidence confidence is categorical

The four states are `CONFIRMED`, `SUPPORTED`, `UNVERIFIED`, and `STALE`. `STALE` is derived from changed evidence rather than written over historical confidence. The model stays simple and explainable; no pseudo-probability score is used.

### Role projections do not merge responsibilities

Roles name responsibilities; current recommendations are Controller/Control Plane, Investigator, and Curator -> GPT-5.6 Luna; Reasoning Specialist -> GPT-5.6 Sol; Implementer and Independent Reviewer -> GPT-5.6 Terra. Investigator, Curator, Reasoning Specialist, and Independent Reviewer are conditional roles, not a fixed pipeline. Bounded, structured findings from one Investigator without evident duplication, conflict, or staleness go directly to Controller; a fresh Curator rewrites only the compact task-local investigation snapshot when findings are oversized, repetitive, conflicting, stale, or high reasoning genuinely needs working-set compression. The Reasoning Specialist receives only controller-promoted Decision Context plus routed durable constraints and decisions. It has no task-state write permission: requests for more facts or verification return to the Controller as reasoning output. An Implementer receives the explicit modification boundary and changed surface. An Independent Reviewer receives only intent, hard constraints, durable decisions, changed surface/diff, and the evidence necessary to inspect them; reviewer findings remain outside both its input pack and the Reasoning Specialist until the Controller promotes one. Fresh independent review remains appropriate for high-risk changes. Findings are independent evidence, not an automatic repair loop: P0/P1 or a finding directly violating requested completion criteria must be resolved, while the Controller returns P2/lower findings for implementation only when they materially affect correctness, requested behavior, regression safety, or the accepted Modification Boundary. The persistent Controller retains the complete routing view and is the only role that modifies Decision Context. A microtask still follows Controller -> Implementer -> deterministic verification -> done; it does not authorize Controller direct source edits. User-requested real runtime verification is not downgraded to static checks.

### Verification is proportional, not mechanical

Verification is layered by changed surface, risk, and fresh evidence: targeted checks during development, related regression after related fixes are combined, and one complete relevant validation at the end. Documentation-only changes, low-risk P2 fixes, and merges/conflicts that do not change already-verified behavior do not automatically repeat expensive checks. This does not relax completion criteria or replace user-requested real runtime or visible-behavior verification with static tests.

### Investigation history and working state are separate

`investigation_findings` and `review_findings` are immutable-prefix raw history for every role, including Controller. Updates contain additions; the state layer appends them, so no role can replace, delete, reorder, or rewrite existing provenance during a task. `investigation_snapshot` is a replaceable working view for deduplication, merging, resolved-unknown removal, and evidence compression. Its `derived_from` indexes are stable because raw history is append-only; `supersedes` may name entries from the immediately previous snapshot, and evidence must come from the referenced raw findings. `investigation_covered_through` is an exclusive raw prefix cursor: it says the snapshot has processed findings before that position. `review_handled_through` is the Controller's equivalent review cursor.

The snapshot is limited to 64 entries and 32 KiB. Validation prevents curation from raising or laundering epistemic status: `SUPPORTED` raw material cannot become `CONFIRMED`, and a source mix containing `UNKNOWN` or `CONTRADICTION` cannot collapse into an ordinary `SUPPORTED` conclusion. Confirmed raw findings themselves require fresh native evidence when written. Curation is explicit and intended for phase boundaries, budget pressure, or preparation for high-reasoning work—not after every investigation update. Curator input is current effective snapshot plus the uncovered raw suffix; it does not receive the full historical prefix. The Controller, not the Curator, decides what is promoted to Decision Context. Raw findings, the snapshot, and reviewer findings are all excluded from the Reasoning Specialist; it sees pending/readiness metadata only.

### Claims remain evidence-addressable

Task state separates raw investigation findings, the curated investigation snapshot, append-only reviewer findings, and controller-promoted Decision Context. A confirmed claim needs fresh native file-hash or Git-blob evidence at mutation time and is rechecked when a pack is prepared. Weaker test, runtime, task-input, or memory evidence remains supported. Test/runtime freshness proves only that its explicitly named file/Git `source_refs` have not changed; it does not establish complete repository or worktree freshness, dependency coverage, or stability of unbound code. A changed bound source demotes the claim, while unbound source state remains explicitly unproven. Prohibited transcript and raw-log fields keep handoffs compact and auditable.

### Bounded Controller promotion

Task end is deliberately ordered: task-local state, Controller retention decision, minimal durable promotion, then task-close. `task-promote` is Controller-only and deterministic: it accepts only explicit semantic records (`decision`, `invariant`, `failure_mode`, `constraint`) and explicit current-milestone progress or verification. For continuous feature work with a current milestone, material progress and verification belong there first; `.agent-memory/` is limited to reusable cross-task decisions, constraints, invariants, and failure modes. Unless the user explicitly requests it, repository work does not proactively read or write personal/global Codex memory such as `~/.codex/memories` or `MEMORY.md`; project continuity uses Git-owned `.agent-memory/`, `.milestones/`, `task-promote`, and tracked-document maintenance. It does not summarize, read broad history, deduplicate, clean stale entries, merge records, or restructure INDEX files. Every record is bounded, single-line, and references only the current ACTIVE task's fresh native file/git evidence or fresh test/runtime evidence whose native `source_refs` are fresh; CONFIRMED promotion additionally requires a directly referenced fresh CONFIRMED file/git evidence ref. Memory entries are new ACTIVE records with native locator Evidence and one appended INDEX link; existing targets are never overwritten. Milestone files preserve their contract and increment their own metadata Revision. A task-local counter allows at most 16 promotion units total (one per memory record and per milestone progress/verification field); it is bounded bookkeeping only, not durable memory, a scheduler, or a framework. The operation checks the supplied task base revision under the existing lock, uses CAS against concurrent task updates, atomically backs up the counter with the durable writes, and intentionally leaves task revision unchanged. No evidence means no promotion and no durable write.

### Child lifecycle epistemic/control policy

Child observation is epistemically conservative: no result observed yet is not failure, and timeout, slowness, or incomplete observation is not capability limitation. An unsupported child state remains `UNKNOWN`; `RUNNING` is wait/re-observe and `UNKNOWN` is keep-unknown/re-observe. One elapsed wait window cannot justify close, replacement, or takeover. Explicit `FAILED`, `CANCELLED`, `UNAVAILABLE`, or deterministic spawn failure permits only a narrower fresh delegation. Objective capability unavailability permits the smallest capability fallback, never Controller investigation or implementation. After failure, narrowing and fresh delegation take priority. This is managed Controller policy over Codex-native observations; it is not a Thaliris child runtime, scheduler, heartbeat, retry state machine, or agent framework. Deterministic Thaliris enforcement is limited to its own structured fields, evidence/freshness, CAS, role projection, and capture filtering.

### Applicability is not authorization

Memory `Applicability`, `Topics`, and `Symbols` are routing hints. They may add relevant files or claims to read, but they can never enlarge `Modification Boundary`. The controller must set that boundary explicitly in task state.

### Routing is explicit and Unicode-safe

Memory declares a `Kind` and `Audience` and is filtered per role; legacy entries without an audience are not projected. The root memory INDEX is routing authority. Normal routing recursively follows only valid linked INDEX files with path, cycle, depth, and count guards; an empty, damaged, missing, invalid, or escaping link fails closed and produces an explicit unknown rather than broadening recall by directory scan. INDEX nodes are navigation-only, not projected memory. Lexical routing normalizes Unicode and indexes ordinary words plus CJK characters and bigrams, along with explicit topics and symbols. Only an ACTIVE, trusted, fresh, audience-allowed, project-wide `HARD_CONSTRAINT` bypasses lexical matching. Ordinary decisions and lessons remain on-demand. The MVP intentionally has no embedding dependency. Milestone scope, decisions, and verification retain source, status, and confidence metadata in their relevant projections; milestone Progress is projected only to the Controller.

### External tools remain optional

- Serena is used for precise positive symbol/reference navigation. Dynamic-language negative results need evidence appropriate to the risk.
- cachebro owns unchanged-read caching and delta production; this project does not duplicate its cache.
- agentmemory is episodic and explicit-recall-only. Durable facts must be promoted into Git-owned memory and revalidated.

These integrations are an awareness and policy boundary, not runtime orchestration: Thaliris does not call their MCP tools while producing packs. Diagnostics report only directly observable states and preserve `UNKNOWN` for authorization, running, health, and subagent claims that cannot be proved.

These choices borrow the useful ideas of structured project memory and source-linked invalidation without making `taichuy/agentMemory`, project-memory, PackMind, or Kage runtime dependencies. PackMind remains a future experiment only if real coding tasks demonstrate lower token use without lower downstream quality or weaker provenance. Kage's runtime is not used.

### Intent audit is a fail-open runtime adapter

Initialization conservatively merges exact Thaliris command handlers into `.codex/hooks.json`, preserving user hook order and unknown fields; unsafe or malformed configurations are reported for manual handling rather than overwritten. The thin adapter uses `UserPromptSubmit` to create an unbound root capture with a short-lived one-time opaque capability, then `task-start --intent-capture-id` binds that capture to the task; binding failure only makes coverage `UNKNOWN` and never blocks normal task execution. Filtered `PostToolUse` events capture real native delegation instruction text from `spawn_agent`, `Agent`, `followup_task`, `send_input`, and `send_message`, including namespaced forms; root `Stop` runs a one-shot tail audit. `intent.json` is an append-only raw intent anchor; per-partition `capture.json` files contain only actual delegations and audit cursors. Child events carrying `agent_id` are ignored. No transcript path, tool log, worker output, repository data, test output, or Controller reasoning is captured.

A low-frequency fresh, ephemeral Luna auditor with `reasoning=high` receives only a fixed drift rubric, the necessary raw intent anchor, and the delegation suffix since the partition's exclusive `audit.through` cursor. It runs in an isolated execution context; this is not a model-level independence claim. Strings are recorded as `AVAILABLE_UNVERIFIED`, while non-string or unavailable values remain `UNKNOWN`. Minimal tool-response flags classify dispatch as `ACCEPTED`, `REJECTED`, or `UNKNOWN`; rejected calls do not enter a batch, response bodies are never stored, and an unknown dispatch prevents `PASS`. Five new delegations form a checkpoint, where all drift categories including requirement omission may be reported. Every attempt advances the cursor before model execution, so `PASS`, `UNKNOWN`, and `DRIFT` history is not resent. Stop audits only a non-empty suffix, persists its one-shot guard first, and closes a missing-turn partition. Missing `turn_id` values receive deterministic monotonic `unknown-turn-N` partitions after a prompt or `orphan-N` partitions otherwise, preventing a permanent shared final guard. Before emitting a blocking drift, the adapter stores a one-shot hash so the generated continuation prompt is ignored rather than captured as user intent. `PASS` and `UNKNOWN` produce no hook output; `DRIFT` alone emits a bounded finding. Recursion is suppressed by `THALIRIS_INTENT_AUDIT_ACTIVE=1`.

Each turn retains a bounded append-only view of up to 32 normalized audit results: mode, attempt number, categorical status, at most four short findings, fresh-verification state, and a short failure category. It never retains runner stdout, logs, error bodies, or tool-response content, and this trace is not part of any normal projection.

The adapter trusts the Codex hook contract exposed by the official `/hooks` runtime boundary. Production starts a fresh `codex exec --ephemeral --ignore-user-config --ignore-rules --model gpt-5.6-luna` process with `reasoning=high` from a temporary non-repository directory, with `--sandbox read-only`, `--skip-git-repo-check`, fixed developer instructions/schema, and multi-agent, plugins, and memories disabled. `THALIRIS_CODEX_EXECUTABLE` may select only a validated local executable and is never repository configuration; otherwise runner resolution falls back to `PATH`. Existing v1 captures are read conservatively by mapping `checkpoint_through` to `through`; without a v2 session anchor their intent coverage remains `UNKNOWN`. Hook configuration, observed execution, root classification, payload fidelity, runner availability, and fresh execution are separate diagnostic claims. The current live probe confirms configured hooks and an unusable PATH runner only: `payload_fidelity`, `root_classification`, `runtime_observed`, and overall status are `UNKNOWN`; `runner_available` is `NO`; and `runner_resolution` is `PATH_UNUSABLE`, not HEALTHY. Encrypted/non-string fields and execution paths not validated by a live runtime probe remain `UNKNOWN`; mere string capture never upgrades payload fidelity, and test fakes cannot prove native-session freshness. Storage, runner, schema, and configuration failures exit successfully with no output, so deleting the capture plane can remove only supplemental protection, never native correctness.

## Mutations and recovery

Initialization and uninstall acquire a non-blocking cross-process lock, write through same-directory temporary files, and use atomic replacement. Before mutation, the tool records prior bytes and expected written hashes in `.context/backups/`. Rollback refuses to overwrite a later user edit. Existing `AGENTS.md` and `.gitignore` content outside the managed markers is preserved.

The same conservative ownership applies to `.codex/hooks.json`: init/migrate append missing exact handlers, repeated runs are idempotent, and uninstall removes only those handlers. Malformed or structurally unsafe hook files are left byte-for-byte unchanged and reported for manual migration.

Transient task updates use the same lock and atomic replacement plus compare-and-swap revision checks. The single state file is ignored, size-bounded, schema-validated, and marked `DONE` on close; it has no event database or separate history store. Append-only semantics for raw investigation and reviewer findings, and additions-only immutable evidence identity, are enforced within the current task state; only bounded working snapshot/cursors and Controller Decision Context are replaceable. Projection computes effective stale/unknown state for raw and snapshot material without rewriting historical records. A later `task-start` replaces the completed task state.

## Explicit non-goals

No agent framework, recursive scheduler, Web UI, server database, graph database, permission system, embeddings-first RAG, automatic project summary, or lossy hard context limit is part of the MVP.
