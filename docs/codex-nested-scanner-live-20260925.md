# Live nested Scanner probe evidence — 2026-09-25

This is a sanitized record of one local Codex Desktop probe. It preserves the observed sequence and source hashes so the claim remains reviewable in this repository even if the temporary probe directory is removed. It does not contain native thread IDs, task IDs, messages, or absolute machine paths.

## Provenance

- Observation date: 2026-09-25, 10:43–10:46 UTC. Evidence retrieved locally at 11:41 UTC.
- Host: Codex Desktop / `codex-cli 0.155.0-alpha.9.2` (native rollout `session_meta`); Thaliris `0.4.0`, adapter protocol `9` (runtime audit).
- Target repository identity: SHA-256 of this repository's canonical workspace path, UTF-8: `63c37feec487b4ab89a96d21a427cd24925f938fb7830f09f17074125ec69750`. The probe ran in a separate temporary workspace.
- Probe identity: SHA-256 of the temporary probe directory name, UTF-8: `13d06778571a57ed4c3e1f1478d68a019d07d6f1f79e3f14debfaf6c9270d894`. These hashes are correlation labels, not authentication.
- Publishers: Codex CLI wrote the event streams and native rollouts; the Thaliris Codex adapter wrote the runtime and lifecycle audit; the probe wrote `probe-result.txt`.
- Retrieval locations: the probe sources were read from a local temporary `thaliris_nested_probe_<redacted>` directory; native rollouts were read under `$CODEX_HOME/sessions/2026/09/25/`. The table hashes identify the exact files without retaining private paths or IDs.

| Source (local, outside this repository) | SHA-256 |
| --- | --- |
| Probe `codex-events.jsonl` | `109c8452d519e3b1abf54ac71d07b399b11002dd4d3e503ee5647bbd047111f8` |
| Probe `codex-events-resume.jsonl` | `0a9002146c4612442a4647e699a50aef079007224ce9fd5bd40135fef5a1be5d` |
| Probe `.context/audit/*/runtime.json` | `e141c046275a953edb8d1b35edbdc0fa717584bafa49a6d14709752a70bf7ecb` |
| Probe `.context/audit/lifecycle/*.json` | `aaaa8d9ced749c940f8d79fb738f9699f7d7a6551c0e5864cefdd95030173708` |
| Probe `probe-result.txt` | `98a640c91e5a8b41530b219eb12f4a8f10b1767b118b261ce1b0291ac83caece` |
| Root native rollout | `da337998016c557f150b343c009ce4d88591863c19ea9a392ce0af20332d79cd` |
| Focused Implementer native rollout | `b754954270f5b5d1146f05b57261b0b2084dee34f0990e60c8004d66127c402a` |
| Scanner native rollout | `d7fe1b870d455728d49ff71b2581bad762cd673f9f803ef22a83419629f72984` |

## Selected observations

1. The root native rollout records a `spawn_agent` call for `thaliris-focused-implementer` with `fork_turns: "none"` (line 74). The lifecycle audit records its depth-1 handoff created at 10:45:15 UTC, bound, and started at observation sequence 2.
2. The Focused Implementer native rollout records exactly one nested `spawn_agent` call for `thaliris-investigator`, task name `scanner`, with `fork_turns: "none"` (line 13). The lifecycle audit records its depth-2 handoff created at 10:45:24 UTC, bound, and started at sequence 4.
3. The runtime audit records `SubagentStart` and `PreToolUse` events, two child start hashes, and two PreToolUse child hashes. Both lifecycle child agent hashes occur in the PreToolUse set. The lifecycle audit records Scanner stop at sequence 5 and Focused Implementer stop at sequence 6; both terminal states are `STOP_ATTESTED`.
4. The Scanner native rollout has a `task_complete` event (line 24) reporting one nonce match in `payload/right/match.txt`. The nonce's SHA-256, UTF-8, is `d7e7c00b7b10066f037596a7d54bf84404680db0dc758c02d6d7936e15094a19`. The probe result file contains that relative match path followed by the Focused Implementer continuation marker using the same nonce. The Focused Implementer native rollout records its continuation in the final message (line 53); the resumed CLI event stream also records that continuation (line 11) and `turn.completed` (line 12).

## Limits

- The native rollouts contain turn `task_complete` events and native waits returned `"Wait completed."`; the lifecycle audit nevertheless records `native_terminal_status: null` for both children. These sources do not establish an explicitly observed native **Completed** child status for managed lifecycle completion.
- The native rollout arguments and adapter audit correlate the nested spawn and bound child identity. They do not prove byte-for-byte equality of raw Host tool wire input, hook input, or serialized payloads.
- This is one local probe, not evidence that nested spawning works in every session, Host version, or workspace. The runtime audit reports `HOST_ROLE_CATALOG_UNKNOWN`.
