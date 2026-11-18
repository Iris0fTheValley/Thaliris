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

Execution modes are `delegated` (the default), `controller-direct`,
`single-agent` and `adaptive`. In `adaptive` mode the Controller may execute
directly and may also dispatch children. An adaptive contract may omit
`boundary` and `invariants`; `validate_contract` stores each omitted one as the
explicit marker `unspecified`. `human_instruction` and `acceptance` stay
required, and the goal comes from the task ledger. The optional `write_surface`
is a list of 1 to 64 repo-relative POSIX globs; Core compares the task surface
against it only to surface a lane advisory.

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

A contract may also select `parallel_dispatch`, which is user-directed: `enabled`
must be true, `budget` is optional (absent means no cap; present, it is the user's
explicit integer of at least 1, with no program ceiling), and `workstreams` is
optional (absent or empty means read-only fan-out). Declared workstreams carry
`{id, domain, scope, worktree, mode}` with unique ids; `worktree` is optional and
need not be unique. Scopes are literal canonical repo-relative paths, not patterns
(`thaliris.authority.canonical_scope`): Unicode NFC and casefolded on every
platform, `\` read as `/`. `[ ] { } ( )` are ordinary characters (for example
`app/[slug]` or `{templates}`); `*` and `?` are rejected as glob-only characters.
Also rejected, each with a message naming the failed rule: absolute, drive-letter,
`:`, UNC or leading-`~` forms, `.`/`..` segments, segments ending in a dot or space,
empty scopes and control characters; declare a parent directory instead of a
rejected path. Windows 8.3-looking segments (`PROGRA~1`, `lib~2`) are admitted but
compared conservatively: such a segment at index i overlaps any scope that agrees on
every segment below i, so it may alias any sibling under the same parent
(`a/PROGRA~1/x` overlaps `a/Program Files/y`; `b/lib~2` does not overlap `c/lib`).
This can over-refuse siblings but never under-detects. Invalid scopes are invalid for
read and write streams alike. The only mechanical refusal is overlapping write scopes
(`scopes_overlap`: equal, path-segment prefix or 8.3 alias, across all domains); read
workstreams never conflict. A total-text
guard of 1 MiB across declared workstream strings bounds state size. Maximum
managed depth two with one active Scanner is unaffected.

## Ledger continuity (Core 0.5.3)

Task state schemas form a forward chain: 7 (the base ledger), 8 (Controller-local
evidence), 9 (the verification-first ledger: declared checks and their results,
requirement kinds, typed claims, handoff usage, gate overrides) and 10 (compact
serialization and hot/cold archive segments). Each schema is a valid subset of the next,
so `_COMPATIBLE_PRIOR_SCHEMAS` lifts every supported prior version (6 through 9) step by
step to the current one. A state is validated once under the rules of its own on-disk
version, then lifted in memory only: reading never rewrites the ledger, so an external
anchor's recorded byte digest still matches and does not report
`TASK_AUTHORITY_STATE_CHANGED`. Every write stores the current schema; the adapter then
checkpoints it as for any checked write. Task ID, goal, records, evidence and revision
are unchanged by the lift. Only a schema newer than the running Core (and versions below
the table, or malformed states) is refused with the `STATE_SCHEMA_INCOMPATIBLE`
diagnostic; for a newer schema it carries `upgrade_required: true` and a
`recovery_action` that names the upgrade, otherwise it names the adapter's recovery
procedure and the expected sha256. An older Core refuses a ledger a newer Core wrote;
backward reading is not supported.

### Capacity and the hot/cold archive (schema 10)

`core.task_state_capacity()` returns the bounds adapters use instead of hard-coding them
(`max_bytes` 512 KiB for the hot ledger file, `archive_high_water_bytes`, `list_max`
512, `archived_list_max` 8192, the current and supported schemas);
`core.read_state_bytes(path)` reads a ledger's exact bytes within that bound. The state
file is written as compact, key-sorted JSON (`separators=(",", ":")`); loading accepts
the older indented form too, and digests are always over the exact bytes written.

When a write's serialized hot state would exceed the high-water mark (70% of the cap,
358.4 KiB), or a hot list passes 7/8 of its item cap, Core archives inside that same
write. It moves the long bodies of *settled* objects into an immutable,
content-addressed segment `.context/tasks/<task id>/archive/<sha256>.json` and replaces
each object by a stub: the same object with every structural field, a 64-character
preview (suffix ` …[archived]`) of each moved text field, and
`archived: <segment sha256>`. Moved fields: observation `text`, judgment `reasoning`,
source `locator`/`summary`, record `text`, verification-result `summary` and
`observed_files` (stub `[]`), handoff `durable_paths`. A text of at most 128 characters
stays in the stub unchanged. Below the cap a pass is committed only when it frees at
least 16 KiB (or relieves a crowded list), so a ledger that is mostly stubs does not
write a tiny segment on every write.

Settled means none of: an unincorporated observation, an unresolved judgment, an
observation an unresolved judgment cites, a handoff with open observations or no
returned result (no observation, claims marker or usage outcome), a current
(unsuperseded) record, one of the last two runs of a declared check (or of a
non-check verification kind), or a source that any hot object, artifact or current
record cites (with its source chain). Requirements, checks, artifacts, closure and
authority are never archived. Settledness is monotone because continuity is
append-only, so an archived object never becomes open evidence again. A latest
judgment may be archived: its stub keeps id, requirement_ref, candidate, outcome,
observation_refs, judgment_refs and any override, so the close gate, the withholding
gate, `evidence_summary`, `changes_since`, the tamper and claim dedupes and the
usage/claims aggregates read exactly what they read before.

Integrity and ordering: the segment is written first (temporary file, then rename;
an existing segment with the right digest is kept), then the state that references
it. The state lists its segments in `archive` (`{sha256, revision, items,
collections}` each), so the authority anchor's state digest covers every segment
digest. The validator treats stubs as present for every reference check, requires
every `archived` value to name an indexed segment and never reads segments; a model
or adapter payload cannot carry `archived`. `task-get <id>` of an archived object
reads its segment, verifies the sha256 and returns the full object (plus
`archived.segment`); a missing, damaged or foreign segment gives
`TASK_ARCHIVE_UNAVAILABLE` while gates, status and writes keep working. Promotion of
an archived source reads the full source the same way. A CAS conflict leaves the
state untouched; a crash between the segment and the state write leaves an
unreferenced orphan segment, which is harmless. The compact status packet gains an
`Archive` section once a task has archived.

List caps apply to hot objects: an archived stub does not count toward the 512-item
cap of its list (256 for `verification_results`), and a list holds at most 8192 items
including stubs. A full list or file is refused with `TASK_STATE_CAPACITY_EXCEEDED`
(still a `ValueError`) only after archiving everything archivable. `details` carries
`field`, `limit`, `count` and `unit`, and for the file (`state_file`) the open
observation edges, unresolved judgments and archived item counts; the recovery explains
that what stays hot is open evidence, current records and sources, checks and the task
surface. The write is refused and the state is unchanged; every other list stays
writable and `task-close` still works. Strict per-object validation (for example an
unknown field in one continuity object) is intentionally unchanged.

An unreadable anchor (not valid UTF-8 JSON, or a recorded snapshot that is not
valid base64) raises `TASK_AUTHORITY_INVALID` as a `ThalirisError` whose message is
that same code; recovery semantics are unchanged. Anchor records are promoted forward
like task state: an older record (no `version` reads as 0) is lifted to the current
`ANCHOR_VERSION` in memory and written in the current shape on the next anchor write;
fields an older writer did not record read with defaults (`security` and `snapshots`
empty, `history` empty, a contract without `execution_mode` as `delegated`), and an
adapter evidence digest the anchor never recorded is not compared. `state_sha256`,
`project`, `task_id`, `goal`, `contract` and `status` stay required, every digest the
anchor holds is compared exactly, and a newer anchor version is refused with
`upgrade_required` in `details`. Core never repairs or replaces the
anchor. `recover` writes the anchor only after every restoration step succeeds, so a
recovery that fails midway can be retried with the same expected digest; each attempt
archives the bytes it found before touching them. Every Git call Core makes is
bounded by a 60 second timeout (`GIT_TIMEOUT_SECONDS`): a timeout leaves the surface
baseline `UNAVAILABLE` or the base head unknown, and a timed-out root discovery or
ignore check is refused as UNKNOWN rather than treated as an answer.

Controller-local observations are written under the adapter's ordinary revision CAS
and authority checkpoint. Core reads every supported schema without writing on read;
schema 8 permits `provenance:controller-local`, a Controller producer, null handoff,
explicit candidate, registered requirement refs and source refs. It forbids native
actor/status and historical-import fields on such facts. Core validates structure;
the adapter still authorizes the actor. A local fact grants no execution rights or
independent-review status. Historical child and cross-Host observations keep their
exact fields. Older schema-7 readers refuse schema 8 as newer with
`STATE_SCHEMA_INCOMPATIBLE`; backward reading is unsupported, and stripping provenance
or downgrading a ledger is not a recovery procedure. No source change migrates a live
task or rewrites its external security anchor.
