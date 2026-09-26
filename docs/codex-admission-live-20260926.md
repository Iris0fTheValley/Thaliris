# Live admission proof probe — 2026-09-26

This is a sanitized record of one local live probe. It records the observed
hook path and admission result without retaining a bearer token, prompt,
command body, or private machine path.

## Environment

- Codex CLI: `0.155.0-alpha.9.2`
- Managed hook ABI: `thaliris-hook-abi-10`
- Host hook configuration: 7 Thaliris hooks enabled and trusted in the saved
  Host configuration
- Target: a fresh disposable temporary Git repository
- Candidate source: loaded through process-local `PYTHONPATH`; no installed
  candidate package was substituted
- Evidence log path: `<redacted local temp path>/admission-evidence.jsonl`
- Evidence log SHA-256: `<redacted>`

## One-session sequence

One Host session made four distinct calls against the fresh repository:

1. `bootstrap-check` returned the canonical bridge data.
2. `init` created the project activation state.
3. A harmless `PreToolUse` call traversed the live hook and issued the
   admission bearer for that session payload.
4. `task-start` consumed the bearer with the bridge digest and returned
   `ACTIVE`.

A second consumption attempt was rejected, demonstrating one-shot local
   consumption. The report contains no bearer token or secret payload.

## Scope

The sequence demonstrates a real hook path and one-shot adapter state for this
CLI build, ABI, local user, and fresh repository. The bearer embeds a session
hash and is checked against a local record, bridge digest, ABI, and expiry. The
selected trust boundary includes local processes running as the same Windows
user, so another same-user process could replay the bearer while it remains
valid. This observation does not provide cryptographic Host provenance and
does not generalize to other Host builds, Desktop scenarios, or repositories.
