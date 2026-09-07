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
