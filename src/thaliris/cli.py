"""JSON command boundary for Host-neutral Core operations.

Callers supply opaque actor labels; authorization belongs to their adapter.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from . import __version__, core


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ValueError(message)


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="thaliris-core", description="Host-neutral task records, evidence, explicit retrieval, memory and authority")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--pretty", action="store_true")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "uninstall", "stale", "milestone-check", "task-show", "task-status", "version"):
        commands.add_parser(name)
    command = commands.add_parser("catalog")
    command.add_argument("path", nargs="?")
    command = commands.add_parser("document-get")
    command.add_argument("paths", nargs="+")
    command = commands.add_parser("task-start")
    command.add_argument("goal")
    command.add_argument("--milestone")
    command.add_argument("--input")
    command.add_argument("--actor", default="unspecified")
    for name in ("task-update", "task-promote"):
        command = commands.add_parser(name)
        command.add_argument("--actor", required=True)
        command.add_argument("--base-revision", type=int, required=True)
        command.add_argument("--input", required=True)
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
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--pretty" in argv:
        argv = ["--pretty", *[item for item in argv if item != "--pretty"]]
    try:
        args = _parser().parse_args(argv)
        root = args.root.resolve()
        name = args.command
        if name == "version":
            out = {"ok": True, "version": __version__}
        elif name in {"init", "uninstall", "stale", "milestone-check", "task-show", "task-status"}:
            out = getattr(core, name.replace("-", "_"))(root)
        elif name == "catalog":
            out = core.catalog(root, args.path)
        elif name == "document-get":
            out = core.document_get(root, args.paths)
        elif name == "task-start":
            out = core.task_start(root, args.goal, args.milestone, args.input, actor=args.actor)
        elif name in {"task-update", "task-promote"}:
            out = getattr(core, name.replace("-", "_"))(root, args.actor, args.base_revision, args.input)
        elif name in {"task-get", "artifact-get"}:
            out = getattr(core, name.replace("-", "_"))(root, args.id)
        elif name == "task-artifact":
            out = core.task_artifact(root, args.base_revision, args.id, args.path, args.summary,
                producer=args.producer, registered_by=args.actor, evidence_refs=args.source_ref, supersedes=args.supersedes)
        elif name == "task-close":
            out = core.task_close(root, args.base_revision, expected_task_id=args.expected_task_id)
        else:
            out = core.rollback(root, args.backup)
        print(json.dumps(out, sort_keys=True, indent=2 if args.pretty else None))
        return 0 if out.get("ok") else 3
    except core.TaskStateSchemaIncompatible as exc:
        print(json.dumps({"ok": False, **exc.diagnostic}, sort_keys=True))
        return 3
    except (ValueError, OSError, RuntimeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 2
