# `wait_agent` payload evidence — 2026-09-26

## Source-verified contract

For Codex CLI `0.155.0-alpha.9.2`, the `wait_agent` tool result contains
`message` and `timed_out`. It does not contain a waited child ID, reservation
ID, or child status. The current `PostToolUse` payload also carries no target
identity for the wait.

## Live probe status

Two redacted live probe attempts failed to capture an authenticated
`wait_agent` `PostToolUse` payload. Live payload fidelity therefore remains
`UNKNOWN`; these attempts do not change child-completion reconciliation.
Returned wait text and `SubagentStop` are not native `Completed` status and
must not be treated as child completion.

Temporary evidence locations and hashes were not included with the available
probe summary, so this note records no paths or digests for those attempts.
