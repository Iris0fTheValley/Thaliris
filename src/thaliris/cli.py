"""Console interface: every normal stdout response is exactly one JSON value."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from . import __version__
from .core import init, migrate, milestone_check, prepare, rollback, stale, uninstall, task_close, task_show, task_start, task_update
from .doctor import report
from .intent_audit import handle_hook


class _Parser(argparse.ArgumentParser):
    """Normal errors are machine-readable too; help remains argparse-native."""
    def error(self, message: str) -> None:
        raise ValueError(message)


def _parser() -> argparse.ArgumentParser:
    p = _Parser(prog="context", description="Thaliris: Git-native context packs for Codex workflows")
    p.add_argument("--pretty", action="store_true")
    p.add_argument("--root", type=Path, default=Path.cwd())
    sub = p.add_subparsers(dest="command", required=True)
    for name in ("init", "migrate", "doctor", "stale", "milestone-check", "memory-status", "uninstall"):
        sub.add_parser(name)
    q = sub.add_parser("prepare")
    q.add_argument("task", nargs="?")
    q.add_argument("--role", required=True, choices=("controller", "sol-high", "luna", "luna-investigator", "luna-curator", "terra-implementer", "terra-reviewer"))
    q = sub.add_parser("task-start")
    q.add_argument("goal")
    q.add_argument("--milestone")
    q.add_argument("--input")
    q.add_argument("--intent-capture-id")
    q = sub.add_parser("task-update")
    q.add_argument("--role", required=True, choices=("controller", "sol-high", "luna", "luna-investigator", "luna-curator", "terra-implementer", "terra-reviewer"))
    q.add_argument("--base-revision", required=True, type=int)
    q.add_argument("--input", required=True)
    sub.add_parser("task-show")
    q = sub.add_parser("task-close")
    q.add_argument("--base-revision", required=True, type=int)
    q = sub.add_parser("rollback")
    q.add_argument("backup")
    sub.add_parser("version")
    q = sub.add_parser("audit-hook", help=argparse.SUPPRESS)
    q.add_argument("event", choices=("SessionStart", "UserPromptSubmit", "PostToolUse", "Stop"))
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
            response = handle_hook(root, args.event, payload)
            if response:
                sys.stdout.write(response)
            return 0
        if args.command == "init": out = init(root)
        elif args.command == "migrate": out = migrate(root)
        elif args.command == "doctor": out = report(root)
        elif args.command == "stale": out = stale(root)
        elif args.command == "memory-status":
            data = stale(root); out = {"ok": data["ok"], "entries": len(data["entries"]), "stale": data["stale"]}
        elif args.command == "milestone-check": out = milestone_check(root)
        elif args.command == "prepare": out = prepare(root, args.task, args.role)
        elif args.command == "task-start": out = task_start(root, args.goal, args.milestone, args.input, args.intent_capture_id)
        elif args.command == "task-update": out = task_update(root, args.role, args.base_revision, args.input)
        elif args.command == "task-show": out = task_show(root)
        elif args.command == "task-close": out = task_close(root, args.base_revision)
        elif args.command == "rollback": out = rollback(root, args.backup)
        elif args.command == "uninstall": out = uninstall(root)
        else: out = {"ok": True, "version": __version__}
        print(json.dumps(out, sort_keys=True, indent=2 if args.pretty else None, separators=None if args.pretty else (",", ":")))
        return 0 if out.get("ok", False) else 3
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True, separators=(",", ":")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
