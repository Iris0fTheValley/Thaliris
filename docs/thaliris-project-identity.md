# Project identity

Thaliris Core 0.5.0 adds a Project Identity plane: one versioned, repository-tracked
statement of what a project is for and what must not be changed silently, with an
explicit way to change it and an optional way to record why significant decisions
exist.

The invariant it serves:

> Lower-level work (tasks, experiments, strategy, implementation) must not silently
> redefine the project's long-term identity. Identity may be challenged by evidence
> and may change, but only through an explicit, recorded, human-decided amendment.

Core records, versions, validates syntax and references, enforces compare-and-swap
and atomic writes, observes divergence, and returns bounded content. It never decides
which layer a change belongs to, whether a challenge is valid, whether an amendment
is wise, what is affected, or what must be revalidated. Nothing propagates
automatically, nothing is injected into role sessions, and nothing gates ordinary
tasks. A project without an identity is normal and is never blocked or nagged.

## Boundary against other Thaliris mechanisms

| Mechanism | Scope | Changes how |
| --- | --- | --- |
| Project identity | The whole project, across all tasks and Hosts | Only by an amendment that records the human owner's decision |
| Task Authority | One task's frozen human intent and constraints | Never by an amendment; a new human decision starts a new task |
| Task ledger / evidence continuity | One task's records, observations and judgments | Task-scoped CAS updates |
| Memory (`.agent-memory/`) and milestones (`.milestones/`) | Durable knowledge and long-lived plans | `task-promote`, `document-maintain`, ordinary edits |

- An amendment never rewrites a running task's frozen Task Authority contract. A task
  whose contract conflicts with a newer identity keeps its contract; the owning
  Controller tells the user, and only a human decision starts a new task or changes
  intent.
- Amendment is not memory promotion. `task-promote`, `document-maintain` and Host
  memory approval never amend identity.
- Legacy memory labels (`Kind: HARD_CONSTRAINT`, `Applicability: PROJECT`,
  `Status: CURRENT`) confer no identity authority anywhere.
- `.project-identity/` is not a Task Authority protected or security path, so an
  in-task amendment does not trip authority security checks. Adapters that block
  child writes to it do so with a separate child-write list.

## Files

```text
.project-identity/
  IDENTITY.md                         human-readable copy of the current recorded version
  ledger.json                         baseline chain only; the commit point of an amendment
  versions/v0001.md                   immutable exact snapshot of each recorded version
  amendments/A-0001.md                immutable amendment record (A-000N produces v000N)
  challenges/<CH-id>.json             one immutable file per challenge
  challenges/<CH-id>.resolution.json  immutable resolution: amended | dismissed
  relations/<REL-id>.json             one immutable file per purpose relation
  relations/<REL-id>.retraction.json  immutable retraction
```

- The namespace is tracked by Git and is not created by `init`, `task-start` or any
  adapter bootstrap. An absent namespace means "no identity".
- `ledger.json` has `format: "thaliris-project-identity-v1"`, `version`, a
  `versions` chain (`version`, `path`, `sha256` canonical, `raw_sha256` as written,
  `amendment`, `recorded_at`) and an `amendments` index (`id`, `path`,
  `from_version`, `to_version`, `sha256`, `summary`, `recorded_at`). Core refuses to
  write an unknown format and reports it on read. Concurrent amendments on two Git
  branches conflict in `ledger.json`; that conflict is intended.
- Challenge and relation ids are `CH-<UTC yyyymmddThhmmssZ>-<12 hex>` and
  `REL-<UTC yyyymmddThhmmssZ>-<12 hex>`: collision-resistant across branches, never
  sequential counters. Resolutions and retractions are new files; nothing is edited
  or deleted.
- Amendment records are Markdown for humans with the exact machine record in a
  final `## Record` JSON block. The replacement text is the immutable snapshot the
  record names by path and canonical sha256.

### Hashing

Every comparison uses a canonical sha256: UTF-8 bytes without a leading BOM, with
CRLF and CR normalized to LF. Core writes canonical bytes and records the raw hash
alongside, so Git line-ending conversion (`core.autocrlf`) never produces false
divergence.

### Item anchors

