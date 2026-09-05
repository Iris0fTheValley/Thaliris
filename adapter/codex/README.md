# Codex Adapter

This branch maps Codex runtime roles and lifecycle mechanisms onto the
runtime-neutral Thaliris Core. Codex role names are translated to semantic Core
roles by `src/thaliris/codex_adapter.py`. The adapter aliases are compatibility
profiles, not Codex-native semantic roles; Core never persists them.

`fork_turns="none"` means no inherited parent-thread history; it does not mean
an empty context. A fresh child still has applicable instructions, tools,
environment, and native delegation content. The child loads its own Core role
projection through the minimal bootstrap instruction. The Controller does not
preload child-only working material.

Hooks cover only known local native surfaces. During an ACTIVE task the root
Controller is denied on matched `mcp__*` tools as well as guarded local shell
and mutation paths; children are not given that root allowlist. Hosted,
specialized, and unverified surfaces remain outside this enforcement envelope.
Configuration, current hook-definition observation, payload fidelity, and
runtime identity compatibility remain `UNKNOWN` without compatible live
evidence. This is not filesystem confidentiality.
