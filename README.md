# Thaliris Core

Thaliris is a small, Git-native information-topology core for agent workflows.
It retains task history and provenance without treating their existence as
permission to occupy every future model context.

```text
repository / raw provenance / durable memory
        retained and addressable, not automatically exposed
                            |
                 evidence-backed task state
                            |
                 role-specific projection
                            |
              fresh role-specific reasoning context
```

The Core supplies bounded task state and Controller packets, semantic role
projections, evidence freshness, external artifact pointers, project memory,
milestones, explicit durable promotion, and atomic CAS-backed persistence and
recovery. It is runtime-neutral: it does not execute agents, define hooks or
sessions, run shell commands, or know model aliases. Runtime adapters map Core
contracts to their own execution environments.

## Operating Principles

- Working set is not handoff set.
- Retention is not retrieval, and retrieval is not propagation.
- Availability is not injection.
- History retention is not active-context permission.
- Recorded truth is not effective current truth.
- Fresh role context does not mean zero useful state.

Raw findings, transcripts, logs, evidence registries, durable-memory bodies,
and artifact contents remain retained or externally addressable. They do not
cross a role boundary by default. The Core constrains propagation paths and
evidence semantics; it does not replace a model's relevance judgement with a
fixed handoff quota. An explicitly selected large payload remains valid.

## Durable Memory

Durable memory is retained, not automatically injected into a role pack.
`context recall QUERY --role ROLE` is explicit retrieval: it returns routed,
evidence-aware candidates but neither accepts them into task state nor forwards
them to another role. The model decides whether a retrieved item is relevant
enough to select; Core validates how selected material is recorded and
propagated.

## Semantic Task State

Constraints, unknowns, contradictions, and decisions have stable IDs and
historical states. Ordinary `task-update` cannot replace their collections.
The Controller proposes a small transition vocabulary which Core validates:
`add`, `resolve`, `reopen`, `adjudicate`, and `supersede`.

- Active constraints remain retained until an explicit resolve transition.
- Unknowns remain open until resolve and can be explicitly reopened.
- Contradictions remain open until resolve or adjudicate.
- Decisions remain historical after explicit supersession; the prior ID links to
  its replacement.
- Raw investigation and review findings are append-only.
- Curator snapshots may replace/supersede their view, but remain
  provenance-bound to raw findings and cannot promote epistemic status.

Evidence freshness changes projections, not recorded history. A stale active
constraint remains applicable with `STALE_PROVENANCE`; stale active decisions
and contradictions are marked `REVALIDATION_REQUIRED`. Unknowns remain open.

## Verification And Current Surface

An artifact pointer records a content SHA-256 at registration. The historical
pointer remains readable after a file changes or disappears, while projections
report `FRESH`, `STALE`, `MISSING`, or `LEGACY`.

Verification targets are requirements, not shell authority. Core does not infer
test success from a model-authored `summary`, `locator`, or command text. A
normal `test`/`runtime` evidence record is a report only. A task with a target
can close only after a trusted runtime adapter records an immutable observed
execution result with `PASSED`, fresh native source identities, and full surface
coverage. The adapter is responsible for producing that trusted observation;
Core validates the attested result and its current source freshness. Thaliris
does not claim to independently prove arbitrary shell commands ran correctly.

At task start, Core captures the Git-visible dirty baseline. At close it
combines explicit target bindings, verification-target artifact bindings, declared changed
surface, and newly changed Git paths within the modification boundary. A
post-start path outside those signals is attribution `UNKNOWN`, so close fails
until reconciliation rather than silently assuming it was unrelated. Unchanged
dirty files that predate the task stay baseline workspace state and do not by
themselves fail the task. This is conservative attribution, not a claim that
Core can identify every concurrent human edit.

## Research / Design Evidence

These works motivate design questions and empirical risks. They do not prove
that Thaliris works, that role-specific projections improve SWE performance, or
that task purity is more important than context length.