Items are ATX Markdown headings outside fenced code whose text starts with an id
token matching `[A-Z][A-Z0-9]{0,15}-[0-9]{1,4}` (for example `## INV-1 ...` or
`### P-3: ...`). Any prefix is accepted; Core imposes no taxonomy. Duplicate ids in
one version are invalid. An item's text is its heading through the line before the
next heading of the same or higher level (trailing blank lines excluded); Core hashes
item text to diff versions.

### States and integrity

| State | Meaning |
| --- | --- |
| `ABSENT` | No `ledger.json` and no recorded history (`versions/*`, `amendments/*`, resolution files). A hand-written `IDENTITY.md` alone is still `ABSENT` (reported in `detail`) and can become v1 |
| `CURRENT` | `IDENTITY.md` canonically equals the recorded current version |
| `UNRECORDED_CHANGE` | `IDENTITY.md` differs from (or is missing against) the recorded version. Core never adopts or reverts it; reads serve the recorded version and flag the divergence |
| `INVALID` | An integrity check failed; `detail` states the scope (see below). All mutations refuse until repaired |

`INVALID` has two scopes, stated in the first `detail` entry (`scope: chain` or
`scope: side_records`):

- **`chain`**: the baseline chain cannot be trusted (ledger unreadable, conflict markers,
  unknown format, snapshot or amendment-record hash mismatch, missing or duplicate version,
  files for versions beyond the ledger, or `ledger.json` missing while any recorded history
  exists). Reads refuse; only `identity-status` answers.
- **`side_records`**: the chain verified but a challenge, relation or resolution file is
  malformed, over its count limit, or disagrees with the chain. Baseline reads
  (default, `--version`, `--item`, `--amendment`) still succeed and carry an integrity
  `notice`; `--challenge` refuses for a damaged record and `identity-trace` refuses while
  relations are damaged.

### Integrity rules

- **History is never overwritten.** An amendment writes only the files of the one
  uncommitted next version and `IDENTITY.md`; files at or below the committed ledger
  version are never rewritten. A missing ledger with recorded history is `INVALID`
  (`chain`), never `ABSENT`, so a retried establishment cannot erase it. Restore
  `ledger.json` from Git history or a `.context/backups/` record. If an *establishment*
  was interrupted before the ledger commit, its remnants (`versions/v0001.md`,
  `amendments/A-0001.md`) cannot be told apart from a lost ledger and need the same
  manual repair.
- **`amended` comes from the chain.** A challenge is `amended` only when a committed,
  hash-chained amendment record lists it in `resolves`; the `*.resolution.json` mirror is
  derived, so a missing mirror changes nothing. A mirror that cites an amendment not in the
  chain, or one whose record does not list that challenge (for example after a merge of
  two branches that both amended v1), makes the state `INVALID` (`side_records`) and
  names the file. `dismissed` resolutions remain file-based and may not contradict a
  committed `resolves`.
- **Interrupted amendments are recoverable.** The ledger is the commit point and
  resolution mirrors are written after it. A crash before the commit leaves the identity
  readable at the last committed version; remnants of exactly the next version
  (`versions/vN+1.md`, `amendments/A-N+1.md`, a mirror citing it, the changed
  `IDENTITY.md`) are listed in `detail`, the state is `UNRECORDED_CHANGE` when
  `IDENTITY.md` differs, and retrying the same `identity-amend` (naming the on-disk
  `base_sha256`) replaces them.

`rollback` refuses backups produced by identity mutations. Reversing an identity
change is a new amendment, a challenge dismissal or a relation retraction. Prior
bytes still remain in `.context/backups/` as recovery evidence.

## References

| Ref | Validation at registration | Recorded |
| --- | --- | --- |
| `identity` | a recorded baseline exists | version |
| `identity:INV-2` | item exists in the current recorded version | version and item canonical sha256 |
| `amendment:A-0003` | exists in the ledger | — |
| `challenge:<CH-id>` | exists | — |
| `path:docs/design.md` (optional `#anchor`) | safe repo-relative file, exists, not under `.git`/`.context` (compared case-insensitively) | canonical sha256 |
| `task:<task-uuid>/<object-id>` | if that task's ledger exists locally, the object must exist; otherwise accepted as unverified | `verified` |
| `commit:<7-40 hex>` | syntax only | — |
| `url:http(s)://...` | syntax only | — |

