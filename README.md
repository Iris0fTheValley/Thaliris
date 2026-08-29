# codex-context

`codex-context` is a small, Git-native context and memory layer for Codex. It reduces repeated source reads, repeated investigation, repeated verification, and wasteful agent bootstrap without reducing necessary reasoning.

It is **not** an agent framework. Codex remains the runtime and controller. Current source, Git, compilers, tests, and runtime evidence remain the correctness core; optional tools may make work cheaper, but their failure must only make it slower or larger.

## What it provides

- A short managed router in an existing repository's `AGENTS.md`.
- Structured, evidence-backed Markdown in `.agent-memory/`.
- Scoped milestone state in `.milestones/`.
- A single ignored transient task snapshot in `.context/state.json` for compact, evidence-addressable handoffs.
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
context task-start "fix request cancellation" --milestone M001-name
context task-update --role controller --base-revision 1 --input update.json
context prepare --role luna-investigator --pretty
context prepare --role luna-curator --pretty
context prepare --role sol-high --pretty
context prepare --role terra-implementer --pretty
context prepare --role terra-reviewer --pretty
context task-show --pretty
context task-close --base-revision 2
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
Kind: MEMORY
Audience: ["sol-high", "terra-implementer"]
Topics: ["request cancellation"]
Symbols: ["Request.cancel"]
---
```

`Evidence` also accepts `git:path#<blob-id>`. When the referenced bytes change, `context stale` reports an effective confidence of `STALE` without rewriting the historical entry. An unchanged hash proves that evidence did not change; it does not prove that an old interpretation was correct.

`.milestones/` keeps one directory per milestone with `scope.md`, `decisions.md`, `progress.md`, and `verification.md`. Progress is the latest state, not an append-only session log. `context milestone-check` verifies the routed structure.

A Task Context Pack is transient output. It never replaces source inspection and is not committed as project truth.

`task-start`, `task-update`, and `task-close` maintain one current task in the ignored `.context/state.json`. Updates use an expected revision so two roles cannot silently overwrite each other. The state rejects transcript, raw-log, stdout, and stderr fields: a handoff carries claims and addressable evidence, not exploratory history.

Investigation has two layers. A Luna investigator (`luna` remains a compatibility alias) appends raw `investigation_findings` (`kind`, `text`, and evidence refs); an update supplies additions, never a replacement. A fresh `luna-curator` invocation may fully rewrite `investigation_snapshot` at a phase boundary, before high-reasoning work, or when the snapshot budget is reached. Each snapshot item has an `id`, `kind`, compact `text`, raw list indexes in `derived_from`, optional prior snapshot IDs in `supersedes`, and evidence refs inherited from those raw findings. The snapshot is deterministically limited to 64 items and 32 KiB. Curation may deduplicate, merge, remove resolved unknowns, and compress evidence, but cannot promote epistemic status—for example, a merely `SUPPORTED` source cannot become `CONFIRMED` through summarization.

A fresh reviewer appends only `review_findings` (`issue`, `impact`, and evidence refs); earlier reviewer findings are never rewritten. The curator cannot modify raw findings, evidence, verification targets, or Sol-facing fields. Sol high has no task-state write permission: it returns reasoning to the controller instead of maintaining evidence or verification state. Only the controller selects and promotes material from the curated snapshot or reviewer output into the Decision Context: confirmed facts, supported evidence, unknowns, contradictions, hard constraints, decisions, verification target, and architectural intent. Neither raw findings, the curated snapshot, nor reviewer findings are projected into Sol high.

`Confirmed Facts` require currently fresh file-hash or Git-blob evidence. `Supported Evidence` remains explicitly weaker and may cite tests, runtime observations, task input, or memory. Test and runtime references must declare non-empty `source_refs` to fresh file/Git evidence; when a bound source changes, preparation demotes the affected supported claim until it is reverified. This freshness proves only that the explicitly bound `source_refs` have not changed. It does not prove that every file capable of affecting the test or runtime observation is unchanged, and unbound source is outside the freshness proof. Memory `Applicability` helps route relevant files only; it never expands the task's `Modification Boundary`.

Each memory entry also declares `Kind`, `Audience`, `Topics`, and `Symbols`; entries without `Audience` remain readable for migration and stale checks but are not projected to any role. Ordinary `MEMORY` entries use Unicode-safe lexical routing. A `HARD_CONSTRAINT` bypasses lexical matching only when it is project-wide, ACTIVE, audience-allowed, backed by fresh evidence, and captured as CONFIRMED or SUPPORTED. There is no embedding index. Milestone scope, decisions, and verification are projected with source, status, and confidence metadata. A fresh reviewer receives only intent, hard constraints, durable decisions, the actual changed surface/diff, and evidence necessary for those fields, not earlier findings, implementation explanations, known-risk framing, or a scoring rubric.

Passing a task string to `context prepare` remains a stateless compatibility path. Omitting it prepares the current task snapshot.

## Optional optimization adapters

The tested contract is graceful degradation:

| Component | Pinned baseline | Purpose | Native fallback |
|---|---:|---|---|
| [Serena](https://github.com/oraios/serena) | 1.7.0 | Symbol, declaration, reference, and impact navigation | `rg`, source inspection, compiler/tests |
| [cachebro](https://github.com/glommer/cachebro) | 0.2.2 | Cache unchanged reads and return deltas | Normal full-file reads |
| [agentmemory](https://github.com/rohitg00/agentmemory) | 0.9.29 | Explicit episodic recall and handoff | Repo memory, source, and Git |

Serena has an explicit Codex setup path (`serena setup codex`). cachebro is a standard stdio MCP server, but its upstream documentation does not currently claim a Codex-specific setup; treat Codex compatibility as provisional until `context doctor` and an actual read/delta call pass. agentmemory is manual-recall-only here: automatic context injection and automatic LLM compression are rejected by project configuration.

Add these MCP servers through normal Codex configuration, then enable the matching names in `.context/config.json` if desired. `codex-context` describes policy and awareness for these tools; it does not invoke MCP servers to assemble a context pack or orchestrate their lifecycle. `context doctor` reports executable installation independently from the observed version and whether that version matches the tested baseline. Probes disabled or unavailable remain `UNKNOWN`; version mismatch is not reported as uninstalled. Adapter output never upgrades a fact on its own.

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

Rollback is hash-guarded: if a file changed after the recorded operation, it is retained and reported instead of overwritten. Initialization adds a marked `.gitignore` block only when the transient state, lock, and backup paths are not already ignored. Uninstall removes the managed `AGENTS.md` and `.gitignore` blocks and unchanged generated templates only. Modified memory and milestone files are kept. Local backups remain available for recovery and may be deleted manually after review.

## Limits of the MVP

- No Web UI, scheduler, agent runtime, workflow engine, database, graph store, embeddings, or automatic whole-repository summary.
- Ordinary task routing is lexical and conservative; explicitly classified, fresh project-wide hard constraints are routed independently of lexical hits.
- The MVP stores one current transient task snapshot; it is not a task database, event log, or transcript store.
- Raw findings remain bounded by the existing 256 KiB task-state cap and global list limits; the tool does not provide unlimited investigation history.
- cachebro's Codex-specific compatibility is not established by upstream documentation.
- Codex Desktop currently exposes agentmemory MCP tools, while plugin-local lifecycle hooks may not dispatch; this project does not depend on those hooks.
- `doctor` leaves authorization, runtime health, and subagent state `UNKNOWN` when they are not directly observable.

See [DESIGN.md](DESIGN.md) for the architectural decisions.