| Work | Relevant finding or motivation | Thaliris consequence |
| --- | --- | --- |
| Lost in Compaction / COMPINT | Free-form compaction can drop persistent side constraints. | Constraints have an independent structured retention channel; summaries are not correctness sources. |
| The Compaction Cliff / Knowledge Triage | Heterogeneous information can need different retention contracts. | Core uses existing semantic types with distinct invariants, not the paper's complete taxonomy. |
| SKILL.state | Validated explicit execution state can replace rolling history in a long-horizon runtime. | History/provenance is retained externally, then routed through evidence-backed task state and role projection. |
| Scroll: Context as an Environment | Available external history need not be serialized into active context. | Thaliris borrows existence-versus-exposure separation, not Scroll's persistent Python kernel. |
| Handoff Debt | Fresh successors can incur rediscovery cost when predecessor context is opaque. | Trajectory isolation retains useful artifacts and evidence; it does not mean minimizing handoff at all costs. |
| Harness-of-Harness | Versioned artifacts, bounded fresh invocations, and independent evaluation can coexist in an iterative harness. | Artifact/evidence continuity and verification boundaries are useful patterns; its multi-variable results are not attributed solely to task purity. |
| AutoCompact | Obsolete exploration history can interfere even before context capacity is exhausted. | Adjacent motivation only; Core does not implement learned or automatic compaction. |
| Adversarial Review | Structured, evidence-grounded disagreement can improve review protocols. | Motivation for evidence boundaries only; Core does not introduce a mandatory critic or review loop. |

### References

- Zhiqi Wang, Yichi Zhang, Dongwon Lee, and Yuchen Yang. *Lost in
  Compaction: Evaluating Side-Constraint Loss under Context Compaction*.
  arXiv:2608.11242, 2026. <https://arxiv.org/abs/2608.11242>
- Saber Zerhoudi, Jelena Mitrovic, and Michael Granitzer. *The Compaction
  Cliff in Long-Running AI Agent Memory*. arXiv:2608.22752, 2026.
  <https://arxiv.org/abs/2608.22752>
- Sanket Badhe, Priyanka Tiwari, and Jonghyun Chung. *SKILL.state: Scalable
  Long-Horizon Agent Skills*. arXiv:2608.26263v3, 2026 (arXiv lists it as
  accepted at EMNLP). <https://arxiv.org/abs/2608.26263>
- Yin Lin, Elaine Ang, Erkang Zhu, Bolin Ding, and Jingren Zhou. *Context as
  an Environment: Programmatic Context Management for Long-Horizon Agents*.
  arXiv:2608.21690, 2026. <https://arxiv.org/abs/2608.21690>
- Dipesh KC and Anjila Budathoki. *Handoff Debt: The Rediscovery Cost When
  Coding Agents Take Over Interrupted Tasks*. arXiv:2606.02875, 2026.
  <https://arxiv.org/abs/2606.02875>
- Haoyang Yan, Min-le Su, Hangfan Zhang, Zhanhao Li, Chen Zhang, Shao Zhang,
  Yang Chen, Lei Bai, and Shuyue Hu. *Harness-of-Harness: Multi-Day
  Autonomous Software Development with Continual Improvement*. arXiv:2609.01481,
  2026. <https://arxiv.org/abs/2609.01481>
- Xuan Zhang, Longtao Zheng, Cunxiao Du, Bo An, and Xin Dong. *AutoCompact:
  Learning When to Compact Context in Long-Horizon Coding Agents*. Public
  project page, accessed 2026-09-07. <https://autocompact.github.io/>
- Eric S. Qiu and Joyce Gill. *Adversarial Review: Structured Disagreement for
  Grounded Agentic Code Review*. arXiv:2608.18167, 2026.
  <https://arxiv.org/abs/2608.18167>

The working hypothesis for future benchmarks is narrower than a research
claim: competing cognitive objectives and role contamination may be an
important resource constraint for frontier reasoning models. Existing work
supports context interference, typed retention, structured state, selective
handoff, and evidence-grounded checking. It does not separately establish
`task purity > context length` or guarantee that Thaliris projections improve
software-engineering outcomes.

See [DESIGN.md](DESIGN.md) for Core invariants and persistence details.
