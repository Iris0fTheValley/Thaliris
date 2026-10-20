# Thaliris

[简体中文](README.md)

**Attention is the most expensive resource.**

Thaliris is a **cognitive orchestration layer** for AI coding agents. It does not shorten context; it addresses two problems in long tasks:

- A capable model's attention is diluted by noise. Exploration, debugging and logs should not stay in the reasoning path responsible for key judgments.
- Original requirements and counterevidence can disappear during handoffs. A local “done” report must not silently overwrite an issue already found.

> **Protect the reasoning. Isolate the noise. Isolation without amnesia.**

Thaliris builds on the native Agent capabilities of Hosts such as Codex and DeepSeek Harness, adding a layer for isolation, handoffs and evidence continuity rather than creating another Agent Runtime.

> **Status: Beta.** Real refactoring work has shown an implementer dispatching an investigation, a Controller starting an independent review, and counterevidence driving repairs. The sample is too small to establish a general quality or cost advantage. See [empirical observations](#empirical-observations).

## Why this is not context management

Common approaches manage more context within one Agent through compaction, retrieval or memory. Thaliris sees a larger problem than token count: too many competing goals share one reasoning path. The same Agent may be expected to investigate, design, implement, debug, review its own work and remember earlier failures.

Thaliris manages **who reasons and with what reasoning context**:

> **Give each reasoning context the information it needs; do not include other information merely because it exists.**

The name combines Thalamus, which filters and routes information, and Iris, which regulates how much light reaches the eye.

## Three pillars

### 1. Cognitive isolation: focus capable models on the work that needs them

A long-lived **Controller** retains the user goal, hard constraints and acceptance criteria. Short-lived roles work in fresh contexts and return conclusions, sources, verification results and decision-changing unknowns rather than the full working trail.

| Role | Responsibility |
| --- | --- |
| Investigator | Investigate facts within the selected scope |
| Implementer | Implement an accepted direction and verify it |
| Focused Implementer | Handle tightly coupled design and implementation until the core semantics converge |
| Reviewer | Optionally challenge a candidate independently and read-only |

Roles are selected as needed, not used as a fixed pipeline. Single-Agent work, direct Controller execution and delegation are all valid. Different roles can use models with different capabilities, keeping stronger models at decision-critical points.

### 2. Evidence continuity: isolate without forgetting

The main risk of isolation is that a counterexample found by a reviewer can disappear after several handoffs and repairs behind a simple “tests pass.” Thaliris addresses that risk with these rules:

1. **Record counterevidence.** When a child discovers a fact that changes a local conclusion, local acceptance or critical unknown, record an observation with sources, handoff provenance and its associated user requirement.
2. **Keep it visible until disposition.** Relevant observations remain visible in later handoffs until the Controller explicitly judges each related requirement satisfied, unknown, needing repair, or no longer relevant with a reason.
3. **Good news does not erase bad news.** A later test PASS, Reviewer READY, child Completed or Core DONE does not retire an earlier repair or unknown basis. The Controller must explicitly respond to it.
4. **Present evidence before the next decision.** The Adapter returns still-unresolved evidence with the child result before the Controller's next broad completion decision. This needs no extra Agent, fixed stage or polling.
5. **Append history instead of rewriting it.** Earlier observations and judgments remain in the record without automatically becoming current facts.

Core stores these links and append-only history; it does not decide what matters. The Controller decides relevance and acceptance.

~~~text
Reviewer finds a counterexample -> observation with source and requirement
                    |
      repair, test PASS, child Completed ... do not erase it
                    |
Controller disposition: satisfied / unknown / repair / no longer relevant
~~~

### 3. Semantics belong to the model; mechanics belong to Thaliris

The mechanical layer handles identity, sources, versions, continuity and bounded retrieval; semantic judgments stay with the model. Conclusions carry sources such as file hashes, Git blobs or test observations. Freshness only says whether declared sources changed; it does not prove every dependency stayed unchanged. When evidence is insufficient, keep the state UNKNOWN rather than upgrading an inference to a confirmed fact.

## Components

| Component | Responsibility |
| --- | --- |
| **Thaliris Core** (this repository) | Task IDs and task records, observation/judgment links, evidence and freshness, project memory, milestones, compare-and-swap writes and rollback |
| [Thaliris-codex](https://github.com/Iris0fTheValley/Thaliris-codex/blob/main/README.md) | Native Codex integration: Fresh Children, role profiles, identity and lifecycle, and evidence re-presentation |
| [Thaliris-dsh](https://github.com/Iris0fTheValley/Thaliris-dsh/blob/main/README.md) | DeepSeek Harness plugin: Workspace/Session/Agent integration and optional Memory |

There is one shared Core. Core does not run models, schedule Agents or authenticate callers; native execution belongs to each Adapter.

## Empirical observations

**What this benchmark measures:** We chose a difficult single-turn refactor: desktop and WebUI share Live2D behavior, with model selection, voice/action queues and exit lifecycle involved. The goal is not to fix every bug in one turn. It is to observe whether original requirements keep influencing decisions through investigation, implementation, handoffs, review and repair.

**How to read the results:** Each frozen candidate received an independent, strict product post-review that continued looking for counterexamples. Every row therefore has residual defects, many of which existed in the starting code. Compare whether severe P1 gaps were contained and whether the collaboration behavior actually occurred.

| Sample | Execution | Independent review drove repair | Residual P1 after review (original requirement gaps) | P2 | Runtime | API-equivalent cost |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| C · 10/14 | Luna multi-agent | Yes, local | 2 | 3 | 57.1 min | $0.46 |
| D · 10/14 | Sol + Luna multi-agent | Yes | 1 | 2 | 40.4 min | $2.62 |
| C · 10/19 | Luna (dispatch rejected; single-agent fallback) | No | 3 | 3 | 19.8 min | $0.22 |
| **D · 10/19** | **Sol + Luna native multi-agent** | **Yes, two counterexamples triggered repairs** | **0** | **3** | **34.4 min** | **$2.91** |

The October 14 and October 19 C/D rows are separate runs. The frozen historical single-agent candidates A and B (October 14–15, 2026) each received a new independent product post-review by GPT-6.1 Sol High, and both reviews found concrete failure counterexamples; they were not assigned P1/P2 counts under this table's criteria.

Representative findings were that A's desktop conversion path replaced an explicitly selected custom model with a Sakiko costume and its Web presentation kept only the latest no-audio motion; B's backend missed some character-state and cancellation ingress, and bye did not preempt a playing segment. The original reviews used high/medium severity labels, which are not converted into this table's P1/P2 counts.

API-equivalent costs are reference estimates for comparison, not actual billed amounts. The D · 10/19 external post-review found no P0 or P1 issue, but reported three P2 classes and concluded PARTIALLY SUPPORTED / NOT_READY; this is not full product acceptance. The three classes were: a segment queued before cancellation could arrive afterward and resume playback; an in-flight producer could publish after the shutdown bye, while a separate frontend reproduction also accepted a later segment; and Web selected mouth-parameter names by model version, failing on supported alternate spellings that desktop selected from actual parameter IDs. A conflicting native Agent status during that run was handled as a Codex-native lifecycle anomaly.

**What happened in D · 10/19:**

~~~text
Controller assigns coupled design and implementation to Sol
  -> Sol independently dispatches Luna to investigate runtime support and test boundaries
  -> Sol returns a local candidate
  -> Controller starts an independent review instead of treating local completion as the end
  -> Reviewer finds two counterexamples that overturn the local conclusion:
       - an explicitly selected model can be replaced by an older desktop rule
       - an exit farewell may be sent after its event channel has closed
  -> Controller accepts the counterevidence and dispatches repairs and regression checks
~~~

This demonstrates the behavior Thaliris is designed to test: **local success is not global completion, and counterevidence changes the work that follows.**

**C · 10/19 also matters:** This was not a successful multi-agent run. Luna's request to pass the full conversation history to a child was correctly rejected by Fresh Context protection; it did not retry with an independent context, so the task returned to single-agent execution. This shows that isolation protection worked, while also showing that a critical dispatch decision needs a capable model.

**What is not yet established:** Each arm is a single run; Host and model effort differed between batches, so this is not a single-variable experiment. The mixed-model configuration cost more. Some counterevidence from D · 10/19 review and repair led to real fixes but was not recorded as formal observations, so the persistent Evidence Continuity path is still being completed. See the [ABCD benchmark implementation](https://github.com/Iris0fTheValley/Thaliris/tree/main/benchmarks/abcd) and [benchmark protocol](https://github.com/Iris0fTheValley/Thaliris/blob/main/docs/thaliris-benchmark-protocol.md).

## Quick start

Python 3.11 or newer is required. Git is optional for Core use; installing from the Git URL below also requires Git.

~~~bash
uv tool install git+https://github.com/Iris0fTheValley/Thaliris
cd your-repository
thaliris-core --root . init
TASK_ID=$(thaliris-core --root . task-start "example task" | python -c 'import json,sys; print(json.load(sys.stdin)["task_id"])')
thaliris-core --root . --task-id "$TASK_ID" task-status
~~~

Each task has its own Task ID, which is passed explicitly to later operations. Installing Core alone does not enable multi-agent work. For native integration, follow the [Codex](https://github.com/Iris0fTheValley/Thaliris-codex/blob/main/README.md) or [DSH](https://github.com/Iris0fTheValley/Thaliris-dsh/blob/main/README.md) guide.

An initialized repository contains:

~~~text
.agent-memory/   # selected knowledge that can be reused across tasks
.milestones/     # long-term scope, decisions, progress and verification
.context/tasks/<task-id>/state.json   # task state and evidence; ignored by Git by default
~~~

Task state stores structured facts, observations and judgments, not conversation transcripts. Persistence and handoff are separate choices: recorded information is not automatically passed to every role.

## What it is not

Thaliris is not an Agent Runtime, workflow engine, fixed multi-agent pipeline, vector database or RAG system, automatic whole-repository summarizer, or substitute for source code, tests, compilers and runtime behavior.

Removing Thaliris should not make the underlying development process incorrect.

## Further reading

- [Core design](https://github.com/Iris0fTheValley/Thaliris/blob/main/DESIGN.md)
- [Routing protocol](https://github.com/Iris0fTheValley/Thaliris/blob/main/docs/thaliris-routing-protocol.md)
- [Task authority contract](https://github.com/Iris0fTheValley/Thaliris/blob/main/docs/thaliris-task-authority.md)
- [Prompt ownership and research motivation](https://github.com/Iris0fTheValley/Thaliris/blob/main/docs/thaliris-prompt-design.md)
- [Role descriptions](https://github.com/Iris0fTheValley/Thaliris/blob/main/docs/thaliris-role-packs.md) · [Packaging and API boundaries](https://github.com/Iris0fTheValley/Thaliris/blob/main/docs/host-neutral-packaging.md)

## Development and contribution

~~~bash
git clone https://github.com/Iris0fTheValley/Thaliris
cd Thaliris
uv run --extra test pytest
~~~

Small, evidence-backed changes are welcome: reproducible routing failures, counterexamples lost across handoffs, provenance or freshness defects, role-isolation leaks, real benchmark results, and simplifications that preserve behavior. New complexity needs a concrete failure that the current architecture cannot handle.

MIT License; see [LICENSE](LICENSE).
