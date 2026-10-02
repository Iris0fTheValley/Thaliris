# Persistent task authority

Task authority is selected human task intent, recorded by an explicit
Controller operation. Native Root identity remains UNKNOWN: the pinned Codex
source identifies ThreadSpawn children, but built-in Review may omit identity
fields. UserPromptSubmit also receives generated delegate input and supplies
no mechanical human-original signal. Neither it nor session equality, field
absence, environment or process ancestry creates authority.

The governance boundary accepts the Controller's selection of the actual
human instruction. Shared OS access and indistinguishable unrecognized
delegates are outside universal authentication; this is not cryptographic
human authentication or an OS privilege boundary. Known children, readonly
roles and fenced actors cannot establish, rewrite, enlarge or recover task
authority through the managed Hook. Direct obvious control-file writes are
denied for every mode. The installed pinned runtime remains a separate trust
boundary; changed runtime bytes are never reblessed by repository authority.

After bootstrap, select a JSON contract and call the installed runner:

```json
{
  "human_instruction": "The actual human task instruction",
  "boundary": "The Controller-selected scope and contracts",
  "invariants": "The accepted hard invariants",
  "acceptance": "The accepted completion criteria",
  "execution_mode": "delegated"
}
```

```text
thaliris task-start "goal" --bootstrap-receipt <receipt> --authority-contract <json>
```

The Hook witnesses this explicit operation with a one-shot receipt and binds
the selected file bytes; it does not attest human authorship or promote the
actor to CONTROLLER. The external anchor lives under the platform user's
`.thaliris/task-authority/`, independently of CODEX_HOME and repository config.
It binds resolved project path, task UUID, goal, boundary, invariants,
acceptance, mode and lifecycle, retaining state/lifecycle snapshots, security
baseline and monotonic fences. The project path is the workspace identity;
moving the checkout is a distinct project and requires a new selected grant.

Authority persists across turns, network, Hook, session and daemon interruption.
Unknown Host wait/reentry capability does not revoke task intent or block its
explicit establishment. It remains an UNKNOWN readiness observation; no wait
cap or automatic completion reentry is manufactured from the authority grant.
An intact ACTIVE anchor permits bootstrap continuation, checked control
commands and new fresh handoffs without a new Root identity proof. Child
binding still requires exact parent/session/turn/handoff evidence; reconnect
does not rebind an old child. Authority ends on task closure, human revocation,
Controller abandonment or replacement. A retired anchor cannot revive copied
ACTIVE state. Goal, scope, acceptance, mode, unfencing and a different security
baseline require a superior decision from actual human instruction, never
child-written prompts, state or config. There is no automatic expansion API.

Execution modes are explicit task intent:

- `delegated` retains the default Controller/Implementer routing and native
  Completed closure requirement.
- `controller-direct` permits Controller reads, edits, fixes, tests,
  verification, documentation, Git and closure without an implementation
  spawn. Supported fresh auxiliary roles remain available when useful.
- `single-agent` permits ordinary Codex work and closure and rejects children.

No explicit human override means `delegated`. Every mode retains fresh role
isolation, reviewer/verifier readonly and explicit Astra authorization.
Closing an override task still requires no pending or active managed children.

State, lifecycle or security conflicts leave the external authority unchanged.
`task-status` reports its exact hash and a bounded recovery action:

```text
thaliris task-recover-authority --expected-authority-sha256 <hash> --reason "recover the interrupted task"
```

This continues existing authority: it archives the external anchor and current
repository evidence, restores the last recorded state/lifecycle and original
security bytes, and adds fences for known old children. It does not bless
current changed security config or unfence actors. Attempt native termination
or observation of known old children where available; missing death proof
remains UNKNOWN and does not permanently lock recovery. Old children are never
called Completed; a new delegated handoff is required for delegated closure.
An interrupted write between repository and anchor updates may require this
restore; the prior recorded state is retained. New work can then continue
under the same task UUID, goal, scope, acceptance and execution mode.

