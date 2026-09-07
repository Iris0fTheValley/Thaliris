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

Core v3 distinguishes an ordinary model-authored test report from an observed
execution result. The current Codex hook audit records dispatch and policy
events, not trustworthy test outcomes or native source identities, so it does
not create Core verification attestations. A future Codex execution-observer
bridge must submit an observed `PASSED`/`FAILED`/`UNKNOWN` result through the
non-CLI Core registration boundary with fresh source references. Until then,
tasks with a Core verification target fail closed at `task-close`; a command
string or hook permission is not proof that the command succeeded.
