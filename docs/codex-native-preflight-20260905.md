# Codex native preflight — 2026-09-05

This is a bounded observation record, not a universal Codex permission claim.

## Environment

- Codex CLI: `0.153.0-alpha.5`
- Adapter: `9298358aad637d889f7f84e41b3ed748cc9f845c`
- Core ancestor: `62c405634bf7782c506cea262bd99b98f0de81ea`
- Thaliris: `0.3.0`
- Python: `3.11.9`

The probe used a disposable clone at the adapter commit. Its managed `AGENTS.md`,
project `.codex/hooks.json`, task state, audit files, and target file were never
created in a product checkout.

## Observed native surfaces

In a fresh session created after normal project-hook review/trust:

- the session record identified the probe clone's `AGENTS.md` and included the
  Thaliris Router instructions;
- `/hooks` reported one project-sourced, active Thaliris command hook for each
  configured event: `SessionStart`, `UserPromptSubmit`, `PreToolUse`,
  `PostToolUse`, and `Stop`;
- the current session observed `SessionStart`, `UserPromptSubmit`, and
  `PreToolUse` for the Thaliris handler;
- a root `context task-status` was allowed, while one root
  `git log -1 --oneline` and one root output-redirection write were denied by
  `THALIRIS_CONTROLLER_BOUNDARY`; the requested file was not created;
- the root's native `spawn_agent` call explicitly supplied `fork_turns="none"`;
- the fresh child self-ran `context prepare --role implementer`, completed, and
  returned a bounded report through native wait;
- the child made one nested `spawn_agent` attempt, which the current
  `PreToolUse` handler denied with `THALIRIS_CHILD_DELEGATION`; no nested child
  started.

The root/child identity conclusion is behavioral and intentionally avoids
persisting raw hook payloads: the root Controller guard is reached only when
`agent_id` is absent, while the child-delegation deny is reached only when it is
present. Both branches were observed in the same current native workflow.

## Scope limits

The root spawn hook capture exposed an encrypted delegation `message`, so this
probe does not attest plaintext payload fidelity. `PAYLOAD_FIDELITY` remains
`UNKNOWN`. Hosted, specialized, unknown-tool, and untested MCP surfaces remain
outside this local-hook enforcement envelope and are `UNKNOWN`.

`FULL_NATIVE_PREFLIGHT = OBSERVED PASS` applies only to the tested Codex
`0.153.0-alpha.5` native surfaces above.

## Later edge-case review

Subsequent source review identified untested enforcement edge cases around
cross-task dispatch evidence, unsafe fork rewriting, and arbitrary root shell
commands. Those are separate from the observations recorded above; the
historical probe remains valid for the native surfaces it explicitly exercised.

Later compatibility hardening changed the managed hook definition. Historical
observations do not attest to that new hook hash; a fresh native revalidation is
required before treating current-hook runtime evidence as observed.
