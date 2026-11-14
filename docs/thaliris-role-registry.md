<!-- thaliris-role-registry:v1 -->
# Thaliris Role Registry

Generated from `thaliris_codex.roles.ROLE_REGISTRY`. Role prompts are canonical in `roles.py`; project routing and mechanical design are documented separately. `thaliris-role-packs.md` is generated from the same role source.

| Role | Default model | Default reasoning | Native profile | Repo writes | Delegation | Controller-state mutation | Install metadata |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `controller` | `(host/user)` | `(host/task)` | `(root)` | NO | registered native roles | YES | `(not generated)` |
| `investigator` | `(host/user)` | `(host/task)` | `thaliris-investigator` | YES | NO | NO | `thaliris-investigator.toml` |
| `curator` | `(host/user)` | `(host/task)` | `thaliris-curator` | YES | NO | NO | `thaliris-curator.toml` |
| `reasoning-specialist` | `(host/user)` | `(host/task)` | `thaliris-reasoning-specialist` | YES | NO | NO | `thaliris-reasoning-specialist.toml` |
| `implementer` | `(host/user)` | `(host/task)` | `thaliris-implementer` | YES | investigator | NO | `thaliris-implementer.toml` |
| `focused-implementer` | `(host/user)` | `(host/task)` | `thaliris-focused-implementer` | YES | investigator | NO | `thaliris-focused-implementer.toml` |
| `verifier` | `(host/user)` | `(host/task)` | `thaliris-verifier` | NO | NO | NO | `thaliris-verifier.toml` |
| `reviewer` | `(host/user)` | `(host/task)` | `thaliris-reviewer` | NO | investigator | NO | `thaliris-reviewer.toml` |

Controller-only exceptional native profiles (same stable role IDs; defaults above remain unchanged):

- `thaliris-reasoning-specialist-astra-medium` → `reasoning-specialist`: `gpt-6-astra`, `medium`; `thaliris-reasoning-specialist-astra-medium.toml`.
- `thaliris-reasoning-specialist-xhigh` → `reasoning-specialist`: `gpt-6-astra`, `xhigh`; `thaliris-reasoning-specialist-xhigh.toml`.
- `thaliris-focused-implementer-astra-medium` → `focused-implementer`: `gpt-6-astra`, `medium`; `thaliris-focused-implementer-astra-medium.toml`.
- `thaliris-focused-implementer-xhigh` → `focused-implementer`: `gpt-6-astra`, `xhigh`; `thaliris-focused-implementer-xhigh.toml`.
