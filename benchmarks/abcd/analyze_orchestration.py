"""Analyze root orchestration calls from exported Codex session JSONL.

This is a benchmark-only analyzer.  It does not drive Codex and it does not
claim that the next-turn input proxy is a causal token saving measurement.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

CONTROL_TOOLS = {"wait_agent", "list_agents", "task-status", "send_message"}
LIFECYCLE_TOOLS = CONTROL_TOOLS | {"spawn_agent", "task-start", "task-update", "task-artifact", "task-close"}
TARGET_PROXY_CLASSES = {"TIMEOUT_POLL", "DUPLICATE_QUERY"}


def _load_jsonl(path: Path) -> list[tuple[int, dict[str, Any]]]:
    records: list[tuple[int, dict[str, Any]]] = []
    for index, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            records.append((index, value))
    return records


def _payload(record: dict[str, Any]) -> dict[str, Any]:
    value = record.get("payload")
    return value if isinstance(value, dict) else {}


def _output_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(_output_text(item) for item in value)
    if isinstance(value, dict):
        if isinstance(value.get("output"), (str, list, dict)):
            return _output_text(value["output"])
        if isinstance(value.get("text"), str):
            return value["text"]
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return "" if value is None else str(value)


def _json_object(text: str, marker: str | None = None) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", text):
        try:
            value, _ = decoder.raw_decode(text[match.start() :])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            candidates.append(value)
    for value in reversed(candidates):
        if marker is None or marker in value:
            return value
    return None


def _short_state(child: str, task: dict[str, Any]) -> str:
    status = task.get("status") or "UNKNOWN"
    revision = task.get("revision")
    suffix = f":r{revision}" if revision is not None else ""
    return f"child={child};task={status}{suffix}"


def _control_names_from_exec(input_text: str) -> list[str]:
    names: list[str] = []
    for command in ("task-start", "task-update", "task-artifact", "task-status", "task-close"):
        if re.search(rf"\bcontext\s+{re.escape(command)}(?:\b|[\"'])", input_text, flags=re.IGNORECASE):
            names.append(command)
    return names


def _call_events(records: list[tuple[int, dict[str, Any]]]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    outputs: dict[str, str] = {}
    calls: list[dict[str, Any]] = []
    token_indices: list[tuple[int, int]] = []
    tokens_seen = 0
    for index, record in records:
        payload = _payload(record)
        if record.get("type") == "event_msg" and payload.get("type") == "token_count":
            info = payload.get("info")
            usage = info.get("last_token_usage") if isinstance(info, dict) else None
            if isinstance(usage, dict) and isinstance(usage.get("input_tokens"), int):
                tokens_seen += 1
                token_indices.append((index, usage["input_tokens"]))
        if record.get("type") != "response_item":
            continue
        kind = payload.get("type")
        if kind in {"function_call_output", "custom_tool_call_output"}:
            call_id = payload.get("call_id")
            if isinstance(call_id, str):
                outputs[call_id] = _output_text(payload.get("output"))
            continue
        if kind not in {"function_call", "custom_tool_call"}:
            continue
        name = payload.get("name")
        call_id = payload.get("call_id")
        arguments = payload.get("arguments")
        input_text = payload.get("input")
        new_calls: list[dict[str, Any]] = []
        if kind == "function_call" and isinstance(name, str) and name in LIFECYCLE_TOOLS:
            new_calls.append({"index": index, "tool": name, "call_id": call_id, "arguments": arguments})
        elif kind == "custom_tool_call" and name == "exec" and isinstance(input_text, str):
            for command in _control_names_from_exec(input_text):
                new_calls.append({"index": index, "tool": command, "call_id": call_id, "arguments": input_text})
        for call in new_calls:
            call["root_turn"] = tokens_seen + 1
        calls.extend(new_calls)
    for call in calls:
        next_tokens = next((value for index, value in token_indices if index > call["index"]), None)
        call["next_root_input_tokens"] = next_tokens
        call["result"] = outputs.get(call.get("call_id"), "")
    return calls, outputs


def _state_from_task_output(text: str) -> dict[str, Any] | None:
    value = _json_object(text, marker="Task")
    task = value.get("Task") if isinstance(value, dict) else None
    if not isinstance(task, dict):
        return None
    return {"status": task.get("status"), "revision": task.get("revision")}


def _result_summary(tool: str, result: str) -> str:
    """Keep the ledger structural; never persist raw tool output or paths."""
    if tool == "wait_agent":
        if "at least 10000" in result or "must be at least" in result:
            return "invalid-timeout"
        if "Wait timed out" in result or '"timed_out":true' in result:
            return "timeout"
        if "Wait completed" in result or '"timed_out":false' in result:
            return "completed"
    if tool == "list_agents":
        value = _json_object(result, marker="agents")
        agents = value.get("agents") if isinstance(value, dict) else None
        statuses = [item.get("agent_status") for item in agents if isinstance(item, dict)] if isinstance(agents, list) else []
        return "topology:" + ",".join(str(item) for item in statuses) if statuses else "unparseable"
    if tool in {"task-start", "task-update", "task-artifact", "task-status", "task-close"}:
        state = _state_from_task_output(result)
        if state is not None:
            return f"task={state.get('status')}:r{state.get('revision')}"
    if tool == "send_message":
        return "returned" if result else "empty"
    return "error" if result and ("error" in result.lower() or "failed" in result.lower()) else "returned"


def _classify(call: dict[str, Any], child: str, task: dict[str, Any], last_status: tuple[Any, Any] | None, task_changed: bool, spawned: bool, task_start_packet: bool) -> tuple[str, str, str, dict[str, Any], tuple[Any, Any] | None, bool, str, bool]:
    before = _short_state(child, task)
    tool = call["tool"]
    result = call.get("result", "")
    after_task = _state_from_task_output(result)
    after_child = child
    after = dict(task)
    category = "UNKNOWN"
    if tool == "wait_agent":
        if "at least 10000" in result or "must be at least" in result:
            category = "RECOVERY"
        elif re.search(r"timed[_ ]out[\"']?\s*[:=]\s*true", result, flags=re.IGNORECASE) or "Wait timed out" in result:
            category = "TIMEOUT_POLL"
        elif "Wait completed" in result or re.search(r"timed[_ ]out[\"']?\s*[:=]\s*false", result, flags=re.IGNORECASE):
            category = "PRODUCTIVE"
            after_child = "DONE"
        else:
            category = "UNKNOWN"
    elif tool == "spawn_agent":
        if "task_name" in result and "error" not in result.lower():
            category = "PRODUCTIVE"
            after_child = "ACTIVE"
        else:
            category = "RECOVERY"
    elif tool in {"task-start", "task-update", "task-artifact", "task-close"}:
        if after_task is not None:
            after = after_task
            category = "PRODUCTIVE"
            task_changed = True
            task_start_packet = tool == "task-start"
        else:
            category = "UNKNOWN"
    elif tool == "list_agents":
        value = _json_object(result, marker="agents")
        agents = value.get("agents") if isinstance(value, dict) else None
        statuses = [item.get("agent_status") for item in agents if isinstance(item, dict)] if isinstance(agents, list) else []
        if child == "UNKNOWN" or not statuses:
            category = "RECOVERY"
        elif "completed" in statuses or "done" in statuses:
            category = "PRODUCTIVE"
            after_child = "DONE"
        else:
            category = "DUPLICATE_QUERY"
    elif tool == "task-status":
        if after_task is not None:
            after = after_task
        state_key = (after.get("status"), after.get("revision"))
        if task_start_packet and last_status is None:
            category = "DUPLICATE_QUERY"
        elif last_status == state_key and not task_changed:
            category = "DUPLICATE_QUERY"
        elif spawned and last_status is None and not task_changed:
            category = "DUPLICATE_QUERY"
        else:
            category = "PRODUCTIVE"
        last_status = state_key
        task_changed = False
        task_start_packet = False
    elif tool == "send_message":
        category = "UNKNOWN"
    return category, before, _short_state(after_child, after), after, last_status, task_changed, after_child, task_start_packet


def analyze_run(run: str, root_path: Path) -> dict[str, Any]:
    records = _load_jsonl(root_path)
    calls, _ = _call_events(records)
    child = "NONE"
    task: dict[str, Any] = {"status": None, "revision": None}
    last_status: tuple[Any, Any] | None = None
    task_changed = False
    spawned = False
    task_start_packet = False
    # Reconstruct state in call order and use matched outputs for classification.
    events: list[dict[str, Any]] = []
    for call in sorted(calls, key=lambda item: item["index"]):
        category, before, after, task_after, last_status, task_changed, child_after, task_start_packet = _classify(
            call, child, task, last_status, task_changed, spawned, task_start_packet
        )
        tool = call["tool"]
        if tool in CONTROL_TOOLS:
            event = {
                "root_turn": call["root_turn"],
                "tool": tool,
                "classification": category,
                "result": _result_summary(tool, call.get("result", "")),
                "child_task_state_before": before,
                "child_task_state_after": after,
                "next_root_input_tokens": call.get("next_root_input_tokens"),
                "avoidable_input_proxy": call.get("next_root_input_tokens") if category in TARGET_PROXY_CLASSES else 0,
            }
            events.append(event)
        # Only successful spawn is visible in the root session output; its child
        # identity is enough to establish the normal single-child topology.
        if tool == "task-status" and task_after is not None:
            task = task_after
        if tool in {"task-start", "task-update", "task-artifact", "task-close"} and task_after is not None:
            task = task_after
        if tool == "spawn_agent" and category == "PRODUCTIVE":
            child = "ACTIVE"
            spawned = True
        elif tool == "wait_agent" and category == "PRODUCTIVE":
            child = "DONE"
        elif tool == "list_agents" and category != "UNKNOWN":
            child = child_after
    proxy = sum(item["avoidable_input_proxy"] or 0 for item in events)
    counts = {name: sum(1 for item in events if item["tool"] == name) for name in sorted(CONTROL_TOOLS)}
    classes = {name: sum(1 for item in events if item["classification"] == name) for name in ("PRODUCTIVE", "TIMEOUT_POLL", "DUPLICATE_QUERY", "RECOVERY", "UNKNOWN")}
    return {"run": run, "root_file": root_path.name, "control_call_counts": counts, "classification_counts": classes, "avoidable_input_proxy": proxy, "events": events}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    runs = manifest.get("runs") if isinstance(manifest, dict) else None
    if not isinstance(runs, list):
        raise ValueError("manifest must contain a runs list")
    analyzed = []
    for item in runs:
        if not isinstance(item, dict) or not isinstance(item.get("run"), str) or not isinstance(item.get("root_file"), str):
            raise ValueError("manifest run entries require run and root_file")
        path = args.session_root / item["root_file"]
        if not path.is_file():
            raise FileNotFoundError(path)
        analyzed.append(analyze_run(item["run"], path))
    result = {"schema_version": 1, "classification": ["PRODUCTIVE", "TIMEOUT_POLL", "DUPLICATE_QUERY", "RECOVERY", "UNKNOWN"], "proxy_definition": "Sum of next root model-turn input_tokens for TIMEOUT_POLL and DUPLICATE_QUERY only; not a causal token-saving estimate.", "runs": analyzed}
    encoded = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