For Codex, the checkpoint boundary remains the checked CLI for Core task
mutations and the checked adapter for lifecycle writes. The public
`thaliris.authority.AuthorityStore` is the Core-owned Python API for other
adapters. It imports Core and the standard library, without importing Codex
lifecycle, runtime identity, bootstrap or CLI code. Ordinary ledger calls
still do not implicitly issue task authority: an authorized adapter explicitly
establishes the selected contract and checkpoints its checked writes.

Core owns contract schema validation, execution-mode values, project/task/goal
identity, intent provenance, external anchor naming, state and protected-file
hashes/snapshots, retired-state checking, history, recovery CAS, exact-byte
archives and restoration. The external anchor accompanies the existing Core
task ledger; it is not a second task ledger. Core does not interpret the
contract, authenticate an actor, enforce semantic routing, or decide whether
verification is sufficient to finish.

`thaliris.task_authority` remains the Codex compatibility facade. Its function
signatures, external directory, record fields and conflict error names remain
available. Codex supplies its protected config paths, origin session hash,
lifecycle path/snapshot, and session/agent fences. Its recovery callback resets
native child evidence and adds old child fences. Core never invents a generic
Host/session identity or calls a Host to infer those facts.

An adapter can use the same Python Core from a transport process:

```python
from pathlib import Path
from thaliris import authority, core

# root is an existing Git workspace. These calls require adapter authorization.
core.init(root)
store = authority.AuthorityStore(
    root, Path.home() / ".thaliris" / "task-authority",
    protected_paths=(".context/config.json", "host/security.json"),
)
core.task_start(root, goal, None, None, actor="controller")
store.establish(core.task_show(root)["state"], selected_contract)
store.check()

# After a checked core.task_update(...), anchor the new state bytes.
store.checkpoint()

# Restore the last anchored state and original protected bytes after a conflict.
store.recover(authority.digest(store.path()), "Restore the existing task intent")

# After the adapter authorizes closure, DONE state retires the anchor.
core.task_close(root, core.task_show(root)["state"]["revision"])
store.checkpoint()
```

Record and recovery results contain JSON-compatible values. A transport process
converts incoming workspace/storage/path strings to `Path` objects and calls
this API; Core does not define a Node plugin or Host wire protocol.

The adapter chooses the external storage directory and protected paths from
its trusted boundary, rather than mutable repository config. Core records
selected task intent with neutral provenance (`SELECTED_TASK_INTENT`) and makes
no Host actor assurance claim. An adapter may supply its own immutable
provenance and Host assurance fields. The Codex facade preserves its existing
`CONTROLLER_ASSERTED_HUMAN_INSTRUCTION` provenance and `UNKNOWN` Host assurance
in stored anchors and recovery results. Core recovery reports the recorded
provenance without adding Host assurance or native death-proof claims; the
Codex recovery adapter supplies its existing `UNKNOWN` death-proof metadata.
`establish` can carry explicit `adapter_fields` without overwriting Core-owned
identity fields. For
native evidence, `check(evidence={digest_field: (path, conflict_error)})` checks
adapter-supplied paths against the existing record. `recover` accepts
`archive_paths={archive_relative_path: native_path}`, `restore_adapter(record)`
and that same evidence mapping. The adapter owns native snapshot validation,
fencing and its restoration callback; it must preserve intent and the original
security baseline. Recovery also accepts callables for the archive and evidence
maps; they receive the locked anchor record so native paths are derived after
the CAS and active-status checks. Core holds the repository lock during recovery.
Other mutations run at the adapter's previously checked command boundary; the
repository/anchor checkpoint is not a multi-file transaction. Interrupted
writes can require recovery to the prior anchor. `checkpoint` retires deleted
state as ABANDONED and never reactivates a retired anchor.

For Codex, Host actor assurance and native death proof remain UNKNOWN. Core
does not generate either claim. External anchors and evidence are private local
state and must not be committed. Deleting or forging the external store through
shared OS access is outside this governance boundary; it is not treated as an
authenticated human decision.
