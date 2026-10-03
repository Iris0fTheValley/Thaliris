<!-- thaliris-role-registry:v1 -->
# Thaliris Role Registry

This file is generated from `thaliris.roles.ROLE_REGISTRY`; design and routing guidance remains hand-maintained in `thaliris-role-packs.md`.

| Role | Model | Reasoning | Native profile | Repo writes | Delegation | Controller-state mutation | Install metadata |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `controller` | `gpt-5.6-sol` | `(host/task)` | `(root)` | NO | YES | YES | `(not generated)` |
| `investigator` | `gpt-5.6-luna` | `xhigh` | `thaliris-investigator` | YES | NO | NO | `thaliris-investigator.toml` |
| `curator` | `gpt-5.6-luna` | `xhigh` | `thaliris-curator` | YES | NO | NO | `thaliris-curator.toml` |
| `reasoning-specialist` | `gpt-5.6-sol` | `xhigh` | `thaliris-reasoning-specialist` | YES | NO | NO | `thaliris-reasoning-specialist.toml` |
| `implementer` | `gpt-5.6-luna` | `xhigh` | `thaliris-implementer` | YES | NO | NO | `thaliris-implementer.toml` |
| `verifier` | `gpt-5.6-luna` | `xhigh` | `thaliris-verifier` | NO | NO | NO | `thaliris-verifier.toml` |
| `reviewer` | `gpt-5.6-terra` | `high` | `thaliris-reviewer` | NO | NO | NO | `thaliris-reviewer.toml` |