Trace reports each endpoint's state now, relative to what was recorded at
registration: identity `CURRENT` / `CHANGED_SINCE_v<N>` / `REMOVED`; path `FRESH` /
`CHANGED` / `MISSING`; task `RECORDED` / `UNVERIFIED`; other refs `RECORDED`.
Every trace and dependents list carries the notice: *Registered relations only;
absence of a relation is not evidence of independence.*

## Operations

Python API: `from thaliris import identity`. CLI: `thaliris-core [--root R] [--task-id T] <op>`.
Every response is one JSON object; exit 0 when `ok`, 2 on refusal (`{"ok": false, "error": ...}`).

### Reads (no task needed, never write)

- `identity-status` / `identity.identity_status(root)` returns `ok`, `state`,
  `version`, `format`, `baseline_path`, `recorded_sha256`, `on_disk_sha256`,
  `last_amendment{id, summary, recorded_at}`, `items[{id, title}]`, `items_total`,
  `open_challenges[{id, targets, summary}]`, `open_challenges_total`,
  `challenges_total`, `relations_total`, `relations_active`, `summary`, `truncated`
  and optional `detail[]`. Bounded to 16 KiB, at most 64 items and 16 open challenges.
  Since Core 0.5.2 it also returns `basis{pending, total, retracted, damaged}` and
  `suggestions{enabled, source}` from the machine-local formation store (see
  [Natural formation](#natural-formation-basis-notes-offer-preferences)); they never change
  `state`. `--session-key K` / `session_key=` lets session-scope preferences resolve.
- `identity.identity_summary(root) -> str | None`: the same `summary` line, `None`
  when absent, for example
  `Project identity v3 (A-0003, CURRENT); 1 open challenge. Read on demand: identity-get.`
- `identity-get [--version N] [--item ID ...] [--amendment A-000N] [--challenge ID]` /
  `identity.identity_get(root, version=None, items=None, amendment=None, challenge=None)`:
  - default: `{kind: "version", state, version, current_version, amendment, sha256,
    on_disk_sha256, on_disk_divergent, text, notice?}` for the recorded current version;
  - `--version N`: the same for a historical snapshot;
  - `--item`: `{kind: "items", state, version, current_version, on_disk_divergent,
    items[{id, title, level, sha256, text}]}`;
  - `--amendment`: `{kind: "amendment", amendment, path, record}`;
  - `--challenge`: `{kind: "challenge", challenge, status: open|amended|dismissed, resolution}`.
  Each response is at most 64 KiB.
- `identity-trace REF [--direction up|down|both] [--depth 1..4]` /
  `identity.identity_trace(root, ref, direction="both", depth=1)`: traverses active
  relations. `up` follows edges from `from` to `to` (a lower item toward what it serves),
  `down` follows them inversely. Returns `{ref, direction, depth, state, version,
  edges[{id, from, from_state, rel, to, to_state, note, recorded_at, depth}], truncated,
  notice}` with at most 128 edges. Ref matching is exact.

### Mutations

`identity-amend`, `identity-challenge` and `identity-relate` take
`--actor A --base-revision N --input FILE|-` and require an explicit `--task-id` naming an
ACTIVE task. The Python functions `identity_amend|identity_challenge|identity_relate(root,
actor, base_revision, input)` accept a path, `-` or a dict and require
`core.select_task(root, task_id)` first. They check the task revision (CAS) but do not
bump it, keep task state schema 7, write under the Core lock through the backup and
atomic-write path, and record `task_id`, `actor` and a UTC `recorded_at`. Each returns
`task_id`, `state_revision` and `backup`.

- **identity-amend** input: `{base_version, base_sha256, text, summary, rationale,
  decision{decided_by, human_instruction}, challenge_text?, why_not_lower?,
  evidence_refs?[], resolves?[challenge ids], affected_refs?[]}`. `base_version` must
  equal the recorded version (0 to establish), `base_sha256` the canonical hash of the
  on-disk `IDENTITY.md` (null when absent). Text must be ≤ 64 KiB with unique anchors and
  differ from the current version; `resolves` must name open challenges. Writes the
  snapshot, `IDENTITY.md`, the amendment record, the ledger (commit point), then the
  `amended` resolution mirrors. Returns `version`, `amendment`, `sha256`, `items{added, removed, changed}`,
  `registered_dependents[{id, from, rel, to, to_state, note}]` (active relations to
  `identity` or a removed/changed item, trimmed so the whole response stays within 64 KiB),
  `registered_dependents_total`, `registered_dependents_truncated`,
  `challenges_resolved`, `notice`, `written`.
  Core cannot verify a human: `decision` records the asserted decision, like Task
  Authority's `human_instruction`.
- **identity-challenge** input: open `{targets[identity | identity:ID], summary, text,
  evidence_refs?[], proposed_change?}` returns `{challenge, status: "open"}`; dismiss
  `{dismiss: <id>, reason}` returns `{challenge, status: "dismissed"}`. Only open
  challenges can be dismissed; `amended` happens only through `identity-amend.resolves`.
  Challenges are project-level and survive task closure.
- **identity-relate** input: `{add?[{from, rel, to, note?}], retract?[{id, reason}]}`
  returns `{added[], retracted[], notice}`. `rel` is `serves` (lower → the purpose it
  serves), `supports` or `challenges` (evidence → a judgment, decision or design), or
  `supersedes` (new → old). A `challenges` relation may not target `identity` or
  `identity:*`: evidence challenging identity is recorded with `identity-challenge`.
  Self-edges and duplicate active edges are rejected; retracting an unknown or
  already-retracted relation is rejected. Re-registering an edge at a newer version is
  a retraction plus an add in one request.

Bounds: ≤ 512 challenges, ≤ 2048 relations including retracted, ≤ 64 adds and 64
retractions per request, ≤ 1000 versions.

## Natural formation: basis notes, offer, preferences

Core 0.5.2 lets a project's identity form from what the user already says during normal
work, with one-time confirmation instead of a setup questionnaire, and without nagging.
The semantics stay with the owning Controller (whether a statement is an explicit
long-term statement by the user, how a draft is composed); Core only stores, counts,
gates and resolves preferences mechanically. Python API: `from thaliris import identity_basis`.

Nothing here touches `.project-identity/` or the repository: no draft `IDENTITY.md` is
written, no ref prefix is added, and the identity chain, amendment, challenge and relation
formats are unchanged, so Core 0.5.0/0.5.1 read every identity state 0.5.2 produces
exactly as before. Formal identity still changes only through `identity-amend`.

### Storage (outside the repository, this machine only)

The root is `THALIRIS_HOME`, else `~/.thaliris`; directories are created lazily on the
first write that needs them (reads, status and an offer with no notes create nothing).

```text
$THALIRIS_HOME/
  preferences.json                                   global suggestion preference
  sessions/<sha256(session key)>.json                session preference
  workspaces/<workspace key>/preferences.json        this checkout on this machine
  projects/<project key>/project.json                diagnostics: root path and Git common dir
  projects/<project key>/preferences.json            project preference (all worktrees)
  projects/<project key>/offer-state.json            highest note id an offer was shown for
  projects/<project key>/identity-basis/N-0001.json  immutable basis note
  projects/<project key>/identity-basis/N-0001.retraction.json
```

- **project key**: sha256 of the resolved `git rev-parse --git-common-dir`, so every
  worktree of one repository shares notes, the project preference and the offer state.
  Outside Git, or when Git is unavailable, it is the sha256 of the resolved project root.
- **workspace key**: sha256 of the resolved project root (one checkout on one machine).
- Writes are atomic (temp file + replace) under a per-project lock; files are bounded
  (64 KiB each, at most 4096 notes, ids `N-0001`..`N-9999`, monotonic, never reused).
- A damaged file is reported, never raised into close or session flows, and never makes
  the identity `INVALID`: `identity-status` counts it in `basis.damaged` or lists the
  scope in `suggestions.damaged`, `identity-note --list` names it in `damaged_files`,
  and the offer returns nothing.

### Basis notes: `identity-note`

`thaliris-core identity-note --actor A --input FILE|-` /
`identity_basis.identity_note(root, actor, input)` (path, `-` or dict). No ACTIVE task is
required; with `--task-id` naming an ACTIVE task its id is recorded, otherwise `task_id` is
null. Controller-only in every adapter.

- Add: `{quote, kind?, context?, refs?}`. `quote` is the user's verbatim words (non-empty,
  ≤ 8 KiB UTF-8, no control characters except newline and tab; CRLF is stored as LF).
  `kind` is one of `purpose|direction|constraint|non-goal|decision|rejection|material|other`
  (default `other`). `context` (≤ 300 characters, one line) is the recorder's own framing,
  stored and shown as such, never as the user's words. `refs` (≤ 16 unique one-line strings
  of ≤ 1024 characters, for example `path:docs/vision.md`, `task:<id>`, `url:...`) are
  free-form and never resolved. Unknown fields are refused. The stored record adds `format`,
  `id`, `recorded_at` (UTC), `actor`, `task_id` and `identity_version` (the recorded
  version at recording time; 0 when ABSENT or unreadable). Returns `{note, pending,
  task_id, basis}`.
