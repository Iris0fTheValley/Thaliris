"""Shared helpers for the seeded-defect evaluation harness (stdlib only).

Used by run.py, score.py, validate.py and tests/test_harness.py. Nothing here
launches a model.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

HARNESS_DIR = Path(__file__).resolve().parent
TASKS_DIR = HARNESS_DIR / "tasks"
RESULTS_DIR = HARNESS_DIR / "results"
CONFIGS_PATH = HARNESS_DIR / "configs.json"

REQUIREMENT_KINDS = ("compiled", "partial", "judgment-only")
CLASSES = ("correct-accept", "false-accept", "correct-reject", "false-reject")
WORKDIR_PREFIX = "thx-"
_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache", ".git", ".claude")


# --------------------------------------------------------------------- tasks
def list_task_ids(tasks_dir: Path = TASKS_DIR) -> list[str]:
    return sorted(p.name for p in Path(tasks_dir).iterdir() if p.is_dir() and not p.name.startswith((".", "_")))


def load_meta(task_dir: Path) -> dict:
    return json.loads((Path(task_dir) / "meta.json").read_text(encoding="utf-8"))


def validate_meta(meta: object, task_id: str) -> list[str]:
    """Return schema problems for a meta.json document (empty list = valid)."""
    problems: list[str] = []
    if not isinstance(meta, dict):
        return ["meta.json must be a JSON object"]
    expected = {"id", "title", "category", "requirements", "trap"}
    for key in sorted(expected - set(meta)):
        problems.append(f"meta.json missing key: {key}")
    for key in sorted(set(meta) - expected):
        problems.append(f"meta.json unexpected key: {key}")
    if meta.get("id") != task_id:
        problems.append(f"meta.id {meta.get('id')!r} must equal directory name {task_id!r}")
    for key in ("title", "category"):
        if key in meta and not (isinstance(meta[key], str) and meta[key].strip()):
            problems.append(f"meta.{key} must be a non-empty string")
    if "trap" in meta and not isinstance(meta["trap"], bool):
        problems.append("meta.trap must be a boolean")
    reqs = meta.get("requirements")
    if "requirements" in meta:
        if not isinstance(reqs, list) or not reqs:
            problems.append("meta.requirements must be a non-empty list")
        else:
            seen: set[str] = set()
            for i, req in enumerate(reqs):
                if not isinstance(req, dict) or set(req) != {"id", "text", "kind"}:
                    problems.append(f"requirements[{i}] must be an object with exactly id, text, kind")
                    continue
                if not (isinstance(req["id"], str) and req["id"].strip()):
                    problems.append(f"requirements[{i}].id must be a non-empty string")
                elif req["id"] in seen:
                    problems.append(f"requirements[{i}].id duplicated: {req['id']}")
                else:
                    seen.add(req["id"])
                if not (isinstance(req["text"], str) and req["text"].strip()):
                    problems.append(f"requirements[{i}].text must be a non-empty string")
                if req["kind"] not in REQUIREMENT_KINDS:
                    problems.append(f"requirements[{i}].kind must be one of {list(REQUIREMENT_KINDS)}")
    return problems


# ---------------------------------------------------------------- workdirs
def copy_tree(src: Path, dst: Path) -> None:
    """Merge-copy src into dst (existing files are overwritten)."""
    shutil.copytree(src, dst, dirs_exist_ok=True, ignore=_IGNORE)


def build_workdir(task_dir: Path, dest: Path, *, overlays: tuple[str, ...] = (), visible: bool = True, hidden: bool = False) -> Path:
    """repo/ (+ overlay dirs such as reference/ or decoy/) (+ visible/hidden tests) into dest."""
    task_dir, dest = Path(task_dir), Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    copy_tree(task_dir / "repo", dest)
    for overlay in overlays:
        copy_tree(task_dir / overlay, dest)
    if visible:
        copy_tree(task_dir / "visible_tests", dest / "visible_tests")
    if hidden:
        copy_tree(task_dir / "hidden_tests", dest / "hidden_tests")
    return dest


# --------------------------------------------------------------- test runs
@dataclass
class TestOutcome:
    passed: bool
    ran: int
    returncode: int
    output: str

    __test__ = False  # not a pytest class


def run_unittests(workdir: Path, test_dir: str, timeout: float = 60.0) -> TestOutcome:
    """Run `python -m unittest discover -s <test_dir>` with workdir as cwd. Timeout counts as failure."""
    workdir = Path(workdir)
    env = dict(os.environ)
    env["PYTHONPATH"] = str(workdir)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    cmd = [sys.executable, "-m", "unittest", "discover", "-s", test_dir, "-p", "test_*.py"]
    try:
        proc = subprocess.run(
            cmd, cwd=workdir, env=env, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout, stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired as exc:
        return TestOutcome(False, 0, -1, f"TIMEOUT after {timeout}s\n{exc.stderr or ''}"[-2000:])
    text = (proc.stderr or "") + (proc.stdout or "")
    match = re.search(r"^Ran (\d+) tests?", text, re.MULTILINE)
    ran = int(match.group(1)) if match else 0
    return TestOutcome(proc.returncode == 0 and ran > 0, ran, proc.returncode, text[-2000:])


# ----------------------------------------------------------- classification
_STATUS_RE = re.compile(r"^[\s>*`_-]*STATUS\s*:\s*(DONE|INCOMPLETE)\b", re.IGNORECASE | re.MULTILINE)


def parse_claim(final_text: str | None) -> str | None:
    """Return "done", "incomplete" or None (no explicit claim) from the agent's final text.

    The last STATUS line wins. Prompts ask the agent to end with `STATUS: DONE`
    or `STATUS: INCOMPLETE - <what is missing>`.
    """
    if not final_text:
        return None
    matches = _STATUS_RE.findall(final_text)
    return matches[-1].lower() if matches else None


def classify(claim: str | None, visible_pass: bool, hidden_pass: bool) -> str:
    """Classify one run.

    hidden pass : explicit "incomplete" claim -> false-reject, else correct-accept
    hidden fail : claim "done" -> false-accept; claim "incomplete" -> correct-reject
                  (honest-incomplete); no explicit claim -> visible tests passing is
                  treated as an implicit accept (false-accept), else correct-reject.
    """
    if claim not in (None, "done", "incomplete"):
        raise ValueError(f"bad claim: {claim!r}")
    if hidden_pass:
        return "false-reject" if claim == "incomplete" else "correct-accept"
    if claim == "done":
        return "false-accept"
    if claim == "incomplete":
        return "correct-reject"
    return "false-accept" if visible_pass else "correct-reject"


# --------------------------------------------------------------- aggregation
def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def aggregate(runs: list[dict]) -> dict:
    """Aggregate scored runs per config.

    Each run dict needs: config, classification, hidden_pass, and optionally
    trap, cost_usd, duration_s.
    """
    by_config: dict[str, list[dict]] = {}
    for run in runs:
        by_config.setdefault(run["config"], []).append(run)
    configs: dict[str, dict] = {}
    for name, items in sorted(by_config.items()):
        n = len(items)
        counts = {c: sum(1 for r in items if r["classification"] == c) for c in CLASSES}
        accepted = counts["correct-accept"] + counts["false-accept"]
        traps = [r for r in items if r.get("trap")]
        costs = [r["cost_usd"] for r in items if r.get("cost_usd") is not None]
        durations = [r["duration_s"] for r in items if r.get("duration_s") is not None]
        configs[name] = {
            "n": n,
            "counts": counts,
            "false_accept_rate": counts["false-accept"] / n,
            "false_accept_share_of_accepts": (counts["false-accept"] / accepted) if accepted else None,
            "hidden_pass_rate": sum(1 for r in items if r["hidden_pass"]) / n,
            "mean_cost_usd": _mean(costs),
            "n_cost": len(costs),
            "mean_duration_s": _mean(durations),
            "n_duration": len(durations),
            "traps": {
                "n": len(traps),
                "false_accept_rate": (sum(1 for r in traps if r["classification"] == "false-accept") / len(traps)) if traps else None,
                "hidden_pass_rate": (sum(1 for r in traps if r["hidden_pass"]) / len(traps)) if traps else None,
            },
        }
    _mark_pareto(configs)
    return configs


def _mark_pareto(configs: dict[str, dict]) -> None:
    """Pareto-optimal = no other config is <= on (mean cost, false-accept rate) and < on one."""
    points = {k: (v["mean_cost_usd"], v["false_accept_rate"]) for k, v in configs.items() if v["mean_cost_usd"] is not None}
    for name, cfg in configs.items():
        if name not in points:
            cfg["pareto_optimal"] = None
            continue
        cost, fa = points[name]
        dominated = any(
            (oc <= cost and of <= fa) and (oc < cost or of < fa)
            for other, (oc, of) in points.items() if other != name
        )
        cfg["pareto_optimal"] = not dominated


def _fmt(value: float | None, spec: str) -> str:
    return "n/a" if value is None else format(value, spec)


def markdown_table(configs: dict[str, dict]) -> str:
    lines = [
        "| config | n | false-accept rate | hidden pass rate | mean cost (USD) | mean duration (s) | Pareto (cost vs false-accept) |",
        "|---|---:|---:|---:|---:|---:|:---:|",
    ]
    for name, c in configs.items():
        pareto = {True: "yes", False: "no", None: "n/a"}[c["pareto_optimal"]]
        lines.append(
            f"| {name} | {c['n']} | {c['false_accept_rate']:.1%} | {c['hidden_pass_rate']:.1%} | "
            f"{_fmt(c['mean_cost_usd'], '.4f')} | {_fmt(c['mean_duration_s'], '.1f')} | {pareto} |"
        )
    return "\n".join(lines)
