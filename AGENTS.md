## Thaliris Core

This repository contains the runtime-neutral Thaliris Core. Keep task state,
evidence, projections, artifacts, memory, milestones, and durable promotion
bounded and evidence-backed.

Working set is not handoff set. Retained information is not automatically
propagated. Use `context task-status` for bounded Controller routing and
`context task-show` only for explicit diagnostics. Artifact contents are
external to normal role packs.

Runtime-specific lifecycle and agent instructions belong in adapter branches,
not in this Core instruction file.
