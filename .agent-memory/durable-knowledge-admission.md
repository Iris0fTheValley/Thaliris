---
Evidence: RECORDED
Revision: 2
---

# Durable knowledge admission and recovery

The Controller alone keeps private awareness of reusable-knowledge candidates as ordinary task evidence and results arrive. Near natural task end, it decides whether a concise, sourced entry would improve, constrain, or accelerate future decisions or recovery. The decision is not limited to information a future agent would otherwise need to rediscover.

Existing documentation, source, instructions, tests, commits, and rollout records are evidence: their presence neither rules out memory nor requires it. When selected knowledge has future value, memory can serve as a recovery entrance that links or summarizes canonical material, or preserves a decision basis spread across sources. Executors return their normal results; they do not maintain candidate lists or initiate Curator work. A selected Curator reconciles only the supplied candidates, evidence, and prior memory, preserving scope and provenance; an explicit no-write result is appropriate when the existing record is sufficient.

The root [INDEX](INDEX.md) is the Controller's semantic map for choosing which
durable records to read. When reconciling selected knowledge, Curator checks
its affected INDEX entry and updates it if needed. The canonical
responsibilities are described in the [routing protocol](../docs/thaliris-routing-protocol.md)
and [Curator role profile](../docs/thaliris-role-packs.md#curator).

This entry records the repository policy revision at commit `a15dc84` on `adapter/codex`. It is a reminder to assess future decision value even when canonical documentation exists; it does not make Curator a mandatory task stage. It describes repository policy and does not establish installed or active Host behavior.

## Canonical references

- [`AGENTS.md`](../AGENTS.md), “Thaliris Router” section.
- [`docs/thaliris-role-packs.md`](../docs/thaliris-role-packs.md), “Curator” and “Durable knowledge loop”; [`docs/thaliris-routing-protocol.md`](../docs/thaliris-routing-protocol.md) for broader role routing.
- [`roles.py`](https://github.com/Iris0fTheValley/Thaliris-Codex/blob/main/src/thaliris_codex/roles.py) and [`codex_adapter.py`](https://github.com/Iris0fTheValley/Thaliris-Codex/blob/main/src/thaliris_codex/codex_adapter.py), Codex role definitions and rendered policy.
