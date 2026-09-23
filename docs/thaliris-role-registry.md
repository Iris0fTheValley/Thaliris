<!-- thaliris-role-registry:v1 -->
# Thaliris Role Registry

This file is generated from `thaliris.roles.ROLE_REGISTRY`; design and routing guidance remains hand-maintained in `thaliris-role-packs.md`.

| Role | Model | Reasoning | Native profile | Repo writes | Delegation | Controller-state mutation | Install metadata |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `controller` | `(host/user)` | `(host/task)` | `(root)` | NO | registered native roles | YES | `(not generated)` |
| `investigator` | `gpt-6-luna` | `xhigh` | `thaliris-investigator` | YES | NO | NO | `thaliris-investigator.toml` |
| `curator` | `gpt-6-luna` | `xhigh` | `thaliris-curator` | YES | NO | NO | `thaliris-curator.toml` |
| `reasoning-specialist` | `gpt-6-sol` | `high` | `thaliris-reasoning-specialist` | YES | NO | NO | `thaliris-reasoning-specialist.toml` |
| `implementer` | `gpt-6-luna` | `xhigh` | `thaliris-implementer` | YES | investigator | NO | `thaliris-implementer.toml` |
| `focused-implementer` | `gpt-6-sol` | `high` | `thaliris-focused-implementer` | YES | investigator | NO | `thaliris-focused-implementer.toml` |
| `verifier` | `gpt-6-luna` | `xhigh` | `thaliris-verifier` | NO | NO | NO | `thaliris-verifier.toml` |
| `reviewer` | `gpt-6-sol` | `high` | `thaliris-reviewer` | NO | investigator | NO | `thaliris-reviewer.toml` |

Controller-only exceptional native profiles (same stable role IDs; defaults above remain unchanged):

- `thaliris-reasoning-specialist-astra-medium` → `reasoning-specialist`: `gpt-6-astra`, `medium`; `thaliris-reasoning-specialist-astra-medium.toml`.
- `thaliris-reasoning-specialist-xhigh` → `reasoning-specialist`: `gpt-6-astra`, `xhigh`; `thaliris-reasoning-specialist-xhigh.toml`.
- `thaliris-focused-implementer-astra-medium` → `focused-implementer`: `gpt-6-astra`, `medium`; `thaliris-focused-implementer-astra-medium.toml`.
- `thaliris-focused-implementer-xhigh` → `focused-implementer`: `gpt-6-astra`, `xhigh`; `thaliris-focused-implementer-xhigh.toml`.
