# codex-context

`codex-context` is a small, Git-native context and memory layer for Codex. It reduces repeated source reads, repeated investigation, repeated verification, and wasteful agent bootstrap without reducing necessary reasoning.

It is **not** an agent framework. Codex remains the runtime and controller. Current source, Git, compilers, tests, and runtime evidence remain the correctness core; optional tools may make work cheaper, but their failure must only make it slower or larger.

## What it provides

- A short managed router in an existing repository's `AGENTS.md`.
- Structured, evidence-backed Markdown in `.agent-memory/`.
- Scoped milestone state in `.milestones/`.
- Role-specific Task Context Packs for Sol high, Luna, Terra implementers, and isolated reviewers.
- `CONFIRMED`, `SUPPORTED`, `UNVERIFIED`, and dynamically derived `STALE` evidence states.
- SHA-256 file evidence and Git blob evidence with deterministic freshness checks.
- Environment diagnostics for Codex, Serena, cachebro, agentmemory, repository state, and native fallbacks.
- Idempotent initialization, conservative migration, hash-guarded rollback, and non-destructive uninstall.

## Install and attach to a repository

Python 3.11 or newer and Git are required.

```bash
uv tool install git+https://github.com/Iris0fTheValley/codex-context
cd existing-repository
context init
context doctor --pretty
```

For development:

```bash
git clone https://github.com/Iris0fTheValley/codex-context
cd codex-context
uv run --extra test pytest
uv run context version
```

`context init` requires the repository root. It preserves existing `AGENTS.md` content and owns only the marked `codex-context` block. Every mutation creates a local backup under `.context/backups/` and returns its backup ID.

## Core workflow

```bash
context prepare "fix request cancellation" --role luna --pretty
context prepare "choose the lifecycle design" --role sol-high --pretty
context prepare "implement the agreed change" --role terra-implementer --pretty
context prepare "review the final diff" --role terra-reviewer --pretty
context stale --pretty
context milestone-check --pretty
context memory-status --pretty
```

The four controller routes are:

| Route | When | Flow |
|---|---|---|
| Microtask | A local, obvious, low-risk change | Sol mid edits and runs the smallest deterministic check; no context pack or child agent. |
| Normal | The goal and approach are clear, but implementation is substantial | Terra implementer, deterministic checks, then Luna only if useful. |
| Investigation | Facts or locations are missing | Luna scouts once; Sol mid reuses those facts and routes to Terra or Sol high. |
| Complex | Lifecycle, state, concurrency, architecture, or semantic trade-offs | Focused Luna evidence, Sol high reasoning, Terra implementation, deterministic checks, Luna verification; add a fresh reviewer only for high risk. |

Default concurrency is one. Only the Sol mid controller spawns children, and context packs contain only the role's required fields.

## Memory, milestones, and task packs

`.agent-memory/INDEX.md` is a router, not a summary dump. It links stable operator constraints, prompt policy, project conventions, project decisions, and verified lessons. Each entry has strict front matter:

```markdown
---
Evidence: file:src/example.py#<sha256>
Revision: 1
Status: ACTIVE
Applicability: src/example.py
Confidence: CONFIRMED
---
```

`Evidence` also accepts `git:path#<blob-id>`. When the referenced bytes change, `context stale` reports an effective confidence of `STALE` without rewriting the historical entry. An unchanged hash proves that evidence did not change; it does not prove that an old interpretation was correct.

`.milestones/` keeps one directory per milestone with `scope.md`, `decisions.md`, `progress.md`, and `verification.md`. Progress is the latest state, not an append-only session log. `context milestone-check` verifies the routed structure.

A Task Context Pack is transient output. It never replaces source inspection and is not committed as project truth.

## Optional optimization adapters

The tested contract is graceful degradation:

| Component | Pinned baseline | Purpose | Native fallback |
|---|---:|---|---|
| [Serena](https://github.com/oraios/serena) | 1.7.0 | Symbol, declaration, reference, and impact navigation | `rg`, source inspection, compiler/tests |
| [cachebro](https://github.com/glommer/cachebro) | 0.2.2 | Cache unchanged reads and return deltas | Normal full-file reads |
| [agentmemory](https://github.com/rohitg00/agentmemory) | 0.9.29 | Explicit episodic recall and handoff | Repo memory, source, and Git |

Serena has an explicit Codex setup path (`serena setup codex`). cachebro is a standard stdio MCP server, but its upstream documentation does not currently claim a Codex-specific setup; treat Codex compatibility as provisional until `context doctor` and an actual read/delta call pass. agentmemory is manual-recall-only here: automatic context injection and automatic LLM compression are rejected by project configuration.

Add these MCP servers through normal Codex configuration, then enable the matching names in `.context/config.json` if desired. `context doctor` deliberately distinguishes `configured`, `enabled`, `authorized`, `running`, and `healthy`; it emits `UNKNOWN` when the current process cannot prove a state. Adapter output never upgrades a fact on its own.

## Delta reads and stale facts

Use cachebro for a file already read in a previous session; an unchanged hash permits reuse, while a changed hash should return a delta. If cachebro is absent or unhealthy, read the file normally. This project does not reimplement cachebro's database or replace Codex's native read tool.

Use Serena positives as strong navigation evidence. A zero-reference result is not proof of absence in dynamic Python/JavaScript, reflection, registries, or string-driven calls; escalate with lexical search, source inspection, type checking, or a targeted runtime test when risk warrants it.

agentmemory records are historical claims until current repository evidence verifies them. Promote durable decisions and lessons into `.agent-memory/`; do not inject an entire episodic history into every task.

## Migration, rollback, and uninstall

```bash
context migrate
context rollback <backup-id>
context uninstall
```

Rollback is hash-guarded: if a file changed after the recorded operation, it is retained and reported instead of overwritten. Uninstall removes the managed `AGENTS.md` block and unchanged generated templates only. Modified memory and milestone files are kept. Local backups remain available for recovery and may be deleted manually after review.

## Limits of the MVP

- No Web UI, scheduler, agent runtime, workflow engine, database, graph store, embeddings, or automatic whole-repository summary.
- Task routing is lexical and conservative; it may over-include rather than silently omit authoritative constraints.
- cachebro's Codex-specific compatibility is not established by upstream documentation.
- Codex Desktop currently exposes agentmemory MCP tools, while plugin-local lifecycle hooks may not dispatch; this project does not depend on those hooks.
- `doctor` reports inaccessible executable, authorization, process, and subagent states as `UNKNOWN` instead of guessing.

See [DESIGN.md](DESIGN.md) for the architectural decisions.
