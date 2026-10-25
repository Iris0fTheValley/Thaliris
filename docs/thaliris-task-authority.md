# Persistent task authority

Core records the Controller-selected task contract through
`thaliris.authority.AuthorityStore`. Its API is shared by Host adapters. Native
actor identity and admission are adapter responsibilities; see
[Codex admission and recovery](https://github.com/Iris0fTheValley/Thaliris-Codex/blob/main/docs/thaliris-task-authority.md).

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

`thaliris_codex.task_authority` remains the Codex compatibility facade. Its function
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

The five required contract fields remain unchanged. A contract may additionally
select `execution_constraint` as a nonempty string (at most 16384 characters).
Core transports this explicit intent without interpreting model names or policy
values; each adapter validates its supported constraints. The optional field is
part of the Core-owned immutable contract, history and recovery truth, not an
adapter override. Contracts omitting it retain their existing representation.

## Ledger continuity (Core 0.5.3)

Task state schema stays 7, and every state this Core writes is still readable by
Core 0.5.0. Core reads an earlier schema version when `_COMPATIBLE_PRIOR_SCHEMAS`
lists it (today only 6, which differs from 7 only in the extra value
`"UNAVAILABLE"` for `task_surface_baseline`). A listed version that validates under
the current rules is lifted to the current schema in memory only: reading never
rewrites the ledger, so an external anchor's recorded byte digest still matches and
does not report `TASK_AUTHORITY_STATE_CHANGED`. The next ledger write stores schema
7; the adapter then checkpoints it as for any checked write. Task ID, goal, records,
evidence and revision are unchanged by the lift. Versions below the table, newer
versions and malformed states of any version are refused as before with the
`STATE_SCHEMA_INCOMPATIBLE` diagnostic, whose `recovery_action` now names the
adapter's recovery procedure and the expected sha256 instead of one adapter's command.

A full bounded list is refused with the stable code `TASK_STATE_CAPACITY_EXCEEDED`
(still a `ValueError`). `details` carries `field`, `limit`, `count` and `unit`; the
fields are the ledger lists (`records`, `evidence_refs`, `artifact_refs`,
`verification_results`, the four evidence-continuity collections,
`active_work`, `pending_results`), the routing page (`active_work+pending_results`,
8 KiB) and the whole file (`state_file`, 512 KiB). The write is refused and the state
is unchanged; every other list stays writable and `task-close` still works. To
record more of the full kind, close the task and start a new one that cites the old
Task ID. Strict per-object validation (for example an unknown field in one
continuity object) is intentionally unchanged.

An unreadable anchor (not valid UTF-8 JSON, or a recorded snapshot that is not
valid base64) raises `TASK_AUTHORITY_INVALID` as a `ThalirisError` whose message is
that same code; recovery semantics are unchanged. Core never repairs or replaces the
anchor. `recover` writes the anchor only after every restoration step succeeds, so a
recovery that fails midway can be retried with the same expected digest; each attempt
archives the bytes it found before touching them. Every Git call Core makes is
bounded by a 60 second timeout (`GIT_TIMEOUT_SECONDS`): a timeout leaves the surface
baseline `UNAVAILABLE` or the base head unknown, and a timed-out root discovery or
ignore check is refused as UNKNOWN rather than treated as an answer.
