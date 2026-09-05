# Thaliris Core

Thaliris is a small, Git-native context-routing and bounded-retention core for
agent workflows. It decides which information belongs in each semantic role,
what remains retained without automatic propagation, and which evidence is
fresh enough to support a claim.

The Core provides bounded task state and Controller packets, semantic role
projections, evidence freshness, external artifact pointers, project memory,
milestones, explicit durable promotion, and atomic CAS-backed persistence and
recovery.

Working set is not handoff set. Retention is not propagation. Normal packets do
not include raw findings, review bodies, evidence registries, logs, transcripts,
source dumps, or artifact contents.

Core is runtime-neutral. It does not execute agents or define child creation,
hooks, wait semantics, transport, or session lifecycle. Runtime-specific
adapters map these projections to concrete runtimes. The Codex adapter is
maintained separately under `adapter/codex`; benchmark and evaluator assets are
maintained under `test/abcd-benchmark`.

See [DESIGN.md](DESIGN.md) for the topology and persistence invariants.
