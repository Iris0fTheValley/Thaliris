# codex-context

A lightweight, Git-native context and orchestration layer for Codex.

`codex-context` helps multi-agent coding workflows keep the right information in the right reasoning context without turning the repository into an agent framework.

It provides:

* role-specific context packs;
* evidence-backed project memory;
* transient task state;
* investigation and review handoffs;
* freshness tracking;
* milestone state;
* conservative routing;
* deterministic validation and recovery.

Codex remains the runtime and controller. Source code, Git, tests, compilers, and runtime behavior remain the correctness core.

> **Status:** Alpha. The current implementation is intentionally small and is still being evaluated on real coding workloads.

---

## Why this project exists

Long coding tasks tend to accumulate context.

A single agent may eventually carry:

* repository exploration;
* failed search paths;
* implementation details;
* test output;
* debugging traces;
* architectural reasoning;
* reviewer criteria;
* old decisions;
* unrelated historical context.

More context is not automatically better context.

For strong reasoning models, the larger risk is often not the raw number of tokens but the number of competing objectives inside the same reasoning trajectory.

An agent asked to simultaneously:

* investigate,
* design,
* implement,
* verify,
* review its own design,
* remember previous failures,
* and satisfy a large procedural checklist

is solving a different problem from an agent given a focused reasoning question with the necessary evidence.

`codex-context` is built around a simple idea:

> **Preserve useful information without forcing every role to carry every piece of information.**

The project therefore treats context boundaries as part of the engineering architecture.

---

## Design philosophy

### One dominant objective per reasoning context

Strong models already contain substantial learned engineering knowledge.

The goal is not to tell them every reasoning procedure they should execute. The goal is to give them:

* the problem;
* confirmed facts;
* relevant evidence;
* hard constraints;
* unresolved questions.

Then let the model reason.

The system tries to avoid explicitly combining unrelated cognitive roles inside the same context.

For example:

```text
investigate → summarize evidence → reason → implement → verify
```

is preferred over:

```text
one agent investigates
        + designs
        + implements
        + judges its own design
        + verifies everything
        + rereads all previous logs
```

---

### Weak models need procedure; strong models need evidence

Different capabilities benefit from different amounts of scaffolding.

A useful approximation is:

```text
weaker model
    → WHAT + HOW + CHECKLIST

mid-level model
    → WHAT + BOUNDARY + SOME HOW

strong reasoning model
    → WHAT + FACTS + HARD CONSTRAINTS
```

`codex-context` therefore does not try to give every agent the same prompt.

Investigation and mechanical verification can use explicit schemas and procedures.

High-reasoning roles receive a much smaller evidence-oriented context.

---

### Working set is not handoff set

An investigator may need to inspect hundreds of files, searches, symbols, and intermediate hypotheses.

That does not mean the next agent should receive all of them.

The intended flow is:

```text
large investigation working set
            ↓
structured raw findings
            ↓
bounded curated snapshot
            ↓
Controller selection
            ↓
small Decision Context
            ↓
high-reasoning agent
```

Raw exploration remains available for traceability, but it does not automatically gain the right to enter every downstream context.

---

### Evidence over memory

Project memory is useful, but memory is not truth.

The effective precedence is:

```text
current source / Git / tests / runtime
                ↓
fresh verified project memory
                ↓
milestone state
                ↓
historical memory
```

A stored interpretation can become stale when its supporting evidence changes.

An unchanged hash proves that the referenced evidence did not change. It does **not** prove that the previous interpretation was correct.

---

### Optimization must not become a correctness dependency

Optional tools may reduce repeated reads or accelerate navigation.

They must never be required for correctness.

If Serena, cachebro, agentmemory, or another optimization layer fails, the workflow should become slower—not less correct.

---

## Architecture

The default roles are intentionally narrow.

### Controller — Sol mid

The parent Controller owns:

* task routing;
* task state;
* context promotion;
* phase transitions;
* integration;
* final acceptance.

Only the Controller delegates work.

The Controller should operate on bounded task views rather than raw investigation transcripts.

---

### Luna investigator

Used for focused investigation and mechanical evidence gathering:

* repository search;
* symbol discovery;
* reference lookup;
* Git inspection;
* targeted verification;
* structured extraction;
* test execution;
* residual-reference checks.

Luna may have a large working set.

Its durable output is structured findings and evidence references, not its transcript.

---

### Luna curator

A fresh Luna invocation may compact accumulated investigation findings.

It can:

* merge duplicates;
* remove resolved unknowns from the active snapshot;
* consolidate related evidence;
* replace obsolete snapshot entries;
* keep the current investigation state bounded.

It cannot manufacture stronger certainty than its source findings support.

Curation changes representation, not evidence.

---

### Sol high

Reserved for reasoning that genuinely benefits from a stronger reasoning context:

* architecture;
* lifecycle behavior;
* concurrency;
* cross-module semantics;
* ambiguous root causes;
* difficult migration semantics;
* provenance or security reasoning;
* hard trade-offs.

Sol high does not maintain task state and does not perform routine evidence bookkeeping.

