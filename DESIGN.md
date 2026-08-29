# Design

## Boundary

`codex-context` is a deterministic file and routing layer around Codex. It does not execute agents, decide correctness, or replace the repository. The source tree, Git, compiler/type checker, tests, runtime, and freshly verified repo-owned memory are authoritative in that order.

The system has three deliberately small layers:

1. **Correctness core:** tracked Markdown, current source and Git, deterministic hashes, tests, and runtime evidence.
2. **Transient task state:** one ignored, revision-checked `.context/state.json` carrying structured claims and evidence references, never transcripts or raw exploration.
3. **Optimization layer:** Serena navigation, cachebro read deltas, agentmemory episodic recall, and role-specific projections.

Deleting every optimization cache or losing every adapter must leave a correct native workflow. The acceptable degradation is additional reads and tokens, never weaker validation.

## Decisions

### Git-owned Markdown over a database

Project memory and milestones are reviewable, diffable, portable, and available offline. Small INDEX files route reads to relevant entries. A database, graph store, and default vector retrieval would add operational state and could silently omit required facts.

### Evidence confidence is categorical

The four states are `CONFIRMED`, `SUPPORTED`, `UNVERIFIED`, and `STALE`. `STALE` is derived from changed evidence rather than written over historical confidence. The model stays simple and explainable; no pseudo-probability score is used.

### Role projections do not merge responsibilities

Sol high receives only controller-promoted Decision Context plus routed durable constraints and decisions. It has no task-state write permission: requests for more facts or verification return to the controller as reasoning output. A Luna investigator appends raw findings and evidence; a fresh Luna curator rewrites only the compact investigation snapshot. Terra implementers receive the explicit modification boundary and changed surface. Fresh reviewers receive only intent, hard constraints, durable decisions, changed surface/diff, and the evidence necessary to inspect them; they append isolated reviewer findings, which remain outside both their input pack and Sol high until the controller promotes one. Sol mid retains the complete routing view and is the only role that modifies Decision Context. Microtasks avoid delegation altogether.

### Investigation history and working state are separate

`investigation_findings` is raw structured history. Investigator updates are additions that the state layer appends; they cannot replace, delete, or rewrite earlier findings. `investigation_snapshot` is a replaceable working view for deduplication, merging, resolved-unknown removal, and evidence compression. Its `derived_from` indexes are stable because raw history is append-only; `supersedes` may name entries from the immediately previous snapshot, and evidence must come from the referenced raw findings.

The snapshot is limited to 64 entries and 32 KiB. Validation also prevents curation from raising epistemic status: `SUPPORTED` raw material cannot become `CONFIRMED`, and confirmed raw findings themselves require fresh native evidence when written. Curation is explicit and intended for phase boundaries, budget pressure, or preparation for high-reasoning work—not after every investigation update. The controller, not the curator, decides what is promoted to Decision Context. Raw findings and the snapshot are both excluded from Sol high.

### Claims remain evidence-addressable

Task state separates raw investigation findings, the curated investigation snapshot, append-only reviewer findings, and controller-promoted Decision Context. A confirmed claim needs fresh native file-hash or Git-blob evidence at mutation time and is rechecked when a pack is prepared. Weaker test, runtime, task-input, or memory evidence remains supported. Test/runtime freshness proves only that its explicitly named file/Git `source_refs` have not changed; it does not establish complete repository or worktree freshness, dependency coverage, or stability of unbound code. A changed bound source demotes the claim, while unbound source state remains explicitly unproven. Prohibited transcript and raw-log fields keep handoffs compact and auditable.

### Applicability is not authorization

Memory `Applicability`, `Topics`, and `Symbols` are routing hints. They may add relevant files or claims to read, but they can never enlarge `Modification Boundary`. The controller must set that boundary explicitly in task state.

### Routing is explicit and Unicode-safe

Memory declares a `Kind` and `Audience` and is filtered per role; legacy entries without an audience are not projected. Lexical routing normalizes Unicode and indexes ordinary words plus CJK characters and bigrams, along with explicit topics and symbols. Only an ACTIVE, trusted, fresh, audience-allowed, project-wide `HARD_CONSTRAINT` bypasses lexical matching. Ordinary decisions and lessons remain on-demand. The MVP intentionally has no embedding dependency. Milestone scope, decisions, and verification retain source, status, and confidence metadata in projections.

### External tools remain optional

- Serena is used for precise positive symbol/reference navigation. Dynamic-language negative results need evidence appropriate to the risk.
- cachebro owns unchanged-read caching and delta production; this project does not duplicate its cache.
- agentmemory is episodic and explicit-recall-only. Durable facts must be promoted into Git-owned memory and revalidated.

These integrations are an awareness and policy boundary, not runtime orchestration: `codex-context` does not call their MCP tools while producing packs. Diagnostics report only directly observable states and preserve `UNKNOWN` for authorization, running, health, and subagent claims that cannot be proved.

These choices borrow the useful ideas of structured project memory and source-linked invalidation without making `taichuy/agentMemory`, project-memory, PackMind, or Kage runtime dependencies. PackMind remains a future experiment only if real coding tasks demonstrate lower token use without lower downstream quality or weaker provenance. Kage's runtime is not used.

## Mutations and recovery

Initialization and uninstall acquire a non-blocking cross-process lock, write through same-directory temporary files, and use atomic replacement. Before mutation, the tool records prior bytes and expected written hashes in `.context/backups/`. Rollback refuses to overwrite a later user edit. Existing `AGENTS.md` and `.gitignore` content outside the managed markers is preserved.

Transient task updates use the same lock and atomic replacement plus compare-and-swap revision checks. The single state file is ignored, size-bounded, schema-validated, and marked `DONE` on close; it has no event database or separate history store. Append-only semantics for raw investigation and reviewer findings are enforced within the current task state, while the curated snapshot remains replaceable. A later `task-start` replaces the completed task state.

## Explicit non-goals

No agent framework, recursive scheduler, Web UI, server database, graph database, permission system, embeddings-first RAG, automatic project summary, or lossy hard context limit is part of the MVP.
