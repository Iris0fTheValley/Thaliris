# Runtime drift and administrative recovery

Thaliris 0.4.2 follows Detect -> Diagnose -> Decide -> Repair/Accept -> Continue.
Runtime drift is evidence for a decision. Ordinary repository reads, source
edits, focused tests, investigation, and repairs remain available with managed
assurance UNKNOWN. An unexplained change denies only the affected dangerous
control operation. A legitimate upgrade can be selected at a new isolated
runtime path; the old manifest is archived, owned generated definitions are
updated, and user-owned collisions are preserved for an explicit decision.

`doctor` reports concrete paths and expected/actual hashes for runtime files,
Python bytecode, hooks, and profile definitions. A changed package or `.pyc`
file must not execute before platform validation. Python `-B` suppresses writes
but can still read caches, so caches remain executable inputs in the exact
manifest. An ordinary workspace source edit is outside that installed-runtime
boundary. CLI version, responding daemon version, topology, configuration,
authorization, running state, and health are separate observations. Same
executable path, inherited environment, PID, process ancestry, and SessionSource
do not prove daemon ownership or current Controller identity.
Installation rejects an existing manifest that is a nonfile, symlink, junction,
or has a linked ancestor before any installed-package import or executable
probe. Host installation ownership also cannot cross a linked home ancestor.

The Windows entrypoint pins a separate PowerShell preflight by hash and checks
the complete runtime before invoking Python. Its inline degraded policy is a
compressed generated literal so the physical command stays below cmd's 8191
character limit. The outer Host command uses a quoted PowerShell `-Command`
gzip loader for the same closed generated literal; ownership recognition
decodes it and requires exact regenerated command equality. It does not
evaluate hook input as code. A damaged runtime,
preflight, or trampoline emits a precise diagnostic and preserves ordinary
work. Managed state writes and unsafe authority grants remain denied.

Codex 0.159.2's immutable source supplies `agent_id`/`agent_type` on native
ThreadSpawn PreToolUse/PostToolUse events. Its shared `session_id` is inherited
by descendants. Built-in Review delegates use another source variant and omit
agent fields while sharing that session. Thus absence of fields or a matching
owner session alone cannot authorize Controller control. Current admission
leaves actor assurance UNKNOWN and does not mint or consume Controller
attestations. Definition readiness is reported as
`DEFINITION_READY_ACTOR_UNKNOWN`. Bound named children retain their existing
identity, isolation, and readonly rules. The fixture
`codex-0159-actor-source-contract.json` describes upstream serialization, not a
live capture. See [the immutable runtime source](https://github.com/openai/codex/blob/ff6aec96948b70d94983af2641a6b67c94faeff5/codex-rs/core/src/hook_runtime.rs)
and [the Review delegate source](https://github.com/openai/codex/blob/ff6aec96948b70d94983af2641a6b67c94faeff5/codex-rs/core/src/tasks/review.rs).

With no ACTIVE managed task, ordinary fresh role delegation remains available
without creating a managed reservation, owner, or binding. Named Thaliris
spawns still require `fork_turns="none"`. The Controller's semantic routing
agreement remains in force; UNKNOWN mechanical admission does not appoint a
second Controller or let Root take over substantial executor work.
During platform drift, the fallback admits only a named fresh spawn from an
unlinked Git worktree with a safely absent task slot and no existing recovery
fence. A different payload working directory, any native child identity,
inherited context, model override, existing state (including unreadable or
inactive state), or session reuse is denied. These deliberately bounded disk
observations grant no Controller authority or managed child binding.

An informed user can delegate offline administration when an old task cannot
be recovered through the managed chain. Disconnect the global Thaliris hooks
and global startup block first. The separate reviewed repository source runner
`tools/thaliris_offline_recovery.py` accepts the exact task UUID, revision,
state SHA-256, lifecycle SHA-256 (or `ABSENT`), and an explicit reason, with
`--operator-asserted-user-delegation --integration-disconnected`. Use a trusted
platform Python with `-I -B`; the runner compiles the repository's `.py` files
directly and never imports installed Thaliris or repository bytecode caches.
It holds the repository lock, verifies the exact packet, archives original
state and lifecycle bytes verbatim (including the incomplete goal), fences
extractable session and agent identities even in partial or malformed ledgers,
verifies the archives/fences, and releases the old slot. It never completes the
old task or creates a new Controller, task, child binding, or readonly exemption.
The final release reobserves lifecycle bytes, including an `ABSENT` packet.
Any late appearance retains the task slot for a new exact archival/fencing
decision; evidence already archived during the failed attempt remains intact.

The authority mode is
`OPERATOR_ASSERTED_USER_DELEGATED_ADMINISTRATION`. Flags are operator assertions,
not cryptographic human consent. Disk disconnection is an operational condition,
not proof of what a running Host loaded. Shared unrestricted OS shell access
provides governance, not privilege separation. Every automated actor, including
an ambiguous Root, is denied this operation while integration is present; an
external human operator can disconnect integration first. The ledger records
old owner assurance, unbound identity, incompatible fields, identity extraction
completeness, and Host termination as UNKNOWN. Attempt native termination or
observation for known old children where available; missing death proof does
not permanently lock informed offline recovery. A damaged existing fence is
preserved and requires a separate informed repair.
