# Codex Adapter

This branch maps Codex runtime roles and lifecycle mechanisms onto the
runtime-neutral Thaliris Core. Codex role names are translated to semantic Core
roles by `src/thaliris/codex_adapter.py`. The adapter aliases are compatibility
profiles, not Codex-native semantic roles; Core never persists them.

`fork_turns="none"` cuts implicit parent-task-history propagation; it does not
mean an empty context. A fresh child still has applicable instructions, tools,
environment, and native delegation content. The child loads its own Core role
projection through the minimal bootstrap instruction. The Controller does not
preload child-only working material.

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
execution result. The adapter observes an authorized acceptance command only at
`PostToolUse`: an explicit native exit/tool-success fact becomes `PASSED` or
`FAILED`, while absent or incomplete completion payloads are `UNKNOWN` and do
not create trusted proof. It asks Core for the current target-bound surface and
lets Core record fresh native source identities atomically; a PreToolUse allow,
command string, summary, or locator is never a pass.

This bridge is configured for the explicit local execution matcher and covered
by payload-shape tests. It is not a universal Codex guarantee: a runtime build
without a compatible PostToolUse completion payload remains `UNKNOWN` in
`context doctor`, and targeted tasks fail closed at `task-close`.
