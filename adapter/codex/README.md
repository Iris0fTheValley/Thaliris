# Codex Adapter

This branch maps Codex runtime roles and lifecycle mechanisms onto the
runtime-neutral Thaliris Core. Codex role names are translated to semantic Core
roles by `src/thaliris/codex_adapter.py`. The adapter aliases are compatibility
profiles, not Codex-native semantic roles; Core never persists them.

`fork_turns="none"` is a Thaliris isolation policy that overrides Codex's
history-fork default. It cuts implicit parent-task-history propagation; it does
not mean an empty context. A fresh child still has applicable instructions,
tools, environment, and native delegation content. `SubagentStart` is the
managed projection boundary: the adapter maps the native profile to a Core role
and returns that bounded role projection as hook `additionalContext` with
`additionalContextLimit = 0`, so Codex does not impose a second opaque
truncation. The
Controller never receives child-only projections. `child_bootstrap()` remains a
manual/legacy fallback, not the managed correctness path.

Semantic and CLI aliases are not native spawn authority. Managed
`spawn_agent` accepts only the supported native values `explorer`, `worker`,
and the five `thaliris-*` profiles. Init/doctor report profile definition
presence separately from native profile activation and project-layer
activation; an installed `.codex` file does not prove that the current session
trusted or loaded it.
The compatibility field `hook_trust_required` is only a hook-definition change
trigger. Profile or instruction changes can still set
`session_restart_required` without implying that hook trust is required; neither
field claims anything about the current session's trust state.

Hooks cover only known local native surfaces. During an ACTIVE task the root
Controller is denied on matched `mcp__*` tools as well as guarded local shell
and mutation paths; children are not given that root allowlist. Hosted,
specialized, and unverified surfaces remain outside this enforcement envelope.
Configuration, current hook-definition observation, payload fidelity, and
runtime identity compatibility remain `UNKNOWN` without compatible live
evidence. This is not filesystem confidentiality. Role packs are default
context guidance, not semantic firewalls: the model explicitly selects
decision-relevant facts, constraints, contradictions, unknowns, artifact
pointers, or other necessary detail for each handoff. Explicitly selected large
payloads remain valid; raw working-set material is never propagated
automatically. Artifact pointers provide selective access, not mandatory
compression.

Core v5 distinguishes an ordinary model-authored test report from an observed
execution result and binds a trusted result to the target and current Core
surface identity. An allowed root `spawn_agent(fork_turns="none")` for a
supported Thaliris profile creates one bounded pending authorization scoped to
the active task, semantic role, native `agent_type`, and shared session hash.
The managed lifecycle is
`authorized reservation -> matching SubagentStart -> Core projection emitted
successfully -> matching session/turn/type SubagentStop -> persisted completion`.
Unknown or
mismatched starts remain observations and receive no projection. A pending
reservation and every started managed child are in flight, so managed dispatch
remains serial until the child reaches a terminal execution state. `SubagentStop`
remains the preferred completion proof. `NATIVE_CHILD_COMPLETION_REENTERS_ROOT`
is a Host capability, not an unconditional product claim: only `PASS` selects
EVENT_DRIVEN mode; `UNSUPPORTED` and `UNKNOWN` select configured,
host-bounded BLOCKING_WAIT mode when available. A timeout permits one status
observation, then another long wait only while the child is still running.
Thaliris provides no supervisor, deadline, scheduler, or polling loop. Stop
proves lifecycle completion, not work correctness. A projection-ready child is
not a claim that the native child confirmed receipt.

The current trusted shell candidate is exactly Codex stable `Bash`. Codex CLI
0.153.4 does not document a terminal exit/status field in its Bash PostToolUse
payload, so every such shell outcome remains unavailable for attestation. A
PreToolUse allow,
command string, summary, locator, formatted output, generic `status`, or
generic `success` is never a pass. The adapter can record a `PASSED` only if a
future version-pinned Codex contract supplies an explicit terminal-result fact.
Core binds such a result to the target fingerprint and Core-computed current
surface identity, including deleted files and symlinks. Until then the adapter
records only a bounded diagnostic observation and does not mutate Core
verification state.

Automatic acceptance execution applies only to an executable string target
accepted by the local command allowlist. A structured Core target is still a
Core requirement, not a shell command, and needs another trusted runtime
observation path.

Historical aliases (`Shell`, `exec`, `exec_command`, and similar) remain
diagnostic observations only and cannot enter Core's trusted verification
ingress. Doctor reports definition presence, current-protocol observation,
lifecycle/projection observations, the trusted shell surface, and terminal
status availability separately. A configured hook file is not proof that the
current Codex session loaded or trusted it. Historical compatible observations
do not prove current-session readiness, which remains `UNKNOWN` until a
matching hook-spec and adapter protocol are observed in that session.

In the recorded Codex CLI 0.153.4 protocol-3 probe, a requested fresh child did
not report the Core-only projection sentinel and no adapter hook observation was
written. That invocation is therefore `NOT_OBSERVED`, not evidence that
SubagentStart projection delivery is active. See
[`docs/codex-native-probe-20260908.md`](../../docs/codex-native-probe-20260908.md).

A Protocol 4 disposable-session probe on the same Codex build requested the
`thaliris-investigator` profile with `fork_turns="none"` and a bounded marker.
The native runtime rejected that `agent_type` as unknown before a child
started, so no `SubagentStart`/`SubagentStop` or marker observation was
recorded. The result remains `NOT_OBSERVED`; generated profile presence and
synthetic hook tests are not native projection proof.

Codex CLI `0.153.4` has a release-pinned 10 s / 30 s / 1 h V2 wait
minimum/default/maximum and supports trusted project `.codex/config.toml`.
The adapter conservatively sets only a missing project
`default_wait_timeout_ms` to that Host maximum; a conflicting user value is
left untouched and makes BLOCKING_WAIT unavailable. The same release sends
child-completion communication with `trigger_turn=false`, so
`NATIVE_CHILD_COMPLETION_REENTERS_ROOT = UNSUPPORTED` unless a fresh Host probe
records stronger evidence. A native terminal status observed through the
identity-bound `interrupt_agent` or `list_agents` PostToolUse result can release
the serial execution slot as `NATIVE_TERMINAL_RECONCILED`; it never counts as a
successful child result. `not_found` is `ORPHANED`, not completion. Repeated
blocked spawn attempts with no lifecycle change stop at `ORCHESTRATION_STALLED`.
The local version-bound evidence and the deliberately limited native probe are
recorded in [`docs/codex-host-capability-20260912.md`](../../docs/codex-host-capability-20260912.md).
