"""Console interface: every normal stdout response is exactly one JSON value."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from . import __version__
from . import codex_adapter, lifecycle
from .core import artifact_get, catalog, document_get, milestone_check, rollback, stale, task_artifact, task_get, task_promote, task_show, task_status, task_update


class _Parser(argparse.ArgumentParser):
    """Normal errors are machine-readable too; help remains argparse-native."""
    def error(self, message: str) -> None:
        raise ValueError(message)


def _task_status(root: Path, *, suppress_protocol_notice: bool) -> dict[str, object]:
    """Attach the one-shot lifecycle notice at the Codex CLI boundary."""
    out = task_status(root)
    if not suppress_protocol_notice:
        notice = lifecycle.consume_protocol_deviation_notice(root, str(out["Task"]["id"]))
        if notice is not None:
            out["Protocol deviation"] = notice
    return out


def _parser() -> argparse.ArgumentParser:
    p = _Parser(
        prog="context",
        description=(
            "Thaliris: durable records, identities, provenance, explicit retrieval, "
            "and lifecycle binding for Codex workflows"
        ),
    )
    p.add_argument("--pretty", action="store_true")
    p.add_argument("--root", type=Path, default=Path.cwd())
    sub = p.add_subparsers(dest="command", required=True)
    for name in ("init", "doctor", "stale", "milestone-check", "memory-status", "uninstall"):
        sub.add_parser(name)
    q = sub.add_parser("catalog", help="discover bounded durable document metadata")
    q.add_argument("path", nargs="?")
    q = sub.add_parser("document-get", help="retrieve 1 to 8 explicitly selected durable documents")
    q.add_argument("path", nargs="+")
    q = sub.add_parser("task-start")
    q.add_argument("goal")
    q.add_argument("--milestone")
    q.add_argument("--input")
    q.add_argument("--hook-attestation", help=argparse.SUPPRESS)
    q = sub.add_parser("task-update")
    q.add_argument("--role", required=True, choices=codex_adapter.ROLE_CHOICES)
    q.add_argument("--base-revision", required=True, type=int)
    q.add_argument("--input", required=True)
    sub.add_parser("task-show")
    q = sub.add_parser("task-status", help="bounded Controller routing packet")
    q.add_argument("--suppress-protocol-notice", action="store_true", help=argparse.SUPPRESS)
    q = sub.add_parser("task-get", help="retrieve one current-task object by ID")
    q.add_argument("id")
    q = sub.add_parser("artifact-get", help="retrieve one bounded task Artifact body by ID")
    q.add_argument("id")
    q = sub.add_parser("task-artifact", help="register a bounded external task artifact pointer")
    q.add_argument("--role", default="controller", choices=codex_adapter.ROLE_CHOICES)
    q.add_argument("--base-revision", required=True, type=int)
    q.add_argument("--id", required=True)
    q.add_argument("--path", required=True)
    q.add_argument("--summary", required=True)
    q.add_argument("--producer-role", choices=codex_adapter.ROLE_CHOICES)
    q.add_argument("--source-ref", action="append", default=[])
    q.add_argument("--supersedes", action="append", default=[])
    q = sub.add_parser("task-close")
    q.add_argument("--base-revision", required=True, type=int)
    q = sub.add_parser("recover-pending-spawn", help="clear one exact failed pending spawn reservation")
    q.add_argument("handoff_id")
    q = sub.add_parser(
        "task-promote",
        help="persist Controller-selected durable records",
        description="Store exactly the records selected by the Controller; metadata is descriptive only.",
        epilog=(
            'Example: {"records":[{"id":"D1","path":".agent-memory/architecture/d1.md",'
            '"title":"Decision","text":"..."}],"index_update":{"path":".agent-memory/INDEX.md",'
            '"base_sha256":"<current-index-sha256>","content":"<complete model-authored INDEX.md>"}}'
        ),
    )
    q.add_argument("--role", required=True, choices=codex_adapter.ROLE_CHOICES)
    q.add_argument("--base-revision", required=True, type=int)
    q.add_argument("--input", required=True)
    q = sub.add_parser("rollback")
    q.add_argument("backup")
    sub.add_parser("version")
    q = sub.add_parser("audit-hook", help=argparse.SUPPRESS)
    q.add_argument("event", choices=("SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "SubagentStart", "SubagentStop", "Stop"))
    return p


def main(argv: list[str] | None = None) -> int:
    # Let formatting be placed before or after a subcommand without changing
    # the command schema or emitting non-JSON normal output.
    if argv is None:
        argv = sys.argv[1:]
    if "--pretty" in argv:
        argv = ["--pretty", *[arg for arg in argv if arg != "--pretty"]]
    try:
        args = _parser().parse_args(argv)
        root = args.root.resolve()
        if args.command == "audit-hook":
            try:
                payload = json.loads(sys.stdin.buffer.read().decode("utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                payload = None
            response = codex_adapter.audit_hook(root, args.event, payload)
            if response:
                sys.stdout.write(response)
            return 0
        if args.command == "init": out = codex_adapter.init(root)
        elif args.command == "doctor": out = codex_adapter.doctor(root)
        elif args.command == "stale": out = stale(root)
        elif args.command == "memory-status":
            data = stale(root); out = {"ok": data["ok"], "entries": len(data["entries"]), "not_fresh": data["not_fresh"]}
        elif args.command == "milestone-check": out = milestone_check(root)
        elif args.command == "catalog": out = catalog(root, args.path)
        elif args.command == "document-get": out = document_get(root, args.path)
        elif args.command == "task-start": out = codex_adapter.task_start(root, args.goal, args.milestone, args.input, args.hook_attestation)
        elif args.command == "task-update": out = task_update(root, codex_adapter.controller_actor(args.role), args.base_revision, args.input)
        elif args.command == "task-show": out = task_show(root)
        elif args.command == "task-status": out = _task_status(root, suppress_protocol_notice=args.suppress_protocol_notice)
        elif args.command == "task-get": out = task_get(root, args.id)
        elif args.command == "artifact-get": out = artifact_get(root, args.id)
        elif args.command == "task-artifact": out = task_artifact(root, args.base_revision, args.id, args.path, args.summary, producer=(codex_adapter.semantic_role(args.producer_role) if getattr(args, "producer_role", None) else None), registered_by=codex_adapter.controller_actor(args.role), evidence_refs=args.source_ref or None, supersedes=args.supersedes or None)
        elif args.command == "task-close": out = codex_adapter.task_close(root, args.base_revision)
        elif args.command == "recover-pending-spawn": out = lifecycle.recover_pending_spawn(root, args.handoff_id)
        elif args.command == "task-promote": out = task_promote(root, codex_adapter.controller_actor(args.role), args.base_revision, args.input)
        elif args.command == "rollback": out = rollback(root, args.backup)
        elif args.command == "uninstall": out = codex_adapter.uninstall(root)
        else: out = {"ok": True, "version": __version__}
        print(json.dumps(out, sort_keys=True, indent=2 if args.pretty else None, separators=None if args.pretty else (",", ":")))
        return 0 if out.get("ok", False) else 3
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True, separators=(",", ":")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
