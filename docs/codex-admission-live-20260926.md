# Live admission proof probe — 2026-09-26

This is a sanitized record of one local live probe. It records the observed
hook path and admission result without retaining a bearer token, prompt,
command body, or private machine path.

## Environment

- Codex CLI: `0.155.0-alpha.9.2`
- Candidate Thaliris version: `0.4.0`
- Managed hook ABI: `thaliris-hook-abi-10`
- Host hook configuration: `hooks/list` returned seven Thaliris handlers;
  all seven were enabled and had `trustStatus: trusted` (read-only check)
- Target: a fresh disposable Git repository
- Candidate source: loaded through process-local `PYTHONPATH` inherited by the
  pinned executable; no installed candidate package was substituted
- Live session hash: `4089ce021430a393503b219496bfeb5ffa572217a00b5073c1eafdde379cd59a`
- Init bridge SHA-256: `57c6f9d834242eaffc78f607825b606d8fa5922fc9d0fed55fdce787d1da1d9e`
- Evidence path: `<redacted local temp path>/.context/audit/<session-hash>/runtime.json`

## One-session sequence

One Host `codex exec` session made exactly three relevant shell calls against
the fresh repository, in this order:

1. `bootstrap-check` returned `ok: true` and the canonical bridge data.
2. `init` returned `ok: true` and created the project activation state. The
   same successful init Host result delivered `PostToolUse` `additionalContext`
   containing the one-shot admission proof.
3. The first `task-start` passed that proof and the init bridge digest and
   returned `status: ACTIVE` with no error.

No manual `audit-hook` call or harmless intermediary shell call was made. The
bearer token is intentionally omitted from this report and from retained
evidence.

The runtime observation record contains two Bash PostToolUse observations
after activation (init and task-start), with the expected candidate adapter
protocol version and session hash.

## Scope

This demonstrates the direct-init PostToolUse admission path and one-shot
adapter state for this CLI build, hook ABI, local user, candidate source
import path, and fresh repository. The bearer embeds the current session hash
and is checked against a local record, bridge digest, ABI, expiry, and one-time
consumption. The selected trust boundary includes local processes running as
the same Windows user, so another same-user process could replay the bearer
while it remains valid. This observation does not provide cryptographic Host
provenance and does not generalize to other Host builds, Desktop scenarios,
or repositories.
