# Thaliris Core

Thaliris is a small, Git-native, evidence-backed context-routing and memory
core for agent workflows. It provides low-noise role projections, retains
useful task state and provenance, and keeps evidence freshness visible without
turning retained history into automatic context.

The Core provides bounded task state and Controller packets, semantic role
projections, artifact pointers, durable memory, milestones, explicit durable
promotion, and atomic CAS-backed persistence and recovery.

## Why Thaliris

**Thaliris** combines **Thalamus** and **Iris**. The thalamus filters and
routes information entering cognition; the iris regulates how much reaches the
field of view. Thaliris applies that metaphor to reasoning paths: retain
important evidence and state, route what is useful to the current role, and
isolate unrelated working sets without pretending useful history vanished.

Working set is not handoff set. Retention is not retrieval. Retrieval is not
propagation. Availability is not injection.

Retained parent history, child transcripts, raw findings, evidence registries,
logs, memory bodies, and artifact contents do not cross a role boundary by
default. A fresh child or role is not blank: it receives the facts,
constraints, evidence, and state selected for its current task, rather than an
entire predecessor trajectory.

Durable memory is retained, not injected. A model may explicitly run
`context recall "query" --role ROLE` to retrieve routed, evidence-aware
candidates. Recall neither accepts a candidate into task state nor propagates
it into a role pack; the model explicitly selects what to use next.

Thaliris controls which information enters which reasoning path. It does not
mechanically minimize handoff size, impose a semantic payload quota, or replace
relevance judgement with a fixed context budget. An explicitly selected payload
may be large when correctness needs it.

## Core And Adapters

Core is runtime-neutral. It does not execute agents, define hooks, run shell
commands, or know model/runtime aliases. Runtime adapters map the Core's
evidence and projection contracts to concrete environments. Codex support is
maintained separately on `adapter/codex`; it is not part of Core itself.

Verification targets are requirements, not shell authority. Model-authored
test text is only a claim; a close gate requires a trusted runtime observation
that is bound to the current target, current source identities, and the task's
attributable changed surface. Core records and checks that contract but does
not claim to prove arbitrary commands itself.

## Research Influences

These works motivate design choices around side-constraint retention, typed
state, externalized context, handoff continuity, context interference, and
evidence-grounded checking. They do not prove Thaliris, establish that task
purity outweighs context length, or guarantee role projections improve SWE
performance; those remain benchmark hypotheses.

- [*Lost in Compaction: Evaluating Side-Constraint Loss under Context Compaction*](https://arxiv.org/abs/2608.11242) (COMPINT)
- [*The Compaction Cliff in Long-Running AI Agent Memory*](https://arxiv.org/abs/2608.22752) (Knowledge Triage)
- [*SKILL.state: Scalable Long-Horizon Agent Skills*](https://arxiv.org/abs/2608.26263)
- [*Context as an Environment: Programmatic Context Management for Long-Horizon Agents*](https://arxiv.org/abs/2608.21690) (Scroll)
- [*Handoff Debt: The Rediscovery Cost When Coding Agents Take Over Interrupted Tasks*](https://arxiv.org/abs/2606.02875)
- [*Harness-of-Harness: Multi-Day Autonomous Software Development with Continual Improvement*](https://arxiv.org/abs/2609.01481)
- [*AutoCompact: Learning When to Compact Context in Long-Horizon Coding Agents*](https://autocompact.github.io/)
- [*Adversarial Review: Structured Disagreement for Grounded Agentic Code Review*](https://arxiv.org/abs/2608.18167)

See [DESIGN.md](DESIGN.md) for state, evidence, verification, Git-surface,
migration, and persistence invariants.
