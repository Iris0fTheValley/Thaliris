"""Summarize sanitized model and context metrics for benchmark session JSONL.

This is benchmark-only tooling. It discovers only direct child sessions of the
manifested root and never copies prompts, tool payloads, or raw output into the
ledger. Input-token totals are telemetry sums, not billing estimates.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _records(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _payload(row: dict[str, Any]) -> dict[str, Any]:
    value = row.get("payload")
    return value if isinstance(value, dict) else {}


def _model(rows: list[dict[str, Any]]) -> str:
    for row in rows:
        payload = _payload(row)
        if row.get("type") == "turn_context" and isinstance(payload.get("model"), str):
            return payload["model"]
    return "UNKNOWN"


def _usage(rows: list[dict[str, Any]]) -> tuple[dict[str, int], list[dict[str, Any]]]:
    totals = {key: 0 for key in ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens")}
    timeline: list[dict[str, Any]] = []
    preceding = "initial"
    active_tool: str | None = None
    for index, row in enumerate(rows):
        payload = _payload(row)
        if row.get("type") == "response_item":
            kind = payload.get("type")
            if kind in {"function_call", "custom_tool_call"}:
                active_tool = str(payload.get("name") or "tool")
                preceding = active_tool
            elif kind in {"function_call_output", "custom_tool_call_output"}:
                preceding = active_tool or "tool_result"
        if row.get("type") != "event_msg" or payload.get("type") != "token_count":
            continue
        info = payload.get("info")
        last = info.get("last_token_usage") if isinstance(info, dict) else None
        if not isinstance(last, dict) or not isinstance(last.get("input_tokens"), int):
            continue
        values = {
            "input_tokens": int(last.get("input_tokens", 0)),
            "cached_input_tokens": int(last.get("cached_input_tokens", 0)),
            "output_tokens": int(last.get("output_tokens", 0)),
            "reasoning_tokens": int(last.get("reasoning_output_tokens", 0)),
        }
        for key, value in values.items():
            totals[key] += value
        timeline.append({"call": len(timeline) + 1, "input_tokens": values["input_tokens"], "preceding_action": preceding})
        preceding = "model_turn"
        active_tool = None
    return totals, timeline


def _tool_calls(rows: list[dict[str, Any]]) -> int:
    count = 0
    for row in rows:
        payload = _payload(row)
        if row.get("type") == "response_item" and payload.get("type") in {"function_call", "custom_tool_call"}:
            count += 1
    return count


def _session(path: Path) -> dict[str, Any]:
    rows = _records(path)
    first = _payload(rows[0]) if rows else {}
    totals, timeline = _usage(rows)
    return {
        "file": path.name,
        "session_id": first.get("id"),
        "parent_thread_id": first.get("parent_thread_id"),
        "cwd_leaf": Path(str(first.get("cwd", ""))).name,
        "model": _model(rows),
        "usage": totals,
        "model_calls": len(timeline),
        "peak_context": max((item["input_tokens"] for item in timeline), default=0),
        "tool_calls": _tool_calls(rows),
        "timeline": timeline,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    runs = manifest.get("runs") if isinstance(manifest, dict) else None
    if not isinstance(runs, list):
        raise ValueError("manifest must contain a runs list")
    all_files = list(args.session_root.glob("*.jsonl"))
    output_runs: list[dict[str, Any]] = []
    for item in runs:
        run = item["run"]
        root = args.session_root / item["root_file"]
        root_session = _session(root)
        root_id = root_session.get("session_id")
        children = []
        for path in all_files:
            if path == root:
                continue
            session = _session(path)
            if session.get("parent_thread_id") == root_id and session.get("cwd_leaf") == run:
                children.append(session)
        output_runs.append({"run": run, "root": root_session, "children": children})
    encoded = json.dumps({"schema_version": 1, "runs": output_runs}, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    args.output.write_text(encoded, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
