# Codex native probe - 2026-09-08

This is a bounded observation record, not a statement about every Codex
installation or hook surface.

## Environment

- Codex CLI: `0.153.4`
- Thaliris adapter protocol: `2`
- Probe root: disposable local Git repository

The probe initialized the disposable root through the adapter and asked Codex
to use Bash for one successful and one non-zero shell command. It recorded no
user prompt, command text, tool output, child transcript, or payload body.

## Result

Codex created a current session with project hooks enabled. The adapter observed
`SessionStart`, `PreToolUse`, `PostToolUse`, and `SubagentStart`. The runtime
also recorded two authorized managed child lifecycles, each with matching
`SubagentStart` and `SubagentStop`, and native `agent_type` was
`thaliris-investigator`. This is bounded evidence that the generated profile
name and the authorized-spawn lifecycle path were recognized in this build.

Both observed Bash PostToolUse callbacks supplied `tool_response` as a string.
There was no structured terminal exit/status field or response-key set from
which a trusted outcome could be determined. The adapter correctly recorded
both as diagnostic `UNKNOWN` observations and created no Core verification
result.

The following facts remain `NOT_OBSERVED` for this installation and adapter
protocol version:

- delivery of SubagentStart `additionalContext` into the child's model-visible
  context (the hook emitted it, but this probe did not use a child marker);
- a Bash PostToolUse terminal exit/status field.

The adapter therefore keeps automatic Bash terminal status `UNAVAILABLE`.
Current-session readiness still requires a task-bound observation rather than a
historical runtime artifact. Unit tests exercise only the adapter's handling of
synthetic, explicitly shaped payloads; they are not native runtime proof.

## Protocol 3 follow-up

A second disposable-root probe used the same Codex CLI `0.153.4` with the
current adapter protocol. It started one requested `thaliris-investigator`
child with `fork_turns="none"`. The only complete sentinel was stored in the
Core task goal; the child instruction named only its prefix and asked for a
binary report. The child reported that the sentinel was missing.

That probe root also produced no current adapter runtime observation or
task-local lifecycle record. Consequently, this invocation does **not** prove
that project `SubagentStart` hooks ran, that their `additionalContext` reached
the child, or that the requested profile was loaded rather than merely accepted
by the native spawn interface. These capabilities remain `NOT_OBSERVED` for
this CLI invocation. The adapter must therefore report managed runtime
readiness as unknown/not ready until a compatible live hook observation exists.

The follow-up retained no prompt body, child transcript, shell command, or
payload body. It does not change the independent Bash finding above: a
structured terminal result remains unavailable for trusted shell attestation.
