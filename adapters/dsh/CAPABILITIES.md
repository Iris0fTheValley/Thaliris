# DSH capability map

Source baseline: DeepSeek Harness `639ed015397290b3745d163aafe02ffee4aa3f84`
(`0.2.0-rc.2`). Paths below refer to that repository.

| Requirement | Native surface | Adapter action |
| --- | --- | --- |
| Out-of-tree loading and unload | `vendor/loader/src/config/tree.ts` `create/update/remove`, Cordis effects | REUSE module URL/profile entry and fiber cleanup |
| Calling Controller | `packages/core/tools/src/index.ts` `ToolRunContext.agent`; `packages/core/agent/src/index.ts` `get/roots` | REUSE exact live Agent and native ownership; bind root object and durable native ID |
| Model guidance | `packages/core/system-prompt/src/index.ts` `section/getSectionOrder`; `packages/core/agent/src/runtime-types.ts` `AssembleContext.agent`; `packages/subagent/subagent/src/child-agent.ts` `persona` | REUSE dynamic root-only Controller section and native child persona; no second prompt assembler |
| Fresh child | `packages/subagent/subagent-spawn-in-process/src/index.ts` `inheritsParentContext = false`; `subagent/src/child-agent.ts` | REUSE `ctx.subagents.start`; reject seeding/remote providers |
| Route and tool scope | `subagent/src/types.ts` `agentOptions`, `persona`, `toolFilter`, `maxDepth` | REUSE configured role map and explicit allowlist; deny Controller tools again in their bodies |
| Identity, outcome and cleanup | `subagent/src/types.ts` `SubagentRun.id/localAgent/result/dispose` | REUSE native result/status; no parsing child prose for lifecycle |
| Python process | `packages/subprocess/subprocess/src/types.ts` spawn spec, collection and managed exit | REUSE `ctx.subprocess`; one bounded JSON request/response |
| Task intent and ledger | Thaliris `src/thaliris/authority.py` and `core.py` | NEED BRIDGE to the same Python Core, with explicit source/interpreter/external store |

No replacement Agent loop, tool pipeline, subagent manager, identity service,
Host installation, automatic semantic router or benchmark evaluator is needed.
The bridge adds serialization only. The Controller selects intent, Workstream,
role, context and completion; native status is an observation.
