# Codex Adapter

This branch maps Codex runtime roles and lifecycle mechanisms onto the
runtime-neutral Thaliris Core. Codex role names are translated to semantic Core
roles by `src/thaliris/codex_adapter.py`.

`fork_turns="none"` means no inherited parent-thread history; it does not mean
an empty context. A fresh child still has applicable instructions, tools,
environment, and native delegation content. The child loads its own Core role
projection through the minimal bootstrap instruction. The Controller does not
preload child-only working material.

Hooks cover only known native surfaces. Configuration, session observation,
payload fidelity, root classification, and semantic task delivery remain
`UNKNOWN` without compatible live evidence. Unknown tools and unverified MCP
paths fail open.
