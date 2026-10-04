---
Evidence: NONE
Revision: 4
Status: DRAFT
Applicability: PROJECT
Confidence: UNVERIFIED
Kind: MEMORY
Audience: ["all"]
Topics: []
Symbols: []
---

# Durable memory index

- [Durable knowledge admission and recovery](durable-knowledge-admission.md) — Current
  project policy for deciding whether reusable knowledge merits memory and how
  the Controller and Curator use INDEX navigation; read when evaluating
  durable-memory candidates or selecting recovery documents.
- [Codex adapter lifecycle observations](codex-adapter-lifecycle.md) — Historical
  source-verified and live notes on adapter installation, child wakeups,
  bootstrap, and lifecycle probes; useful for compatibility or recovery. The
  nested Scanner probe is one Codex Desktop / CLI `0.155.0-alpha.9.2` run; the
  bootstrap / ACTIVE-bridge note gives no Host/build identifier. Other Host
  builds, Desktop scenarios, raw Host wire-byte equality, and native child
  `Completed`/`task-close` completion remain unknown.
- [Prompt policy](prompt-policy.md) — Current, source-verified Focused
  Implementer endpoint, Controller handoff, and independent review/repair
  boundaries; read when setting a semantic stopping point, preparing an
  implementation handoff, or routing a bounded correction. It supersedes
  earlier weaker endpoint wording. Core guidance is at commit `99ff867` and
  Codex adapter source at `9cce14c`; active native installation or activation
  is not established.
- [Operator notes](operator.md) and [project conventions](project-conventions.md)
  — Original draft placeholders; operating constraints and conventions remain
  unconfirmed.
- [Decision index](decisions/INDEX.md) and [lessons index](lessons/INDEX.md) —
  Unadopted templates, not project decisions or historical failure claims.
