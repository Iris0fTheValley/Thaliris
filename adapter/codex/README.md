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
and returns that bounded role projection as hook `additionalContext`. The
Controller never receives child-only projections. `child_bootstrap()` remains a
manual/legacy fallback, not the managed correctness path.

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

Core v4 distinguishes an ordinary model-authored test report from an observed
execution result. `spawn_agent` PostToolUse only records dispatch observation;
`SubagentStart` followed by matching `SubagentStop` is the lifecycle condition
for acceptance and `task-close`. Stop proves lifecycle completion, not work
correctness. Managed root children are serial while a started child remains
unstopped.

The current trusted shell candidate is exactly Codex stable `Bash`. Codex CLI
0.153.4 does not document a terminal exit/status field in its Bash PostToolUse
payload, so every such shell outcome remains `UNKNOWN`. A PreToolUse allow,
command string, summary, locator, formatted output, generic `status`, or
generic `success` is never a pass. The adapter can record a `PASSED` only if a
future version-pinned Codex contract supplies an explicit terminal-result fact.
Core then binds the result to the target fingerprint and Core-computed current
surface identity, including deleted files and symlinks.

Automatic acceptance execution applies only to an executable string target
accepted by the local command allowlist. A structured Core target is still a
Core requirement, not a shell command, and needs another trusted runtime
observation path.

Historical aliases (`Shell`, `exec`, `exec_command`, and similar) remain
diagnostic observations only and cannot enter Core's trusted verification
ingress. Doctor reports definition presence, current-protocol observation,
lifecycle/projection observations, the trusted shell surface, and terminal
status availability separately. A configured hook file is not proof that the
current Codex session loaded or trusted it. Current native observation remains
`UNKNOWN` until it is seen under the matching hook-spec and adapter protocol.
