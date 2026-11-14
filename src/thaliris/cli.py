"""JSON command boundary for Host-neutral Core operations.

Callers supply opaque actor labels; authorization belongs to their adapter.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from . import __version__, core, identity, identity_basis


_IDENTITY_MUTATIONS = ("identity-amend", "identity-challenge", "identity-relate")
_CONTINUITY_WRITES = ("task-evidence-register", "task-judge")


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ValueError(message)


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="thaliris-core", description="Host-neutral task records, evidence, explicit retrieval, memory, authority and project identity")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--pretty", action="store_true")
    parser.add_argument("--task-id", help="explicit task ledger selection; never an authority grant")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "uninstall", "stale", "milestone-check", "task-show", "version"):
        commands.add_parser(name)
    command = commands.add_parser("task-status")
    command.add_argument("--evidence-offset", type=int, default=0)
    command.add_argument("--view", choices=core.STATUS_VIEWS, default="full")
    command.add_argument("--since-revision", type=int)
    command.add_argument("--contract", help="FILE or - : the authority contract; lane advisories are computed for execution_mode adaptive")
    command.add_argument("--record-tamper", action="store_true",
                         help="append pending check-tamper observations first (a locked ledger write)")
    command = commands.add_parser("catalog")
    command.add_argument("path", nargs="?")
    command = commands.add_parser("document-get")
    command.add_argument("paths", nargs="+")
    command = commands.add_parser("task-start")
    command.add_argument("goal")
    command.add_argument("--milestone")
    command.add_argument("--input")
    command.add_argument("--actor", default="unspecified")
    for name in ("task-update", "task-promote", "task-evidence-register", "task-judge", "document-maintain"):
        command = commands.add_parser(name)
        command.add_argument("--actor", required=True)
        command.add_argument("--base-revision", type=int, required=True)
        command.add_argument("--input", required=True)
        if name in _CONTINUITY_WRITES:
            command.add_argument("--compact-evidence", action="store_true")
        if name == "task-judge":
            command.add_argument("--override-reason", help="recorded reason for judging satisfied while a declared check is not green")
    command = commands.add_parser("task-observe")
    command.add_argument("--actor", required=True)
    command.add_argument("--input", required=True)
    command.add_argument("--compact-evidence", action="store_true")
    command = commands.add_parser(
        "task-get",
        help="retrieve one selected-task object by exact object ID",
        description=(
            "Retrieve exactly one object from the selected task. Supply its exact object ID, "
            "not the Task ID; use task-status for the selected task or task-show for diagnostics."
        ),
    )
    command.add_argument("id", help="exact object ID; the selected Task ID is not an object ID")
    command = commands.add_parser("artifact-get")
    command.add_argument("id")
    command = commands.add_parser("task-artifact")
    command.add_argument("--base-revision", type=int, required=True)
    command.add_argument("--id", required=True)
    command.add_argument("--path", required=True)
    command.add_argument("--summary", required=True)
    command.add_argument("--actor", default="unspecified")
    command.add_argument("--producer")
    command.add_argument("--source-ref", action="append")
    command.add_argument("--supersedes", action="append")
    command = commands.add_parser("task-close")
    command.add_argument("--base-revision", type=int, required=True)
    command.add_argument("--expected-task-id")
    command.add_argument("--override-reason", help="recorded reason for closing while a declared check is not green")
    command.add_argument("--actor")
    command = commands.add_parser("task-check", help="declare or supersede checks (Controller; the adapter decides who that is)")
    command.add_argument("--actor", required=True)
    command.add_argument("--base-revision", type=int, required=True)
    command.add_argument("--input", required=True, help="FILE or - : one check {id, requirement_refs, command, cwd?, timeout_s?, files?} or {checks: [...]}")
    command.add_argument("--supersede", action="store_true", help="re-declare an existing check id, accepting its current file content")
    command = commands.add_parser("task-verify", help="run one declared check and record its result")
    command.add_argument("--actor", required=True)
    command.add_argument("--check", required=True)
    command.add_argument("--base-revision", type=int)
    command.add_argument("--compact-evidence", action="store_true")
    command = commands.add_parser("task-ingest-claims", help="adapter-called: ingest the typed claim block of a handoff's final message")
    command.add_argument("--handoff", required=True)
    source = command.add_mutually_exclusive_group(required=True)
    source.add_argument("--text", help="the message text")
    source.add_argument("--file", help="FILE or - : the raw message text")
    command.add_argument("--base-revision", type=int)
    command.add_argument("--compact-evidence", action="store_true")
    command = commands.add_parser("task-handoff-usage", help="adapter-called: record dispatch usage on a handoff")
    command.add_argument("--handoff", required=True)
    command.add_argument("--input", required=True, help="FILE or - : any of " + ", ".join(core.USAGE_FIELDS))
    command.add_argument("--base-revision", type=int)
    command = commands.add_parser("task-lane-counter", help="adapter-called: update the Controller tool-output token counter")
    amount = command.add_mutually_exclusive_group(required=True)
    amount.add_argument("--add", type=int)
    amount.add_argument("--set", dest="set_to", type=int)
    command = commands.add_parser("rollback")
    command.add_argument("backup")
    command = commands.add_parser("identity-status")
    command.add_argument("--session-key", help="adapter's native session key, for session-scope suggestion preference")
    command = commands.add_parser("identity-get")
    command.add_argument("--version", type=int)
    command.add_argument("--item", action="append")
    command.add_argument("--amendment")
    command.add_argument("--challenge")
    command = commands.add_parser("identity-trace")
    command.add_argument("ref")
    command.add_argument("--direction", choices=("up", "down", "both"), default="both")
    command.add_argument("--depth", type=int, default=1)
    for name in _IDENTITY_MUTATIONS:
        command = commands.add_parser(name)
        command.add_argument("--actor", required=True)
        command.add_argument("--base-revision", type=int, required=True)
        command.add_argument("--input", required=True)
    command = commands.add_parser("identity-note")
    command.add_argument("--actor")
    command.add_argument("--input", help="FILE or - : {quote, kind?, context?, refs?} or {retract, reason}")
    command.add_argument("--list", action="store_true")
    command.add_argument("--include-retracted", action="store_true")
    command = commands.add_parser("identity-suggest")
    command.add_argument("--actor", required=True)
    setting = command.add_mutually_exclusive_group(required=True)
    for value in ("on", "off", "clear"):
        setting.add_argument(f"--{value}", dest="setting", action="store_const", const=value)
    command.add_argument("--scope", choices=identity_basis.SCOPES, required=True)
    command.add_argument("--session-key")
    command = commands.add_parser("identity-offer")
    command.add_argument("--session-key")
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--pretty" in argv:
        argv = ["--pretty", *[item for item in argv if item != "--pretty"]]
    try:
        args = _parser().parse_args(argv)
        root = args.root.resolve()
        core.select_task(root, args.task_id)
        name = args.command
        if name in {"document-maintain", *_IDENTITY_MUTATIONS} and args.task_id is None:
            raise ValueError("explicit --task-id required for task mutation")
        if name.startswith("task-") and name not in {"task-start", "task-show", "task-status", "task-get"} and args.task_id is None:
            raise ValueError("explicit --task-id required for task mutation")
        if name == "version":
            out = {"ok": True, "version": __version__}
        elif name == "task-status":
            if args.record_tamper and args.task_id is None:
                raise ValueError("explicit --task-id required for task mutation")
            out = core.task_status(root, args.evidence_offset, view=args.view, since_revision=args.since_revision,
                                   contract=core._read_input(args.contract) if args.contract else None,
                                   record_tamper=args.record_tamper)
        elif name in {"init", "uninstall", "stale", "milestone-check", "task-show"}:
            out = getattr(core, name.replace("-", "_"))(root)
        elif name == "catalog":
            out = core.catalog(root, args.path)
        elif name == "document-get":
            out = core.document_get(root, args.paths)
        elif name == "task-start":
            out = core.task_start(root, args.goal, args.milestone, args.input, actor=args.actor)
        elif name == "task-judge":
            out = core.task_judge(root, args.actor, args.base_revision, args.input, compact_evidence=args.compact_evidence,
                                  override_reason=args.override_reason)
        elif name in _CONTINUITY_WRITES:
            out = getattr(core, name.replace("-", "_"))(root, args.actor, args.base_revision, args.input,
                                                        compact_evidence=args.compact_evidence)
        elif name == "task-check":
            out = core.task_check(root, args.actor, args.base_revision, args.input, supersede=args.supersede)
        elif name == "task-verify":
            out = core.task_verify(root, args.actor, args.check, base_revision=args.base_revision,
                                   compact_evidence=args.compact_evidence)
        elif name == "task-ingest-claims":
            out = core.task_ingest_claims(root, args.handoff, args.text, input_file=args.file,
                                          base_revision=args.base_revision, compact_evidence=args.compact_evidence)
        elif name == "task-handoff-usage":
            out = core.task_handoff_usage(root, args.handoff, args.input, base_revision=args.base_revision)
        elif name == "task-lane-counter":
            out = core.task_lane_counter(root, add=args.add, set_to=args.set_to)
        elif name in {"task-update", "task-promote", "document-maintain"}:
            out = getattr(core, name.replace("-", "_"))(root, args.actor, args.base_revision, args.input)
        elif name == "task-observe":
            out = core.task_observe(root, args.actor, args.input, compact_evidence=args.compact_evidence)
        elif name in {"task-get", "artifact-get"}:
            out = getattr(core, name.replace("-", "_"))(root, args.id)
        elif name == "task-artifact":
            out = core.task_artifact(root, args.base_revision, args.id, args.path, args.summary,
                producer=args.producer, registered_by=args.actor, evidence_refs=args.source_ref, supersedes=args.supersedes)
        elif name == "task-close":
            out = core.task_close(root, args.base_revision, expected_task_id=args.expected_task_id,
                                  override_reason=args.override_reason, actor=args.actor)
        elif name == "identity-status":
            out = identity.identity_status(root, session_key=args.session_key)
        elif name == "identity-get":
            out = identity.identity_get(root, version=args.version, items=args.item,
                                        amendment=args.amendment, challenge=args.challenge)
        elif name == "identity-trace":
            out = identity.identity_trace(root, args.ref, args.direction, args.depth)
        elif name in _IDENTITY_MUTATIONS:
            out = getattr(identity, name.replace("-", "_"))(root, args.actor, args.base_revision, args.input)
        elif name == "identity-note":
            if args.list == (args.input is not None):
                raise ValueError("identity-note takes exactly one of --input or --list")
            if args.list:
                out = identity_basis.identity_note_list(root, include_retracted=args.include_retracted)
            else:
                if args.actor is None or args.include_retracted:
                    raise ValueError("identity-note --input requires --actor and takes no --include-retracted")
                out = identity_basis.identity_note(root, args.actor, args.input)
        elif name == "identity-suggest":
            out = identity_basis.identity_suggest(root, args.actor, args.scope, args.setting, session_key=args.session_key)
        elif name == "identity-offer":
            out = {"ok": True, "identity_offer": identity_basis.identity_offer(root, args.session_key)}
        else:
            out = core.rollback(root, args.backup)
        print(json.dumps(out, sort_keys=True, indent=2 if args.pretty else None))
        return 0 if out.get("ok") else 3
    except core.TaskStateSchemaIncompatible as exc:
        print(json.dumps({"ok": False, **exc.diagnostic}, sort_keys=True))
        return 3
    except (ValueError, OSError, RuntimeError) as exc:
        # Structured errors add code/recovery/details; others keep {ok,error}.
        print(json.dumps(core.error_envelope(exc), sort_keys=True))
        return 2
