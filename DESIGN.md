# Design

## Boundary

`codex-context` is a deterministic file and routing layer around Codex. It does not execute agents, decide correctness, or replace the repository. The source tree, Git, compiler/type checker, tests, runtime, and freshly verified repo-owned memory are authoritative in that order.

The system has two layers:

1. **Correctness core:** tracked Markdown, current source and Git, deterministic hashes, tests, and runtime evidence.
2. **Optimization layer:** Serena navigation, cachebro read deltas, agentmemory episodic recall, and role-specific projections.

Deleting every optimization cache or losing every adapter must leave a correct native workflow. The acceptable degradation is additional reads and tokens, never weaker validation.

## Decisions

### Git-owned Markdown over a database

Project memory and milestones are reviewable, diffable, portable, and available offline. Small INDEX files route reads to relevant entries. A database, graph store, and default vector retrieval would add operational state and could silently omit required facts.

### Evidence confidence is categorical

The four states are `CONFIRMED`, `SUPPORTED`, `UNVERIFIED`, and `STALE`. `STALE` is derived from changed evidence rather than written over historical confidence. The model stays simple and explainable; no pseudo-probability score is used.

### Role projections do not merge responsibilities

Sol high receives reasoning inputs, Luna receives investigation targets, Terra implementers receive a modification boundary, and fresh reviewers receive changed surface and known risks. Sol mid retains the complete routing view. Microtasks avoid delegation altogether.

### External tools remain optional

- Serena is used for precise positive symbol/reference navigation. Dynamic-language negative results need evidence appropriate to the risk.
- cachebro owns unchanged-read caching and delta production; this project does not duplicate its cache.
- agentmemory is episodic and explicit-recall-only. Durable facts must be promoted into Git-owned memory and revalidated.

These choices borrow the useful ideas of structured project memory and source-linked invalidation without making `taichuy/agentMemory`, project-memory, PackMind, or Kage runtime dependencies. PackMind remains a future experiment only if real coding tasks demonstrate lower token use without lower downstream quality or weaker provenance. Kage's runtime is not used.

## Mutations and recovery

Initialization and uninstall acquire a non-blocking cross-process lock, write through same-directory temporary files, and use atomic replacement. Before mutation, the tool records prior bytes and expected written hashes in `.context/backups/`. Rollback refuses to overwrite a later user edit. Existing `AGENTS.md` content outside the managed markers is preserved.

## Explicit non-goals

No agent framework, recursive scheduler, Web UI, server database, graph database, permission system, embeddings-first RAG, automatic project summary, or lossy hard context limit is part of the MVP.