- Retract: `{retract: "N-000k", reason}` writes a separate immutable retraction (for a
  wrong recording or the user withdrawing the statement). Returns `{retracted, retraction,
  task_id, basis}`.
- List: `identity-note --list [--include-retracted]` /
  `identity_basis.identity_note_list(root, include_retracted=False)` returns `{identity_state,
  identity_version, notes[...record, pending, retracted, retraction?], omitted, truncated,
  basis, notice, damaged_files?}`, oldest first, at most 64 KiB (oldest omitted first).
- **pending** = not retracted AND `identity_version >= current recorded version`. After an
  amendment, older notes stop being pending; while ABSENT every non-retracted note is.
- Errors use stable codes: `IDENTITY_NOTE_INVALID`, `IDENTITY_NOTE_NOT_FOUND`,
  `IDENTITY_NOTE_ALREADY_RETRACTED`, `IDENTITY_NOTE_LIMIT`.

### Suggestion preferences: `identity-suggest`

`thaliris-core identity-suggest --actor A (--on|--off|--clear) --scope
session|workspace|project|global [--session-key K]` /
`identity_basis.identity_suggest(root, actor, scope, setting, session_key=None)` with
`setting` `on|off|clear`. Set only on the user's words. Session scope needs the adapter's
native session key; session files untouched for 30 days are pruned opportunistically when a
session preference is written. Resolution: session > workspace > project > global >
default on; status reports `{enabled, source}` with `source` one of
`session|workspace|project|global|default`. `--clear` removes that scope's setting (and
also removes a damaged preference file). Invalid input: `IDENTITY_PREFERENCE_INVALID`.

