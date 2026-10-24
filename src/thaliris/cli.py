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
    command = commands.add_parser("task-observe")
    command.add_argument("--actor", required=True)
    command.add_argument("--input", required=True)
    command.add_argument("--compact-evidence", action="store_true")
    for name in ("task-get", "artifact-get"):
        command = commands.add_parser(name)
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
            out = core.task_status(root, args.evidence_offset, view=args.view, since_revision=args.since_revision)
        elif name in {"init", "uninstall", "stale", "milestone-check", "task-show"}:
            out = getattr(core, name.replace("-", "_"))(root)
        elif name == "catalog":
            out = core.catalog(root, args.path)
        elif name == "document-get":
            out = core.document_get(root, args.paths)
        elif name == "task-start":
            out = core.task_start(root, args.goal, args.milestone, args.input, actor=args.actor)
        elif name in _CONTINUITY_WRITES:
            out = getattr(core, name.replace("-", "_"))(root, args.actor, args.base_revision, args.input,
                                                        compact_evidence=args.compact_evidence)
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
            out = core.task_close(root, args.base_revision, expected_task_id=args.expected_task_id)
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
