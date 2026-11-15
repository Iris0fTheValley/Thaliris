#!/usr/bin/env python3
"""Launch (or dry-run) one harness configuration on one or more seeded-defect tasks.

    python run.py --config adaptive --task t01-explicit-selection-override --repeat 3
    python run.py --config all --task all                 # dry-run: prints plan, launches nothing
    python run.py --config adaptive --task t01-... --live # REAL model call; costs money

The default is a dry run. A live launch needs the explicit --live flag. In live
mode each run copies repo/ + visible_tests/ into a fresh temp workdir, runs
`claude -p` there with the prompt on stdin, and writes results/<run-id>.json.
The script only writes inside the results dir and the temp workdirs it creates.
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import harness_common as hc  # noqa: E402


def load_configs(path: Path = hc.CONFIGS_PATH) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def resolve_plugin_dir(configs: dict, override: str | None = None) -> Path:
    if override:
        return Path(override).resolve()
    env = os.environ.get(configs.get("plugin_dir_env", ""))
    if env:
        return Path(env).resolve()
    # harness/ -> benchmarks/ -> core/Thaliris/ -> core/ -> repo root
    return (hc.HARNESS_DIR.parents[3] / configs["plugin_dir_default"]).resolve()


def render_prompt(config: dict, task_dir: Path, test_command: str) -> str:
    task_md = (task_dir / "task.md").read_text(encoding="utf-8").rstrip("\n")
    return config["prompt_template"].format(task_md=task_md, test_command=test_command)


def build_command(configs: dict, config: dict, *, plugin_dir: Path, max_budget_usd: float, model: str | None, claude_bin: str | None = None) -> list[str]:
    """The exact argv for one launch (the prompt itself goes on stdin)."""
    values = {"plugin_dir": str(plugin_dir), "max_budget_usd": f"{max_budget_usd:g}"}
    argv = [claude_bin or configs["claude_bin"]] + [a.format(**values) for a in config["args"]]
    if model:
        argv += ["--model", model]
    return argv


def estimate_cost(configs: dict, config: dict, prompt: str, repo_chars: int) -> float:
    """Order-of-magnitude USD estimate; the real cost is total_cost_usd from the run."""
    model = config["cost_model"]
    price = configs["pricing_assumption_usd_per_mtok"]
    context = model["base_context_tokens"] + model["plugin_context_tokens"] + (len(prompt) + repo_chars) / 4
    turns = model["est_turns"]
    return turns * (context * price["input"] * price.get("effective_input_fraction_after_caching", 1.0) + model["est_output_tokens_per_turn"] * price["output"]) / 1_000_000


def _repo_chars(task_dir: Path) -> int:
    total = 0
    for sub in ("repo", "visible_tests"):
        for path in (task_dir / sub).rglob("*.py"):
            total += len(path.read_text(encoding="utf-8", errors="replace"))
    return total


def _select(requested: str, available: list[str], what: str) -> list[str]:
    if requested == "all":
        return list(available)
    chosen = [part.strip() for part in requested.split(",") if part.strip()]
    for item in chosen:
        if item not in available:
            raise SystemExit(f"unknown {what} {item!r}; available: {', '.join(available)}")
    return chosen


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _summarise(parsed: dict) -> dict:
    return {
        "total_cost_usd": parsed.get("total_cost_usd", parsed.get("cost_usd")),
        "usage": parsed.get("usage"),
        "duration_ms": parsed.get("duration_ms"),
        "duration_api_ms": parsed.get("duration_api_ms"),
        "num_turns": parsed.get("num_turns"),
        "is_error": parsed.get("is_error"),
        "subtype": parsed.get("subtype"),
        "session_id": parsed.get("session_id"),
        "final_text": parsed.get("result"),
    }


def launch(argv: list[str], prompt: str, workdir: Path, timeout_s: float) -> dict:
    """Run claude in workdir. Returns {returncode, stdout, stderr, error, wall_s}."""
    resolved = shutil.which(argv[0])
    if resolved is None:
        return {"returncode": None, "stdout": "", "stderr": "", "error": f"{argv[0]!r} not found on PATH", "wall_s": 0.0}
    started = datetime.now(timezone.utc)
    try:
        proc = subprocess.run(
            [resolved, *argv[1:]], input=prompt, cwd=workdir, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout_s,
        )
        out = {"returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr[-4000:], "error": None}
    except subprocess.TimeoutExpired as exc:
        out = {"returncode": None, "stdout": (exc.stdout or "") if isinstance(exc.stdout, str) else "", "stderr": "", "error": f"timeout after {timeout_s}s"}
    out["wall_s"] = (datetime.now(timezone.utc) - started).total_seconds()
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", required=True, help="config id, comma list, or 'all'")
    parser.add_argument("--task", required=True, help="task id, comma list, or 'all'")
    parser.add_argument("--repeat", type=int, default=1, help="runs per (config, task); default 1")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="print the plan only (this is the default)")
    mode.add_argument("--live", action="store_true", help="REALLY launch claude -p (costs money)")
    parser.add_argument("--show-prompt", action="store_true", help="dry-run: also print each full prompt")
    parser.add_argument("--model", default=None, help="optional --model value passed to claude")
    parser.add_argument("--max-budget-usd", type=float, default=None, help="per-run --max-budget-usd cap")
    parser.add_argument("--plugin-dir", default=None, help="plugin directory for plugin-enabled configs")
    parser.add_argument("--results-dir", type=Path, default=hc.RESULTS_DIR)
    parser.add_argument("--workdir-root", type=Path, default=None, help="parent of temp workdirs (default: system temp)")
    parser.add_argument("--configs", type=Path, default=hc.CONFIGS_PATH)
    parser.add_argument("--tasks-dir", type=Path, default=hc.TASKS_DIR)
    args = parser.parse_args(argv)
    if args.repeat < 1:
        parser.error("--repeat must be >= 1")

    configs = load_configs(args.configs)
    config_ids = _select(args.config, sorted(configs["configs"]), "config")
    task_ids = _select(args.task, hc.list_task_ids(args.tasks_dir), "task")
    max_budget = args.max_budget_usd if args.max_budget_usd is not None else configs["default_max_budget_usd"]
    plugin_dir = resolve_plugin_dir(configs, args.plugin_dir)
    workdir_root = (args.workdir_root or Path(tempfile.gettempdir())).resolve()
    results_dir = args.results_dir.resolve()
    live = bool(args.live)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    print(f"mode: {'LIVE (paid model calls)' if live else 'DRY-RUN (nothing is launched, nothing is written)'}")
    print(f"plugin dir: {plugin_dir} ({'exists' if plugin_dir.is_dir() else 'MISSING'})")
    print(f"results dir: {results_dir}")
    print(f"workdir root: {workdir_root}")
    total_estimate = 0.0
    planned = 0
    for config_id in config_ids:
        config = configs["configs"][config_id]
        if config["plugin"]["enabled"] and live and not plugin_dir.is_dir():
            raise SystemExit(f"config {config_id!r} needs the plugin but {plugin_dir} does not exist (use --plugin-dir)")
        cmd = build_command(configs, config, plugin_dir=plugin_dir, max_budget_usd=max_budget, model=args.model)
        for task_id in task_ids:
            task_dir = args.tasks_dir / task_id
            prompt = render_prompt(config, task_dir, configs["test_command"])
            estimate = estimate_cost(configs, config, prompt, _repo_chars(task_dir))
            for k in range(1, args.repeat + 1):
                planned += 1
                total_estimate += estimate
                run_id = f"{stamp}-{config_id}-{task_id}-r{k}"
                if not live:
                    print(f"\n[{run_id}]")
                    print(f"  workdir : {workdir_root / (hc.WORKDIR_PREFIX + task_id[:3] + '-<random>')}  (would hold repo/ + visible_tests/ of {task_id})")
                    print(f"  command : {shlex.join(cmd)}")
                    print(f"  stdin   : prompt ({len(prompt)} chars) rendered from configs.json + {task_id}/task.md")
                    if args.show_prompt:
                        print("  ---- prompt ----\n" + "\n".join("  | " + line for line in prompt.splitlines()) + "\n  ---- end prompt ----")
                    print(f"  est cost: ~${estimate:.2f} (rough, assumes prompt caching; cap --max-budget-usd {max_budget:g})")
                    continue

                workdir_root.mkdir(parents=True, exist_ok=True)
                workdir = Path(tempfile.mkdtemp(prefix=f"{hc.WORKDIR_PREFIX}{task_id[:3]}-", dir=workdir_root))
                hc.build_workdir(task_dir, workdir, visible=True, hidden=False)
                print(f"[{run_id}] launching in {workdir} ...", flush=True)
                outcome = launch(cmd, prompt, workdir, float(configs["default_timeout_s"]))
                parsed = None
                parse_error = None
                if outcome["stdout"].strip():
                    try:
                        parsed = json.loads(outcome["stdout"])
                        if not isinstance(parsed, dict):
                            parse_error = f"expected a JSON object, got {type(parsed).__name__}"
                            parsed = None
                    except ValueError as exc:
                        parse_error = f"stdout is not JSON: {exc}"
                record = {
                    "run_id": run_id,
                    "config": config_id,
                    "task": task_id,
                    "repeat_index": k,
                    "started_utc": stamp,
                    "workdir": str(workdir),
                    "command": cmd,
                    "model": args.model,
                    "max_budget_usd": max_budget,
                    "prompt": prompt,
                    "returncode": outcome["returncode"],
                    "wall_s": outcome["wall_s"],
                    "error": outcome["error"] or parse_error,
                    "stderr_tail": outcome["stderr"],
                    "result": _summarise(parsed) if parsed else None,
                    "claude_json": parsed,
                }
                results_dir.mkdir(parents=True, exist_ok=True)
                out_path = results_dir / f"{run_id}.json"
                if not _inside(out_path, results_dir):
                    raise SystemExit(f"refusing to write outside the results dir: {out_path}")
                out_path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
                cost = record["result"]["total_cost_usd"] if record["result"] else None
                print(f"[{run_id}] done: rc={record['returncode']} cost={cost} error={record['error']} -> {out_path}")
    if not live:
        print(f"\n{planned} planned run(s); rough total estimate ~${total_estimate:.2f}. Nothing was launched. Add --live to run for real.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