Off suppresses only the proactive offer. Notes are still recorded and listed, and facts
(the identity summary line, `INVALID`, `UNRECORDED_CHANGE`) are never suppressed.

### The offer: selective, at a natural pause, mechanically once

`identity_basis.identity_offer(root, session_key=None) -> str | None` (CLI:
`identity-offer [--session-key K]` returns `{ok, identity_offer: line|null}`). It returns
one line only when suggestions resolve to enabled (and no consulted preference file is
damaged); the identity state is `ABSENT` or `CURRENT` (never `INVALID` or
`UNRECORDED_CHANGE`, which are facts reported elsewhere); at least one note is pending;
and the highest pending note id is above the one last shown. It records that id in
`offer-state.json` before returning the line, so each new piece of user basis surfaces at
most once across all sessions, closes and worktrees. It never raises; any failure returns
None. Adapters call it only after a successful task close and attach the line as an
`identity_offer` field; there is no suggestion line at SessionStart, bootstrap or dynamic
context, and existing identity summary lines are unchanged.

Wording (one line, English, low priority), for example:

- ABSENT: `Project identity: none recorded; 2 user statements about the project's long-term
  direction are noted (identity-note --list). Optional: offer once, briefly, to compose a
  first version from them for the user's confirmation; no answer means no. To stop these
  offers: identity-suggest --off --scope session|workspace|project|global.`
