# Thaliris Core

Thaliris is a small, Git-native context-routing and bounded-retention core for
agent workflows. It provides a low-noise default projection for each semantic
role, records what remains retained without automatic propagation, and tracks
which evidence is fresh enough to support a claim.

The Core provides bounded task state and Controller packets, semantic role
projections, evidence freshness, external artifact pointers, project memory,
milestones, explicit durable promotion, and atomic CAS-backed persistence and
recovery.

Working set is not handoff set. Retention is not propagation. Availability is
not injection. Retained parent history, child transcripts, raw findings,
evidence registries, logs, tool output, memory bodies, and artifact contents do
not cross a role boundary automatically. They may remain available for an
explicit, model-selected follow-up, but only information deliberately selected
for propagation enters the next role's context.

Durable memory is retained, not injected. A model may explicitly run `context
recall "query" --role ROLE` to search routed, evidence-aware candidates. Recall
does not accept a candidate into task state or propagate it into any role pack;
the model selects whether to ignore it, explicitly accept it, or explicitly pass
it onward.

Thaliris constrains propagation paths, not the size or meaning of information a
model explicitly chooses to send. Core bounds protect persistent state,
snapshots, packets, promotion records, and other storage structures; they are
not a semantic payload quota or a handoff-size limit.

Core is runtime-neutral. It does not execute agents or define child creation,
hooks, wait semantics, transport, or session lifecycle. Runtime-specific
adapters map these projections to concrete runtimes. The Codex adapter is
maintained separately under `adapter/codex`; benchmark and evaluator assets are
maintained under `test/abcd-benchmark`.

See [DESIGN.md](DESIGN.md) for the topology and persistence invariants.