Its ideal trajectory is:

```text
facts → reasoning → decision → exit
```

---

### Terra implementer

Receives an explicit implementation boundary and the facts necessary to perform the change.

Its job is implementation, not architectural scope expansion.

When assumptions fail or the required scope expands materially, control returns to the Controller.

---

### Terra reviewer

High-risk changes may receive a fresh independent review.

The reviewer is deliberately isolated from:

* previous reviewer findings;
* implementer self-justification;
* raw investigation history;
* scoring rubrics;
* unnecessary debugging history.

It returns structured issues with impact and evidence.

The Controller decides whether those findings should affect Decision Context.

---

## Typical workflows

### Microtask

For an obvious, local, low-risk change:

```text
Controller
    ↓
direct edit
    ↓
deterministic check
    ↓
done
```

No subagent is required.

---

### Normal implementation

```text
Controller
    ↓
Terra implementer
    ↓
deterministic checks
    ↓
Luna verification when useful
```

---

### Investigation

```text
Controller
    ↓
Luna investigator
    ↓
curated findings when needed
    ↓
Controller

        ├─ obvious solution → Terra
        └─ difficult reasoning → Sol high
```

---

### Complex change

```text
Luna investigation
        ↓
bounded evidence
        ↓
Sol high reasoning
        ↓
Terra implementation
        ↓
deterministic checks
        ↓
Luna verification
```

For sufficiently risky changes:

```text
        ↓
fresh Terra review
        ↓
Controller decision
```

Default concurrency is one.

Parallelism is reserved for clearly independent work.

---

## Installation

Python 3.11 or newer and Git are required.

Install directly from the repository:

```bash
uv tool install git+https://github.com/Iris0fTheValley/codex-context
```

Attach it to an existing Git repository:

```bash
cd your-repository
context init
context doctor --pretty
```

For local development:

```bash
git clone https://github.com/Iris0fTheValley/codex-context
cd codex-context

uv run --extra test pytest
uv run context version
```

---

## Quick start

Start a task:

```bash
context task-start "fix request cancellation"
```

Inspect the Controller view:

```bash
context prepare --role controller --pretty
```

Prepare an investigation:

```bash
context prepare --role luna-investigator --pretty
```

Prepare a curator when investigation findings need compaction:

```bash
context prepare --role luna-curator --pretty
```

Prepare deep reasoning context:

```bash
context prepare --role sol-high --pretty
```

Prepare implementation:

```bash
context prepare --role terra-implementer --pretty
```

Prepare an independent review:

```bash
context prepare --role terra-reviewer --pretty
```

Inspect diagnostic state:

```bash
context doctor --pretty
context stale --pretty
context milestone-check --pretty
```

Close the current task using its current revision:

```bash
context task-close --base-revision <revision>
```

---

## Repository layout

After initialization, a repository may contain:

```text
AGENTS.md

.agent-memory/
├── INDEX.md
├── operator.md
├── prompt-policy.md
├── project-conventions.md
├── decisions/
│   ├── INDEX.md
│   └── ...
└── lessons/
    ├── INDEX.md
    └── ...

.milestones/
├── INDEX.md
└── M001-name/
    ├── INDEX.md
    ├── scope.md
    ├── decisions.md
    ├── progress.md
    └── verification.md

.context/
├── config.json
├── state.json
└── backups/
```

`.context/state.json` is transient and ignored by Git.

Project memory and milestone documents are Git-owned.

---

## Task state

A task keeps structured state rather than conversation transcripts.

Conceptually it separates:

```text
Investigation history
    ↓
Curated investigation state
    ↓
Controller-promoted Decision Context

Review findings
    ↓
Controller promotion when relevant
```

Typical Decision Context contains:

* confirmed facts;
* supported evidence;
* unknowns;
* contradictions;
* constraints;
* decisions;
* relevant files and symbols;
* modification boundary;
* verification target;
* architectural intent.

Task state rejects raw transcript and tool-log fields.

The intent is to preserve traceability without converting `.context/state.json` into a second conversation history.

---

## Evidence model

The project uses four effective evidence states:

| State        | Meaning                                                      |
| ------------ | ------------------------------------------------------------ |
| `CONFIRMED`  | Supported by sufficiently strong current native evidence     |
| `SUPPORTED`  | Evidence exists, but it is weaker or indirect                |
| `UNVERIFIED` | Not yet established                                          |
| `STALE`      | Previously recorded evidence no longer matches current state |

Native evidence can include:

```text
file:path/to/file#sha256
git:path/to/file#blob-id
```

Test and runtime observations may reference the source snapshots they observed.

Their freshness proves only that those explicitly declared sources have not changed.

It does not prove that every possible dependency remains unchanged.

---

## Project memory

`.agent-memory/` stores durable project knowledge.

Examples include:

* project conventions;
* operator constraints;
* adopted decisions;
* verified recurring failure modes.

Memory entries use metadata such as:

```yaml
Evidence: file:src/example.py#...
Revision: 1
Status: ACTIVE
Applicability: src/example.py
Confidence: SUPPORTED
Kind: MEMORY
Audience: ["sol-high", "terra-implementer"]
Topics: ["request cancellation"]
Symbols: ["Request.cancel"]
```

The INDEX files are routers, not summary documents.

Normal routing is conservative and lexical.

Fresh project-wide `HARD_CONSTRAINT` entries may bypass lexical matching when their audience and evidence permit it.

---

## Milestones

`.milestones/` keeps persistent project progress separate from transient task context.

A milestone contains:

```text
scope.md
decisions.md
progress.md
verification.md
```

These files answer different questions:

* **scope** — what belongs to this milestone;
* **decisions** — milestone-specific choices;
* **progress** — current state and next work;
* **verification** — what has actually been checked.

Milestone documents are project state, not agent transcripts.

---

## Managed `AGENTS.md`

`context init` maintains a small marked block inside the repository's existing `AGENTS.md`.

It is deliberately short.

The managed block acts as a router for:

* Controller ownership;
* role isolation;
* investigation/curation;
* Decision Context promotion;
* default sequential delegation;
* microtask fast path;
* native correctness fallbacks.

Existing user content outside the managed markers is preserved.

---

## Optional tools

`codex-context` can coexist with optimization tools such as:

| Tool        | Intended use                      |
| ----------- | --------------------------------- |
| Serena      | symbol and reference navigation   |
| cachebro    | unchanged-read caching and deltas |
| agentmemory | explicit episodic recall          |

These tools are optional.

`codex-context` does not replace their databases or orchestrate their lifecycle.

If they are unavailable, use native source inspection, Git, search, compilers, tests, and runtime behavior.

---

## Diagnostics

Run:

```bash
context doctor --pretty
```

Diagnostics intentionally distinguish states such as:

```text
configured
enabled
installed
version observed
version validated
```

Authorization, health, runtime state, or subagent state remain `UNKNOWN` when the tool cannot actually prove them.

The diagnostic layer should not manufacture confidence.

---

## Recovery and uninstall

Initialization and managed mutations use:

* cross-process locking;
* atomic file replacement;
* local backups;
* hash-guarded rollback.

Rollback:

```bash
context rollback <backup-id>
```

Migration:

```bash
context migrate
```

Uninstall:

```bash
context uninstall
```

User-modified project memory is preserved rather than silently overwritten.

---

## What this project is not

`codex-context` is intentionally **not**:

* an agent runtime;
* a workflow engine;
* a recursive agent scheduler;
* a database-backed memory platform;
* a graph store;
* an embeddings-first RAG system;
* a Web UI;
* an automatic whole-repository summarizer;
* a replacement for source inspection or tests.

The project should remain small enough that deleting it does not make the underlying development workflow incorrect.

---

## Research hypothesis

The strongest claim behind this project is still a hypothesis:

> Protecting the task purity of a strong reasoning model may improve coding performance even when total available context or compute is unchanged.

In other words, two workflows with the same approximate amount of computation may behave differently:

```text
Workflow A

Sol:
search
→ inspect
→ reason
→ implement
→ debug
→ reread logs
→ verify
→ self-review
→ revise
```

versus:

```text
Workflow B

Luna:
investigate
→ structured evidence

Sol:
focused reasoning
→ decision

Terra:
implementation

Luna:
verification

Terra:
fresh review when required
```

The second workflow deliberately terminates disposable contexts instead of allowing every intermediate task to remain inside the strongest model's reasoning trajectory.

This project is an attempt to make that boundary explicit and testable.

It does **not** assume that more agents are always better.

It does **not** assume that less context is always better.

The intended principle is narrower:

> **Give each reasoning context the information it needs, and avoid giving it unrelated objectives merely because that information exists.**

---

## Current limitations

The project is still early.

Current limitations include:

* routing is intentionally conservative;
* task state is local and single-task rather than a task database;
* evidence freshness cannot prove undeclared dependencies;
* role execution is still performed by Codex rather than by this package;
* external adapter health cannot always be observed directly;
* the benefits of cognitive isolation still require controlled evaluation on real coding workloads.

Complexity will only be added when real tasks demonstrate that it improves downstream quality or reliability.

---

## Development

Run the test suite:

```bash
uv run --extra test pytest
```

CI currently covers supported Python versions used by the project.

Changes should preserve the central invariants:

1. correctness does not depend on optional optimization tools;
2. raw exploration does not automatically propagate downstream;
3. evidence cannot become stronger merely through summarization;
4. high-reasoning contexts stay focused;
5. failure should degrade efficiency before it degrades correctness;
6. the project remains a thin layer around Codex rather than becoming another agent framework.

---

## License

MIT License. See [`LICENSE`](LICENSE).

---

## Contributing

The project is experimental, so small and evidence-backed changes are preferred.

Useful contributions include:

* reproducible routing failures;
* provenance or freshness bugs;
* migration and recovery failures;
* role-isolation leaks;
* real-world benchmark results;
* simplifications that preserve behavior.

Large framework additions should be justified by a concrete failure mode that cannot be solved by the existing small architecture.
