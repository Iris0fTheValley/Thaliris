# Thaliris

Main now distributes Host-neutral Core, shared semantic guidance and ABCD benchmark protocol/history. `thaliris-core` exposes Core operations. Native integration lives in [Thaliris-Codex](https://github.com/Iris0fTheValley/Thaliris-Codex) and [Thaliris-DSH](https://github.com/Iris0fTheValley/Thaliris-DSH). See [installation and API boundaries](docs/host-neutral-packaging.md).

[中文](README.md)

A lightweight, Git-native context and orchestration layer for AI coding workflows.

Thaliris helps multi-agent coding workflows keep the right information in the right reasoning context without turning the repository into an agent framework.

It manages the conditions under which information enters a reasoning path, not agents as a general-purpose lifecycle system. Evidence, freshness, memory, and adapter safeguards exist only to prevent incorrect, stale, irrelevant, or role-mismatched information from being propagated. Lower cost is a possible result, never a reason to discard necessary context.

It provides:

* shared semantic guidance for role-specific work;
* evidence-backed project memory;
* transient task state;
* investigation and review handoffs;
* freshness tracking;
* milestone state;
* conservative routing;
* deterministic validation and recovery.

With the Codex adapter, Codex is the runtime and controller. With any adapter, source code, Git, tests, compilers, and runtime behavior remain the correctness core.

> **Status:** Beta. The current implementation is intentionally small and is still being evaluated on real coding workloads.

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

Thaliris is built around a simple idea:

> **Preserve useful information without forcing every role to carry every piece of information.**

The project therefore treats context boundaries as part of the engineering architecture.

---

## Why Thaliris

**Thaliris** combines **Thalamus** and **Iris**.

The thalamus filters and routes information entering cognition; the iris
regulates how much light reaches vision. The name is an image for agent
context: control what reaches a reasoning path, preserve evidence-backed
information, and isolate unrelated working sets.

---

## Context and runtime contracts

Context quality is not context quantity. Runtime prompts are themselves part of the
working context: repeated rules, unrelated history and competing objectives can dilute
the evidence needed for reasoning. Preserve necessary facts and hard invariants while
giving high-capability models dense, low-noise working context. Each invariant has one
authoritative normal runtime expression and a meaningful boundary; explanations and
history live in docs. Selective multilingual islands preserve language-specific meaning
and optimize representation; random switching or adding languages is not the objective.

Normal Controller routing, handoffs, evidence reuse, waiting, endpoints, acceptance and causal diagnosis stay resident; exceptional recovery, Host maintenance and historical migration steps are retrieved on demand. Each necessary dependency has one observation owner: executors wait on their tests, processes and CI; Controller waits for the necessary child result without checking the same job again. Tool maximum is capacity, higher-level duration limits take precedence, and cost assessment includes normal task context, retrieval/reconstruction and delivered quality.

Controller owns direction, scope, acceptance and next routing, while executor owns
implementation design. Decision-complete handoffs reuse selected evidence and established
inventory. Ordinary Implementer converges stable direction; Focused Implementer owns the
full reasoning/implementation/runtime-feedback/revision loop until semantic convergence,
then releases that working context for fresh ordinary deterministic closure. Reviewer is
independent and non-writing; critical acceptance needs supporting evidence. Core records
mechanical facts without interpreting role applicability or semantic completion.

The [routing protocol](docs/thaliris-routing-protocol.md) and
[prompt ownership/research motivation](docs/thaliris-prompt-design.md) explain these boundaries.
Global/project/role prompt generation and native enforcement belong to Host adapters.
ABCD results remain historical evidence for their original setups; this normalization
was not benchmarked, and smaller prompt sizes do not establish quality gains.

## Installation

The legacy `context` command examples in this README describe Codex-adapter behavior and are retained as design background. Core no longer exposes prepare/recall, doctor, migrate or native role packs. See [Core and Host adapter boundaries](docs/host-neutral-packaging.md), the [current Codex adapter guide](https://github.com/Iris0fTheValley/Thaliris-Codex/blob/main/README.md), and the [DSH adapter guide](https://github.com/Iris0fTheValley/Thaliris-DSH).

Python 3.11 or newer and Git are required.

Install directly from the repository:

```bash
uv tool install git+https://github.com/Iris0fTheValley/Thaliris
```

Attach it to an existing Git repository:

```bash
cd your-repository
context init
context doctor --pretty
```

For local development:

```bash
git clone https://github.com/Iris0fTheValley/Thaliris
cd Thaliris

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
context prepare --role investigator --pretty
```

Prepare a curator when investigation findings need compaction:

```bash
context prepare --role curator --pretty
```

Prepare deep reasoning context:

```bash
context prepare --role reasoning-specialist --pretty
```

Prepare implementation:

```bash
context prepare --role implementer --pretty
```

Prepare an independent review:

```bash
context prepare --role reviewer --pretty
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

The intent is to preserve traceability without converting `.context/state.json` into a second conversation history. Semantic records have stable IDs and explicit transitions. When a verification target exists, close requires a trusted runtime observation bound to the current target, source identity, and task surface; a model saying that tests passed is not proof.

### Bounded durable promotion

The task-end order is `task-local state -> Controller retention decision -> minimal durable promotion -> task-close`. This is explicit persistence, not automatic summarization; if there is no durable knowledge, no durable content is written. Only the Controller may run `task-promote`, and it may submit only explicit `decision`, `invariant`, `failure_mode`, or `constraint` records, or explicit `progress`/`verification` fields for the current milestone. For continuous feature work with a current milestone, retain actual progress and verification there first; `.agent-memory/` retains only cross-task reusable decisions, constraints, invariants, and failure modes. Unless the user explicitly asks, a repository task does not proactively read or write personal/global Codex memory such as `~/.codex/memories` or `MEMORY.md`; project continuity uses `.agent-memory/`, `.milestones/`, `task-promote`, and tracked-document maintenance. Inputs must use only evidence refs already in the ACTIVE task and must pass fresh native file/git evidence or fresh test/runtime evidence with native `source_refs`; a CONFIRMED promotion must also directly reference fresh CONFIRMED file/git evidence. Raw findings, transcripts, logs, and unknown fields are rejected. Promotion uses a base-revision CAS and does not change the task revision. Each task may consume at most 16 promotion units (one per memory record and per milestone progress/verification field); the counter is bounded task-local bookkeeping, not long-term memory or a framework.

Minimal order and JSON example:

```bash
context task-start "adopt request policy"
# ...the Controller receives task-local evidence and decides retention...
context task-promote --role controller --base-revision <revision> --input promote.json
context task-close --base-revision <revision>
```

```json
{"records":[{"type":"decision","id":"D-001","title":"Use X","text":"Adopt X.","evidence_refs":["e1"],"confidence":"SUPPORTED"}]}
```

Memory only appends a new entry and one router link to the existing INDEX; milestone updates touch only explicitly supplied fields and use the atomic backup path. History-heavy recall, deduplication, stale cleanup, conflict judgment, INDEX restructuring, and bulk milestone maintenance must be narrowed and delegated to a fresh child.

### Child lifecycle epistemic/control policy

No result observed yet does not mean failed; timeout, slow, or incomplete observation does not mean capability limitation. Without explicit evidence, a child state remains `UNKNOWN`. `RUNNING` means wait/re-observe; `UNKNOWN` means keep `UNKNOWN`/re-observe. A single wait-window expiry must not close, replace, or take over the child. Only explicit `FAILED`, `CANCELLED`, `UNAVAILABLE`, or deterministic spawn failure permits narrower fresh delegation. A minimal capability fallback is allowed only when the objective capability is unavailable, and it must not become an excuse for Controller investigation or implementation. After child failure, first narrow the scope and delegate a fresh child. This is managed Controller policy over Codex-native observations, not a Thaliris runtime, scheduler, heartbeat, retry state machine, or agent framework; Thaliris deterministically enforces only its fields, evidence/freshness, CAS, role projection, and capture filtering.

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

The former Codex-adapter `context recall` command provided explicit, conservative lexical retrieval. Durable memory was not injected into ordinary role packs; recall returned candidates without accepting them into task state or propagating them downstream. Core-only CLI does not provide this command; see the [current Codex adapter guide](https://github.com/Iris0fTheValley/Thaliris-Codex/blob/main/README.md) for supported commands.

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

The Codex adapter's `context init` maintains a small marked block inside the repository's existing `AGENTS.md`. Core-only CLI does not provide this Host setup command; see the [current Codex adapter guide](https://github.com/Iris0fTheValley/Thaliris-Codex/blob/main/README.md).

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

Thaliris can coexist with optimization tools such as:

| Tool        | Intended use                      |
| ----------- | --------------------------------- |
| Serena      | symbol and reference navigation   |
| cachebro    | unchanged-read caching and deltas |
| agentmemory | explicit episodic recall          |

These tools are optional.

Thaliris does not replace their databases or orchestrate their lifecycle.

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

Thaliris is intentionally **not**:

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

Investigator:
large-scale scan
→ compressed facts and evidence

Focused Executor:
read a small number of key materials
→ focused reasoning
→ implementation
→ verification

Independent Reviewer:
fresh review when required
```

The second workflow deliberately terminates disposable contexts instead of allowing every intermediate task to remain inside the strongest model's reasoning trajectory.

This project is an attempt to make that boundary explicit and testable.

It does **not** assume that more agents are always better.

It does **not** assume that less context is always better.

The intended principle is narrower:

> **Give each reasoning context the information it needs, and avoid giving it unrelated objectives merely because that information exists.**

---

## Research motivation and limits

These papers motivate design choices; they do not validate Thaliris or its compression ratios.
[Liu et al. (2024), Lost in the Middle](https://doi.org/10.1162/tacl_a_00638) examines positional
and structural context utilization. [Jiang et al. (2024), LongLLMLingua](https://doi.org/10.18653/v1/2024.acl-long.91)
reports information-density/efficiency and performance effects on its tested tasks.
[Mondshine, Paz-Argaman and Tsarfaty (2025), Beyond English](https://doi.org/10.18653/v1/2025.findings-naacl.73)
supports task-dependent language treatment; [Kim et al. (2025)](https://doi.org/10.18653/v1/2025.findings-emnlp.1215)
examines English-Korean language-specific nuances and knowledge cues, not a universal benefit.
[Park et al. (2026)](https://arxiv.org/abs/2606.19668) motivates caution about random switching
and anchoring. These supplied references are motivation, not newly reproduced experiments.
ABCD results remain historical evidence for their original setups; prompt normalization was
not benchmarked here, and byte/token estimates are sizing observations only.

## Host adapters

Core is runtime-neutral: it does not install Host hooks or execute agents. [Thaliris-Codex](https://github.com/Iris0fTheValley/Thaliris-Codex) and [Thaliris-DSH](https://github.com/Iris0fTheValley/Thaliris-DSH) provide native integrations over the shared Core. A verification target is a requirement, not shell authority. Only an adapter observation with an explicit execution-completion status may submit a trusted result; without such a runtime payload, the result remains `UNKNOWN`.
---

## Current limitations

The project is still early.

Current limitations include:

* routing is intentionally conservative;
* task state is local and single-task rather than a task database;
* evidence freshness cannot prove undeclared dependencies;
* role execution is supplied by host adapters rather than by Core;
* external adapter health cannot always be observed directly;
* the benefits of cognitive isolation still require controlled evaluation on real coding workloads.

Complexity will only be added when real tasks demonstrate that it improves downstream quality or reliability.

---

## Development

Run the Core tests:

```bash
uv run --extra test pytest tests/test_core_authority.py tests/test_mechanical_core.py tests/test_core_cli.py
```

ABCD source tests additionally install the Codex adapter explicitly; see [package and verification instructions](docs/host-neutral-packaging.md). These tests validate the protocol and tools without starting a benchmark.

Verification is layered by changed surface, risk, and fresh evidence: use the smallest targeted tests during development, combine related fixes before related regression, then run one complete relevant validation for the change. Documentation-only changes, low-risk P2 fixes, and merges/conflicts that do not change already-verified behavior code do not automatically repeat expensive checks. This does not lower completion criteria; user-requested real runtime or visible-behavior verification cannot be replaced by static tests.

CI currently covers supported Python versions used by the project.

Changes should preserve the central invariants:

1. correctness does not depend on optional optimization tools;
2. raw exploration does not automatically propagate downstream;
3. evidence cannot become stronger merely through summarization;
4. high-reasoning contexts stay focused;
5. failure should degrade efficiency before it degrades correctness;
6. the project remains a thin, Host-neutral layer around shared Core rather than becoming another agent framework.

---

## Related projects / Integrations

* [Thaliris-codex](https://github.com/Iris0fTheValley/Thaliris-codex): Codex hooks, native identity and lifecycle, profiles, installation and recovery.
* [Thaliris-dsh](https://github.com/Iris0fTheValley/Thaliris-dsh): a DeepSeek Harness plugin using native Settings, model catalogs, Workspaces, Sessions, Subagents and the shared Web/Desktop client.
* [Benchmark](benchmarks/abcd): ABCD implementation, historical evidence index and [protocol](docs/thaliris-benchmark-protocol.md) remain in this main repository.

Both adapters depend on the same Host-neutral Core; neither is another Core implementation. DSH provides editable role/persona, model, tool and context policies; built-in roles are templates. Memory capability and the default provider are independently removable, replaceable components, with multiple providers supported. Disabling memory leaves task/routing available. Users explicitly configure read/write grants and long-term write policy; providers own their RAG/embedding internals, which are not Core dependencies.

## ABCD benchmark results

We ran a controlled single-task benchmark to separate **model capability**, **orchestration**, and **heterogeneous intelligence allocation**. A/B/C used the same task, BASE revision, Codex version, isolated workspace/CODEX_HOME and environment; D is a previously sealed production-architecture run and was not rerun.

The four completed arms test two primary hypotheses:

**Orchestration Gain — B → C:** does role decomposition and isolated multi-agent execution improve a Luna-only system over a single Luna agent?

**Intelligence Allocation Gain — C → D:** once orchestration exists, does selectively placing stronger models at semantic implementation/review/closure points materially improve the result?

### Results

| Arm | Configuration | Coverage | Correctness | Compatibility | Implementation | Verification | Mean | Completion | Wall time | Cost proxy |
|---|---|---:|---:|---:|---:|---:|---:|---|---:|---:|
| **A** | Sol medium, single agent | 6 | 4 | 6 | 6 | 7 | **5.8** | Partial | **21m36s** | **$0.883** |
| **B** | Luna xhigh, single agent | 6 | 5 | 6 | 6 | 4 | **5.4** | Partial | **54m09s** | **$0.232–0.235** |
| **C** | Thaliris, Luna-only | 4 | 6 | 7 | 6 | 4 | **5.4** | Managed DONE / product partial | **41m11s** | **$0.272** |
| **D** | Thaliris, heterogeneous routing | **9** | **8** | **8** | **8.5** | **8** | **8.3** | Largely complete; one P2 remains | **64m47s** | **$2.475** |
| **E?** | D topology, **all-Sol workers** | **9?** | **8?** | **8?** | **8.5?** | **8?** | **8.3?** | D-like? | **64m47s?** | **~$3.67 predicted** |
| **F?** | D + **semantic-convergence cut** | **9?** | **8?** | **8?** | **8.5?** | **8?** | **8.3?** | D-like? | **64m47s?** | **~$2.06–2.07 predicted** |

A/B/C's independent scores and runtime/cost measurements come from the fresh benchmark assessment. D's original sealed assessment rated all five dimensions `GOOD`; the numeric 8.3/10 row above is a later read-only re-evaluation of the same frozen candidate using the A/B/C rubric. The original D run itself remains sealed and unchanged. Its production routing was Luna Investigator → Sol Focused Implementer → Sol Reviewer → Luna repair → Sol Reviewer → Luna repair.

### Token structure

`cached input` is a subset of input, not additional tokens.

| Arm | Input | Cached | Fresh input | Output | Reasoning output | Model distribution |
|---|---:|---:|---:|---:|---:|---|
| **A** | **3.104M** | 2.962M | 0.142M | 30.3k | 7.1k | 100% Sol medium |
| **B** | **16.70M** | 16.39M | 0.309M | 79.8k | 46.8k | 100% Luna xhigh |
| **C** | **15.73M** | 15.03M | 0.695M | 105.0k | 66.3k | 100% Luna xhigh |
| **D** | **15.22M** | 14.51M | 0.706M | 108.2k | 44.2k | Sol: 9.96M input / 64.3k output; Luna: 5.26M / 43.9k |
| **E? all-Sol** | **~15.22M?** | ~14.51M? | ~0.706M? | **~80.9k predicted** | ? | Same D topology, Luna nodes replaced by Sol |
| **F? semantic cut** | **~14.05–14.65M predicted** | ? | ? | **~100.9–108.9k predicted** | ? | Sol ~8.09M input; Luna ~5.96–6.56M |

Observed D usage was 15.219M input, of which 14.513M was cached. Luna consumed 5.260M input / 43.9k output, while Sol consumed 9.959M input / 64.3k output.

### What each arm shows

| Arm | Strength | Main weakness |
|---|---|---|
| **A — Sol solo** | Fastest run; strong implementation and extensive self-generated verification. | A single trajectory developed a coherent but incomplete semantic model. Its tests largely validated its own assumptions, leaving cross-surface ownership/replay/shutdown defects. |
| **B — Luna solo** | Extremely cheap. With much more compute and time, Luna reached nearly the same aggregate score as A. | ~5.4× A's input and ~2.5× wall time; weak global semantic convergence and verification. Large compute did not eliminate lifecycle/authority gaps. |
| **C — Luna orchestration** | Clear role separation, managed lifecycle, ~13 minutes faster than B, and slightly better correctness/compatibility. | **No aggregate quality gain over B.** Coverage fell 6→4. Treatment review produced a false-negative closure and the managed task reached DONE while product acceptance remained incomplete. |
| **D — heterogeneous Thaliris** | Only configuration to cross into substantially stronger completion. Independent review → repair → re-review actually changed the candidate and closed defects. | Most expensive and slowest observed arm. Sol accumulated large cached-context replay; one later P2 presentation-lifecycle defect remained and real GPU/audio/UI behavior was still unverified. |

A/B/C's principal independent defects are documented in the assessment: each reached a different partially-correct implementation rather than failing in exactly the same way.

### Hypothesis 1 — Orchestration Gain

**Method:** compare **B vs C** while holding actual execution capability at Luna xhigh. B is one Luna agent; C uses Thaliris roles, isolated child contexts and managed lifecycle, but every observed worker remains Luna xhigh.

**Observed result:**

`5.4 → 5.4`

No product-quality gain was observed. C was about **13 minutes faster** and used slightly fewer total tokens, but its estimated cost was **~16–18% higher** because more input was uncached. Its quality distribution changed rather than improving overall: coverage −2, correctness +1, compatibility +1.

**Conclusion:** orchestration alone did not make the weaker model materially stronger in this sample. It showed workflow/lifecycle and throughput benefits, but not aggregate quality improvement.

### Hypothesis 2 — Intelligence Allocation Gain

**Method:** compare **C vs D**. Both use Thaliris orchestration, but D selectively assigns Sol to the Controller, core semantic implementation and independent review while retaining Luna for investigation and bounded repair.

**Observed result:**

`5.4 → 8.3`

The largest rubric jumps were:

`Coverage: 4 → 9 (+5)`<br>
`Verification: 4 → 8 (+4)`<br>
`Implementation: 6 → 8.5 (+2.5)`<br>
`Correctness: 6 → 8 (+2)`<br>
`Compatibility: 7 → 8 (+1)`<br>

D cost about **9.1× C** and took about **1.57× longer**, but it was the only arm to substantially cross the product-completion threshold. D used no parallel execution; the main observable mechanism was repeated **Reviewer → bounded repair → re-review**, not agent count or parallel compute.

**Conclusion:** the result supports **selective intelligence allocation**, not “more agents are automatically better.”

### Two cost hypotheses to test next

**E — All-Sol counterfactual.** Keep D's task, topology, role sequence and lifecycle unchanged, but replace Luna Investigator/Implementer nodes with Sol. Input/context replay is held approximately constant; only output is adjusted using the observed A/B output-efficiency ratio (`79.8k / 30.3k ≈ 2.64×`). This predicts approximately **$3.67** for an all-Sol D-shaped run versus **$2.475 observed**, implying roughly **32.6% routing savings** from heterogeneous execution if D-level quality is preserved. Without the output-efficiency adjustment, the simple same-token estimate is about **$3.94**. This remains a counterfactual until run.

**F — Semantic-Convergence Cut.** Keep D's architecture and high-capability semantic nodes, but terminate the Sol Focused Implementer once the core implementation and hard invariants are established. Broad tests, build/lint closure, deterministic compatibility fallout and small repairs move to a fresh Luna Implementer; a fresh Sol Reviewer remains responsible for semantic acceptance. Trace-based estimation removes roughly **1.87M Sol input / 15.3k Sol output** and adds approximately **0.7–1.3M Luna input / 8–16k output**, predicting **~$2.06–2.07**, or roughly **16–17% below D**, while targeting the same 8.3-level result. Quality remains explicitly unknown until tested.

### Bottom line

The benchmark currently supports a narrower claim than “multi-agent is better”:

> **Weak-model orchestration alone did not improve aggregate quality. Selective placement of stronger intelligence at semantic implementation, review and closure points did.**

It also exposes the next optimization target: **not less high-capability implementation, but shorter expensive-context lifetime**. High-capability models should remain available for work that genuinely requires their reasoning during execution; once the semantic solution has converged, deterministic closure can move to cheaper fresh workers instead of repeatedly replaying a large Sol context.

## Benchmark boundary

`benchmarks/abcd/` may contain complex collectors, formal authority, and
offline scoring. The production `thaliris` Core package does not depend on D11,
formal registries, capture authority, or benchmark receipt issuers. Benchmarks
observe production; they do not define production architecture.

See [DESIGN.md](DESIGN.md) and
[docs/thaliris-routing-protocol.md](docs/thaliris-routing-protocol.md).

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
