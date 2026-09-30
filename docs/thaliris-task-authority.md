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

The checkpoint boundary is the checked CLI for Core task mutations and the
checked adapter for lifecycle writes. Direct Core Python calls do not issue
task authority. External anchors and evidence are private local state and
must not be committed. Deleting or forging the external store through shared
OS access is outside this governance boundary; it is not treated as an
authenticated human decision.
