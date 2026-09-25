---
Evidence: RECORDED
Revision: 2
---

# Codex adapter lifecycle observations

This record keeps future decision-changing facts from the managed lifecycle work. It is not a task log.

## Source-verified

- Commits `44b9a84` through `45de489` on `adapter/codex` establish that global `codex-install` owns only the Thaliris-managed span in `CODEX_HOME/AGENTS`.
- Child messaging defaults to no ordinary progress; parent wakeups are for completion, blockers, or decision-changing information.

## Live-observed

- The current pinned executable supported proactive bootstrap for substantive work in a blank Git repository and the same-session ACTIVE bridge. Project initialization did not require a restart.
- One live managed Codex CLI `0.155.0-alpha.9.2` probe on 2026-09-25 verified the exact nested reservation, `SubagentStart`, and bound Scanner `PreToolUse` acceptance at depth two. The Scanner result returned and the Focused Implementer parent continued. This scope is limited to that one CLI build and probe.
- A `CHANGED` freshness result reflected changed evidence while the conclusion remained true. Treat `CHANGED` as evidence change, not semantic invalidation by itself.

## Open lifecycle boundary

- Raw Host wire-byte equality, other Host builds or Desktop scenarios, and native child `Completed`/`task-close` completion were not observed and remain UNKNOWN. Any task closure that requires native lifecycle completion remains gated until explicit `Completed` is observed.

## Evidence boundary

- The source claims above are traceable to commits `44b9a84` through `45de489` on `adapter/codex`.
- Durable evidence for the nested probe is [`docs/codex-nested-scanner-live-20260925.md`](../docs/codex-nested-scanner-live-20260925.md) from commit `67e7743`. Its provenance records Codex Desktop / `codex-cli 0.155.0-alpha.9.2`, Thaliris `0.4.0`, adapter protocol `9`, and source hashes for the probe streams, audits, result, and native rollouts while omitting private paths and IDs.
- Future reports should label source-verified, live-observed, and unknown facts separately.
