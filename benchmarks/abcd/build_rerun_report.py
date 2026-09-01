"""Build the sanitized before/after report for the four orchestration reruns."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


RUNS = ("C_T2", "C_T3", "D_T2", "D_T3")
QUALITY = {
    "C_T2": {"target": "1 passed", "full": "127 passed", "scope": "PASS", "isolation": "PASS"},
    "C_T3": {"target": "4 passed", "full": "130 passed", "scope": "PASS", "isolation": "PASS"},
    "D_T2": {"target": "1 passed", "full": "127 passed", "scope": "PASS", "isolation": "PASS"},
    "D_T3": {"target": "4 passed", "full": "130 passed", "scope": "PASS", "isolation": "PASS"},
}


def _by(items: list[dict[str, Any]], key: str, values: tuple[str, ...]) -> dict[str, dict[str, Any]]:
    return {item[key]: item for item in items if item.get(key) in values}


def _rerun_metrics(item: dict[str, Any]) -> dict[str, Any]:
    root = item["root"]
    usage = root["usage"]
    children = item["children"]
    child_input = sum(child["usage"]["input_tokens"] for child in children)
    child_output = sum(child["usage"]["output_tokens"] for child in children)
    child_turns = sum(child["model_calls"] for child in children)
    child_peak = max((child["peak_context"] for child in children), default=0)
    return {
        "root_model": root["model"],
        "root_input_tokens": usage["input_tokens"],
        "root_cached_input_tokens": usage["cached_input_tokens"],
        "root_uncached_input_tokens": usage["input_tokens"] - usage["cached_input_tokens"],
        "root_output_tokens": usage["output_tokens"],
        "root_reasoning_tokens": usage["reasoning_tokens"],
        "root_model_turns": root["model_calls"],
        "root_tool_calls": root["tool_calls"],
        "root_cumulative_input": usage["input_tokens"],
        "root_peak_context": root["peak_context"],
        "child_count": len(children),
        "child_input_tokens": child_input,
        "child_output_tokens": child_output,
        "child_model_turns": child_turns,
        "largest_child_context": child_peak,
        "total_input_tokens": usage["input_tokens"] + child_input,
        "total_output_tokens": usage["output_tokens"] + child_output,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--baseline-orchestration", type=Path, required=True)
    parser.add_argument("--rerun-orchestration", type=Path, required=True)
    parser.add_argument("--sessions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    baseline_orchestration = json.loads(args.baseline_orchestration.read_text(encoding="utf-8"))
    rerun_orchestration = json.loads(args.rerun_orchestration.read_text(encoding="utf-8"))
    sessions = json.loads(args.sessions.read_text(encoding="utf-8"))
    old_runs = _by(baseline["runs"], "id", RUNS)
    old_control = _by(baseline_orchestration["runs"], "run", RUNS)
    new_control = _by(rerun_orchestration["runs"], "run", RUNS)
    new_sessions = _by(sessions["runs"], "run", RUNS)
    rows: list[dict[str, Any]] = []
    for run in RUNS:
        old = old_runs[run]
        old_orch = old_control[run]
        new_orch = new_control[run]
        old_controls = {"spawn_agent": 1, **old_orch["control_call_counts"]}
        new_controls = {"spawn_agent": 1, **new_orch["control_call_counts"]}
        old_metrics = {
            "root_model": old["model"],
            "root_input_tokens": old["root_cumulative_input"],
            "root_cached_input_tokens": "UNAVAILABLE",
            "root_uncached_input_tokens": "UNAVAILABLE",
            "root_output_tokens": "UNAVAILABLE",
            "root_model_turns": old["root_model_turns"],
            "root_tool_calls": old["root_tool_calls"],
            "root_cumulative_input": old["root_cumulative_input"],
            "root_peak_context": old["root_peak_context"],
            "child_count": old["child_count"],
            "child_input_tokens": old["input_tokens"] - old["root_cumulative_input"],
            "largest_child_context": old["largest_child_context"],
            "total_input_tokens": old["input_tokens"],
            "total_output_tokens": old["output_tokens"],
        }
        rows.append({
            "run": run,
            "baseline": {"controls": old_controls, "classification_counts": old_orch["classification_counts"], "avoidable_input_proxy": old_orch["avoidable_input_proxy"], "metrics": old_metrics},
            "rerun": {"controls": new_controls, "classification_counts": new_orch["classification_counts"], "avoidable_input_proxy": new_orch["avoidable_input_proxy"], "metrics": _rerun_metrics(new_sessions[run]), "quality": QUALITY[run]},
        })
    model_breakdown: dict[str, dict[str, int]] = {}
    for item in sessions["runs"]:
        for session in [item["root"], *item["children"]]:
            model = session["model"]
            usage = session["usage"]
            target = model_breakdown.setdefault(model, {"input_tokens": 0, "cached_input_tokens": 0, "uncached_input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0, "model_calls": 0})
            target["input_tokens"] += usage["input_tokens"]
            target["cached_input_tokens"] += usage["cached_input_tokens"]
            target["output_tokens"] += usage["output_tokens"]
            target["reasoning_tokens"] += usage["reasoning_tokens"]
            target["model_calls"] += session["model_calls"]
    for target in model_breakdown.values():
        target["uncached_input_tokens"] = target["input_tokens"] - target["cached_input_tokens"]
    aggregate: dict[str, Any] = {}
    for phase in ("baseline", "rerun"):
        controls = {name: sum(row[phase]["controls"].get(name, 0) for row in rows) for name in ("spawn_agent", "wait_agent", "list_agents", "task-status", "send_message")}
        aggregate[phase] = {
            "controls": controls,
            "avoidable_input_proxy": sum(row[phase]["avoidable_input_proxy"] for row in rows),
            "root_model_turns": sum(row[phase]["metrics"]["root_model_turns"] for row in rows),
            "root_cumulative_input": sum(row[phase]["metrics"]["root_cumulative_input"] for row in rows),
            "total_input_tokens": sum(row[phase]["metrics"]["total_input_tokens"] for row in rows),
            "total_output_tokens": sum(row[phase]["metrics"]["total_output_tokens"] for row in rows),
            "root_peak_context_max": max(row[phase]["metrics"]["root_peak_context"] for row in rows),
            "child_input_tokens": sum(row[phase]["metrics"]["child_input_tokens"] for row in rows),
        }
    aggregate["ratios"] = {
        "root_cumulative_input": round(aggregate["rerun"]["root_cumulative_input"] / aggregate["baseline"]["root_cumulative_input"], 6),
        "total_input": round(aggregate["rerun"]["total_input_tokens"] / aggregate["baseline"]["total_input_tokens"], 6),
        "total_io": round((aggregate["rerun"]["total_input_tokens"] + aggregate["rerun"]["total_output_tokens"]) / (aggregate["baseline"]["total_input_tokens"] + aggregate["baseline"]["total_output_tokens"]), 6),
    }
    result = {
        "schema_version": 1,
        "baseline_commit": "ebfe9e9c4598e7896015d90cb89dd3c55eea0809",
        "policy_commit": "247abc4",
        "wait_timeout_policy": {
            "prior_child_latency_seconds": [104.2, 163.8, 118.3, 116.1, 257.3, 214.0, 239.8],
            "selected_first_wait_timeout_ms": 240000,
            "basis": "Observed prior C/D T2/T3 child task durations; 240 seconds covers the common range without using the tool maximum.",
        },
        "aggregate": aggregate,
        "runs": rows,
        "model_breakdown": model_breakdown,
        "models_not_observed": ["gpt-5.6-sol"],
        "limitations": [
            "Root/child input totals are telemetry sums; cached input is reported separately and is not treated as free.",
            "avoidable_input_proxy is the next root model-turn input after a redundant control call; it is not a causal token-saving estimate.",
            "Quality and scope are recorded from the real CLI acceptance output; no hidden-risk equivalence claim is made beyond those checks.",
        ],
    }
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
