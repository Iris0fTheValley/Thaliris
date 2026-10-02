# Shared client contract

The shared Web/Desktop client is the `@thaliris/dsh-plugin/client` entry. It uses one native Plugins-page item, ConfigForms, native model and tool catalogs, native Workspace and Session projections, and the native Plugin Manager. A client view is a projection; it cannot replace Core/native records or imply completion.

## Native configuration

The bundle runtime entry ID is `thaliris`. Custom deployments may choose another ID; find its namespace in `remote.settings.describe()`. Its Config has one live field, `policy`. Python/Core/authority paths and provider/timeout deployment settings are ordinary native plugin configuration and absent from the live Settings form.

`ctx.configForms.get<{ policy: UserPolicy }>('thaliris')` returns the native form. Use `getSnapshot()`, `subscribe()` and `mutate(ops, expectedRevision?)`. The native form serializes writes and supplies the latest Settings revision; a stale fixed revision is refused. Example atomic role edit:

```ts
await form.mutate([
  { op: 'set', path: ['policy', 'roles', '0', 'name'], value: 'My implementer' },
  { op: 'set', path: ['policy', 'roles', '0', 'prompt'], value: editedFullPrompt },
])
```

For deletion/duplication/reordering, write the complete selected `policy.roles` array (with unique IDs for duplicates). Explicit `[]` is legal and persists. Do not unset the roles field to delete all roles: native unset re-inherits the composition templates. Adding a template explicitly stores a copied record; templates are not active hidden roles. No prompt suffix is applied by the runtime. Default schema roles are empty; the installation composition stores initial templates.

Paths and defaults:

| Path | Shape/default |
|---|---|
| `policy.controllerPrompt` | Visible editable Controller guidance string |
| `policy.workspaces` | `[{workspaceId, root, enabled}]`, default `[]`; exact native ID/canonical Git root |
| `policy.roles` | Full `RoleRecord[]`; schema default `[]`; bundle initial templates |
| `role.id/name/description/prompt/enabled` | User-editable identity/display/full prompt; enabled defaults true |
| `role.tools` | Explicit native tool allowlist, default `[]` |
| `role.modelPolicy` | `{mode:'inherit'|'fixed'|'allowed',routes:[{provider,model,reasoningEffort?}]}`; inherit, empty routes |
| `role.memory` | `{read:[providerId],write:[providerId]}`, both empty |
| `role.context` | `{handoff:true,memory:false}` |
| `policy.memory` | `{mode:'disabled',autoAuthorized:false,providers:[],controllerRead:[],controllerWrite:[]}` |

Full public types are exported from `@thaliris/dsh-plugin/remote`. Native ConfigForms distinguishes writable Host mode from process-local memory mode on a non-loopback client. Honor that native state; do not label a process-local preference as a persisted grant. The explicit native `remote.settings.update/replace/mutate` API takes namespace, patch/ops and expected revision. Do not add another settings storage/API. `settings/document-updated` and `connection/reset` already refresh ConfigForms.

For model choices, reuse `ctx.remote.session.modelCatalog()` as the native subagent settings controller does. It returns the native `RemoteResult<ModelCatalog>` envelope: store `response.value` only when `response.ok` is true, and treat a failed result as an unavailable catalog. The initial projection has no catalog until this request succeeds. Join stored allowed routes with current native catalog facts; a previously stored route may be unavailable. Thaliris validates exact route metadata/capabilities at launch, does not rank models, create a model registry or modify user preferences. For workspaces, use the existing native `remote.workspace` projection/page and stored native Workspace IDs. Do not generate replacement IDs or create a workspace/session database. For enable/disable/install/remove use the existing native Plugin Manager page. Runtime, API, memory capability and default provider have independent native effects/entries; the two memory components have separate package manifests.

## Implemented Remote projection