- CURRENT: `Project identity v3 (A-0003, CURRENT); 1 user statement about the project's
  long-term direction noted since v3 (identity-note --list). Optional: offer once, briefly,
  to compose an amendment from them for the user's confirmation; no answer means no. To
  stop these offers: ...`

### Formal recording and limits

- Recording is unchanged: `identity-amend` (base_version 0 for v1) still needs an ACTIVE
  task, CAS and an explicit user decision. The Controller shows the composed text with the
  user's quotes and its own organization marked apart; on the user's yes it quotes the
  confirmation and the cited basis quotes (with dates or `N-` ids) verbatim inside
  `decision.human_instruction`, so the tracked amendment record carries the basis. If the
  user's original statement already said to make it part of the project identity, that
  statement is the decision.
- Notes are local to this machine: they are not committed, do not travel with a clone and
  are not shared with collaborators. The durable, shared basis is what an amendment quotes
  in `human_instruction`.
- Notes are not identity. They confer no authority, are never injected into children, and
  a note's `identity_version` is a counter for pending, not a reference into the chain.

## Suggested IDENTITY.md skeleton (not enforced)

```markdown
# <Project> identity

## ID-1 Identity
What the project is and whom it serves.

## INV-1 <Invariant>
A property that must hold across all work.

## P-1 <Principle>
A design principle that guides trade-offs.

## DIR-1 <Direction>
A long-term direction the project is moving in.

## B-1 Identity boundary
What would make this a different project.

## NG-1 <Non-goal>
Something the project deliberately does not do.
```

Any heading structure works; only anchored headings become diffable items. An existing
document such as a constitution can be the v1 text.

## Guidance for the owning Controller

Adapters deliver this in their own Controller guidance; the wording here is Host-neutral.

- **What it is.** Project identity is the project-level, cross-task baseline. Task
  Authority is one task's frozen intent; memory and milestones are durable knowledge
  and plans; evidence continuity records one task's observations and judgments.
- **Delivery.** Read the one-line identity summary at startup or admission and in task
  status when present; read more on demand (`identity-status`, `identity-get --item`).
  Never inject identity text into children automatically; quote the selected item ids
  and text into a handoff when they bind that child's work.
- **When to read it.** For directional or architectural tasks, replanning, cross-layer
  conflicts, and before turning an implementation limit into a principle. Not for
  ordinary local repairs.
- **Procedure.** LOCATE the layer of the problem → TRACE UP through registered
  relations → REPAIR at the lowest sufficient layer → CHALLENGE UP when evidence
  contradicts identity (record a challenge; do not edit `IDENTITY.md`) → AMEND
  EXPLICITLY only on the human owner's decision (quote it; give the rationale and, when
  a lower repair was considered, why it is insufficient) → decide which registered
  dependents to revalidate. Nothing propagates automatically.
- **Relations.** Register relations only for significant decisions, designs and
  experiments. Trace covers registered relations only; absence of a relation is not
  evidence of independence.
- **Boundaries.** Legacy memory labels confer nothing. Absent identity is normal.
  Amendment is not memory promotion. An amendment never rewrites a running task's frozen
  contract.
- **Natural formation.** Record a basis note only for an explicit statement by the user
  (in this conversation) about the project's long-term purpose, direction, constraint or
  non-goal, or an explicit decision or rejection of one; quote it verbatim. Not AI
  inferences, tentative "maybe", temporary technical choices, summaries, or child reports
  of what the user said. One runner call; never pause the current task for it. If the
  user supplies material (a few sentences, a goal, a document) and asks to record it, that
  is the decision: amend; otherwise note it (a document via `refs`). Offer to compose a
  version only when an `identity_offer` line appears (or the user is plainly describing
  what a new project is for), at most once, never blocking; no answer means no. On "don't
  ask again", run `identity-suggest --off` at the scope the user named (unstated: session,
  and mention the other scopes in one short line).
- **Writes.** Identity mutations are Controller-only. Where an adapter cannot prevent a
  child from editing `.project-identity/`, detection is `UNRECORDED_CHANGE` or
  `INVALID` plus Git diff.