Mount the optional Host plugin `@thaliris/dsh-plugin/api` beside the active runtime. It registers native service `thalirisController`, namespace `thaliris`. The client imports the contribution and mounts through the existing Gateway:

```ts
import { remoteContribution } from '@thaliris/dsh-plugin/remote'
ctx.effect(() => ctx.remote.$mount(remoteContribution))
ctx.inject(['remote.thaliris'], ctx => {
  // Consume the traced namespace from this dependent fiber.
  // Promise<RemoteResult<T>>: inspect response.ok before reading response.value.
  void ctx.remote.thaliris.diagnostics(selectedNativeSessionId)
})
```

The mounting fiber requires `remote`; its dependent page fiber requires `remote.thaliris`. The Gateway creates this namespace as a traced Cordis service, so calling it from a fiber without that injection is rejected even after mounting succeeds. Keeping the dependency on the child avoids a circular startup dependency. The page's initial catalog refresh runs in the dependent fiber, and unload removes both its subscriptions/page and the owned contribution. The Plugins item is named `Thaliris`; `General` labels only its internal tab.

The contribution uses native strict input codecs and the Host's SRC Remote method markers; native Gateway/client mount and dispatch are exercised in the runtime tests. No separate RPC carrier is needed. Inputs contain only native IDs; runtime verifies the exact persisted root ancestry, configured Workspace and Core anchor before resuming a nonresident Session through the native Agent service. Diagnostics and approval dispose only a temporary Agent handle they opened; resident root Agents remain under their existing owner. Signal is the optional final client parameter and is supplied by the native Gateway to the Host method.

| Method | Arguments | Successful value |
|---|---|---|
| `templates()` | none | Detached initial editable role templates; does not change stored roles |
| `providers()` | none | Current registered `[{id,name}]`; empty when capability/providers absent |
| `toolCatalog()` | none | Current native tool registry `[{name,description}]` |
| `diagnostics(sessionId, signal?)` | Native root Session ID | `{task:{state,contract},workspace:{root,workspaceId},configurationRevision:number|null,permissions:{memory,roles},providers,reservations:[{reservation,native}]}` |
| `approveMemory(sessionId, proposalId, signal?)` | Native root Session and selected Core proposal ID | Provider write result and Core acknowledgement; records native-client approval observation under current grants |

Diagnostics uses current Core state/intent, native catalog/terminal Session evidence and live Settings. `configurationRevision:null` means native Settings is absent/unavailable; it is not revision zero. Resident child evidence may remain UNKNOWN. Re-query on native task/session activity or an explicit user refresh; never infer Completed from a missing card or catalog activity. No mutable diagnostic state is stored.

Memory proposals are JSON records in `task.state.pending_results`, distinguished by `proposal_id`. Their policy, provider, key, text, provenance, selected role and Workspace ID are retained. Native-client approval receipts carry `approval_id` and the same proposal ID. The Diagnostics view renders proposal content once and displays receipts as approval evidence; receipts do not become proposal cards. A view may show these records and an explicit user review action; it must not auto-approve proposals, treat Curator text as approval, or enable auto policy on its own. Auto requires explicit persisted user opt-in. Provider response limits apply to serialized UTF-8 bytes. Provider writes may be completed before a subsequent Core receipt failure; report that outcome as uncertain and refresh evidence/provider state rather than fabricate failure or success. Providers own write idempotency.

## Tool/runtime contract

The Controller's native tool calls are independent of UI:

- `thaliris_task_start({goal,contract})` selects actual human intent and execution mode.
- `thaliris_task_inspect({})` reads Core state/contract.
- `thaliris_workstream({task_id,base_revision,workstream,role,handoff,route?,memoryContext?})` takes an enabled role ID. `handoff` has goal/scope/invariants/acceptance/context strings. Allowed model mode requires the supplied route; inherit forbids an override. `memoryContext` is at most four explicit selections `{provider,operation:'read'|'search',key? ,query?,limit?,maxBytes}`; bytes 1–16384 and search limit 1–20. Results reach only that selected handoff and require Controller plus selected role grants/context permission. No ambient memory is injected.
- `thaliris_reconcile({task_id,base_revision,action:'check'|'reconcile'|'cancel-reconcile'})` reads exact native correlation/terminal evidence. Check never releases. Reconcile only releases proven terminal work and preserves reservation/evidence. Cancel-reconcile handles an exact resident native child first. UNKNOWN remains reserved; no broader abandon endpoint exists.
- `thaliris_task_close({task_id,base_revision,decision})` records Controller acceptance; unresolved work blocks it.

Optional memory tools read/search under explicit byte/item bounds and propose writes. Children need native tool allowlist membership and current enabled role grants/context permission. The model-facing tools expose no policy mutation or approval endpoint. Tasks/close/routing remain usable after memory capability removal.

## Client behavior and packaging

The shared client registers in native `plugins.item` only while the Host serves `thaliris`. General edits `policy.controllerPrompt`; Roles edits complete records, supports custom and empty role sets, explicit templates, duplication with a new unique ID, deletion, exact native routes, native tool grants, and role memory/context permissions; Memory exposes write mode, independent auto-write consent, provider enablement and Controller grants, with each role's controls labeled by its name and ID; Context binds native Workspace IDs and role context permissions; Diagnostics reads a selected native root Session, displays Core and native observations, opens a correlated child Session, copies a valid reconcile request, and exposes an explicit proposal-approval action only when current grants permit it. A Settings revision conflict exposes the page's explicit reload action, which discards the local draft and reads the latest native values. Approval remains disabled while a request is pending; failures display the returned detail with the provider-write uncertainty guidance.

The component uses native locale and settings primitives. Editable data remains on the `thaliris` ConfigForm with revision-fenced atomic mutations. The only client-side policy state is the unsaved page draft. Duplicating a role copies its visible fields and grants while assigning a new unique, stable ID. Diagnostics, Workspace, Session, model, provider, and tool values are native projections; they do not become a second Settings, Session, Workspace, or task store. Desktop uses the same DSH Web client registration and module bundle.

`dsh.client` declares the shared client dependencies, and `./client` resolves to the generated DSH closure-factory artifact in `lib/client.js`. Build from the pinned DSH source with `npm run build:client` and `DSH_SOURCE` set; component tests use `npm run test:client`. The activation smoke takes `THALIRIS_PACK_DIR`, `DSH_SOURCE`, `THALIRIS_TEST_TMP_ROOT`, `THALIRIS_TEST_PYTHON`, and `THALIRIS_TEST_CORE_PATH`. It installs the real local archives through the native Plugin Manager in an isolated profile, then resolves and activates their packed runtime, API, memory capability, and provider entries through the native Host Loader. A Core wheel is installed in the fresh test environment; the smoke starts, inspects and explicitly closes a task through the packed runtime and local subprocess, removes the optional memory packages, then confirms the task can still be inspected and closed. The two optional memory packages ship their own disabled-by-default bundle patches and are independently removable through the existing native Plugin Manager.

Client tests cover native Settings revision conflicts, role create/edit/duplicate/delete/empty persistence, model and tool selection, Workspace binding, separate memory consent and grants, absent providers, native diagnostic projections, explicit proposal approval, and actual slot/Gateway contribution mount and disposal. The generated bundle is built with the DSH client preset. In an isolated native Web profile, the served boot document advertised `@thaliris/dsh-plugin/client`, and the native Host returned the corresponding packed client module combo. The profile activated the packed runtime, API, capability, and provider bundles; interactive page rendering was not verified. Desktop declares the same shared Web client bundle, but a Desktop binary was not launched. No online model credentials or current installed profile are needed.

Do not add an orchestration state machine, claim semantic completion from observations, duplicate native policy/pipeline storage, or auto-release UNKNOWN reservations.
