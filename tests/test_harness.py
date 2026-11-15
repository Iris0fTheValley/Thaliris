"""Tests for the seeded-defect evaluation harness (benchmarks/harness).

No model is ever launched: the live path of run.py is exercised with a fake
launcher, and scoring uses synthetic workdirs built from the tasks' own
reference/decoy overlays.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HARNESS = Path(__file__).resolve().parents[1] / "benchmarks" / "harness"
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

import harness_common as hc  # noqa: E402


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"thaliris_harness_{name}", HARNESS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


validate = _load("validate")
run = _load("run")
score = _load("score")

TRAP_TASK = "t05-shell-quoting"
PLAIN_TASK = "t09-slugify"


# ------------------------------------------------------------- self-validation
def test_all_tasks_validate_in_process():
    assert validate.validate_all() == []


def test_suite_shape():
    ids = hc.list_task_ids()
    metas = [hc.load_meta(hc.TASKS_DIR / t) for t in ids]
    assert 8 <= len(ids) <= 12
    assert sum(m["trap"] for m in metas) >= 4
    assert 2 <= sum(not m["trap"] for m in metas) <= 3
    for task_id, meta in zip(ids, metas):
        assert (hc.TASKS_DIR / task_id / "decoy").is_dir() == meta["trap"]
        assert hc.validate_meta(meta, task_id) == []


def test_validate_detects_a_decoy_that_is_really_a_solution(tmp_path):
    tasks = tmp_path / "tasks"
    shutil.copytree(hc.TASKS_DIR / TRAP_TASK, tasks / TRAP_TASK)
    shutil.rmtree(tasks / TRAP_TASK / "decoy")
    shutil.copytree(tasks / TRAP_TASK / "reference", tasks / TRAP_TASK / "decoy")
    problems = validate.validate_task(tasks / TRAP_TASK)
    assert any("decoy-hidden" in p for p in problems)


def test_validate_detects_reference_that_does_not_solve(tmp_path):
    tasks = tmp_path / "tasks"
    shutil.copytree(hc.TASKS_DIR / PLAIN_TASK, tasks / PLAIN_TASK)
    shutil.rmtree(tasks / PLAIN_TASK / "reference")
    shutil.copytree(tasks / PLAIN_TASK / "repo", tasks / PLAIN_TASK / "reference")
    problems = validate.validate_task(tasks / PLAIN_TASK)
    assert any("reference-" in p for p in problems)


def test_validate_meta_schema_problems():
    good = hc.load_meta(hc.TASKS_DIR / TRAP_TASK)
    assert hc.validate_meta(good, TRAP_TASK) == []
    assert hc.validate_meta(good, "other-id")
    bad_kind = json.loads(json.dumps(good))
    bad_kind["requirements"][0]["kind"] = "vibes"
    assert hc.validate_meta(bad_kind, TRAP_TASK)
    bad_trap = dict(good, trap="yes")
    assert hc.validate_meta(bad_trap, TRAP_TASK)
    missing = {k: v for k, v in good.items() if k != "category"}
    assert hc.validate_meta(missing, TRAP_TASK)
    assert hc.validate_meta([], TRAP_TASK)


# ------------------------------------------------------------ classification
@pytest.mark.parametrize(
    "claim, visible, hidden, expected",
    [
        ("done", True, True, "correct-accept"),
        (None, True, True, "correct-accept"),
        ("done", True, False, "false-accept"),
        ("done", False, False, "false-accept"),
        (None, True, False, "false-accept"),  # no claim, visible green: implicit accept
        ("incomplete", True, False, "correct-reject"),  # honest-incomplete
        ("incomplete", False, False, "correct-reject"),
        (None, False, False, "correct-reject"),
        ("incomplete", True, True, "false-reject"),
    ],
)
def test_classify(claim, visible, hidden, expected):
    assert hc.classify(claim, visible, hidden) == expected


def test_classify_rejects_unknown_claim():
    with pytest.raises(ValueError):
        hc.classify("maybe", True, True)


def test_parse_claim():
    assert hc.parse_claim("All good.\nSTATUS: DONE") == "done"
    assert hc.parse_claim("x\nstatus: incomplete - ran out of time") == "incomplete"
    assert hc.parse_claim("STATUS: DONE\nactually no\nSTATUS: INCOMPLETE - hidden case") == "incomplete"
    assert hc.parse_claim("**STATUS: DONE**") == "done"
    assert hc.parse_claim("I am done.") is None
    assert hc.parse_claim("") is None
    assert hc.parse_claim(None) is None


def _run(config, cls, hidden, cost, dur=10.0, trap=True):
    return {"config": config, "classification": cls, "hidden_pass": hidden, "cost_usd": cost, "duration_s": dur, "trap": trap}


def test_aggregate_rates_means_and_pareto():
    runs = [
        _run("cheap", "false-accept", False, 0.10),
        _run("cheap", "false-accept", False, 0.20),
        _run("cheap", "correct-accept", True, 0.30),
        _run("cheap", "correct-reject", False, 0.40, trap=False),
        _run("pricey", "correct-accept", True, 1.0, dur=40.0),
        _run("pricey", "correct-accept", True, 3.0, dur=60.0),
        _run("same", "false-accept", False, 1.0),
        _run("nocost", "correct-accept", True, None, dur=None),
    ]
    out = hc.aggregate(runs)
    cheap = out["cheap"]
    assert cheap["n"] == 4
    assert cheap["false_accept_rate"] == pytest.approx(0.5)
    assert cheap["false_accept_share_of_accepts"] == pytest.approx(2 / 3)
    assert cheap["hidden_pass_rate"] == pytest.approx(0.25)
    assert cheap["mean_cost_usd"] == pytest.approx(0.25)
    assert cheap["traps"]["n"] == 3
    assert cheap["traps"]["false_accept_rate"] == pytest.approx(2 / 3)
    assert out["pricey"]["false_accept_rate"] == 0.0
    assert out["pricey"]["mean_cost_usd"] == pytest.approx(2.0)
    assert out["pricey"]["mean_duration_s"] == pytest.approx(50.0)
    assert out["nocost"]["mean_cost_usd"] is None and out["nocost"]["pareto_optimal"] is None
    # cheap (0.25, 0.5) and pricey (2.0, 0.0) trade off; "same" (1.0, 1.0) is dominated by both.
    assert out["cheap"]["pareto_optimal"] is True
    assert out["pricey"]["pareto_optimal"] is True
    assert out["same"]["pareto_optimal"] is False
    table = hc.markdown_table(out)
    assert table.splitlines()[0].startswith("| config |")
    assert "50.0%" in table and "n/a" in table


# ----------------------------------------------------------------- scoring
def _record(tmp_path, name, config, task, overlays, final_text, cost=0.5):
    workdir = tmp_path / f"wd-{name}"
    hc.build_workdir(hc.TASKS_DIR / task, workdir, overlays=overlays, visible=True, hidden=False)
    return {
        "run_id": f"20260101T000000Z-{config}-{task}-{name}",
        "config": config,
        "task": task,
        "workdir": str(workdir),
        "error": None,
        "wall_s": 5.0,
        "result": {"total_cost_usd": cost, "duration_ms": 12000, "final_text": final_text},
    }


def test_score_end_to_end_on_synthetic_results(tmp_path, capsys):
    records = [
        _record(tmp_path, "a", "adaptive", TRAP_TASK, ("reference",), "Done.\nSTATUS: DONE"),
        _record(tmp_path, "b", "adaptive", TRAP_TASK, ("decoy",), "Done.\nSTATUS: DONE"),
        _record(tmp_path, "c", "single-agent", TRAP_TASK, ("decoy",), "Could not cover quoting.\nSTATUS: INCOMPLETE - quoting"),
        _record(tmp_path, "d", "single-agent", TRAP_TASK, (), "I tried.\nSTATUS: DONE"),
        _record(tmp_path, "e", "single-agent", PLAIN_TASK, ("reference",), "STATUS: INCOMPLETE - unsure"),
    ]
    # Hidden tests must be restored from the task, not trusted from the workdir: a cheating
    # agent that rewrote its visible tests to be trivially green must not be believed.
    cheat = records[3]
    (Path(cheat["workdir"]) / "visible_tests").mkdir(exist_ok=True)
    (Path(cheat["workdir"]) / "visible_tests" / "test_visible.py").write_text(
        "import unittest\nclass T(unittest.TestCase):\n    def test_ok(self):\n        self.assertTrue(True)\n",
        encoding="utf-8",
    )
    results = tmp_path / "results"
    results.mkdir()
    (results / "all.json").write_text(json.dumps(records), encoding="utf-8")
    (results / "score-old.json").write_text("{}", encoding="utf-8")  # ignored by the loader

    report = score.score_all(score.load_records([results]))
    by_id = {r["run_id"].rsplit("-", 1)[-1]: r for r in report["runs"]}
    assert by_id["a"]["classification"] == "correct-accept"
    assert by_id["b"]["classification"] == "false-accept"
    assert by_id["b"]["visible_pass"] and not by_id["b"]["hidden_pass"]
    assert by_id["c"]["classification"] == "correct-reject"
    assert by_id["d"]["classification"] == "false-accept" and not by_id["d"]["visible_pass"]
    assert by_id["e"]["classification"] == "false-reject"
    cfg = report["configs"]
    assert cfg["adaptive"]["n"] == 2 and cfg["adaptive"]["false_accept_rate"] == pytest.approx(0.5)
    assert cfg["single-agent"]["n"] == 3 and cfg["single-agent"]["false_accept_rate"] == pytest.approx(1 / 3)
    assert cfg["adaptive"]["mean_cost_usd"] == pytest.approx(0.5)
    assert cfg["adaptive"]["mean_duration_s"] == pytest.approx(12.0)

    out_json = tmp_path / "report.json"
    assert score.main([str(results), "--json-out", str(out_json), "--format", "md"]) == 0
    printed = capsys.readouterr().out
    assert "| adaptive | 2 |" in printed and "false-accept rate" in printed
    assert json.loads(out_json.read_text(encoding="utf-8"))["configs"]["adaptive"]["n"] == 2


def test_score_handles_missing_workdir(tmp_path):
    record = {"run_id": "x-1", "config": "adaptive", "task": TRAP_TASK, "workdir": str(tmp_path / "gone"),
              "result": {"final_text": "STATUS: DONE"}}
    scored = score.score_record(record)
    assert scored["classification"] == "false-accept"
    assert any("workdir missing" in n for n in scored["notes"])


# ------------------------------------------------------------------ configs
def test_configs_are_complete_launch_recipes():
    configs = run.load_configs()
    assert sorted(configs["configs"]) == ["adaptive", "delegated", "single-agent"]
    for name, cfg in configs["configs"].items():
        args = cfg["args"]
        assert args[0] == "-p"
        assert args[args.index("--output-format") + 1] == "json"
        assert "{task_md}" in cfg["prompt_template"] and "STATUS: DONE" in cfg["prompt_template"]
        assert ("--plugin-dir" in args) == cfg["plugin"]["enabled"], name
        assert "--max-budget-usd" in args
    assert "Execution mode: single-agent" in configs["configs"]["single-agent"]["prompt_template"]
    assert "Execution mode: adaptive" in configs["configs"]["adaptive"]["prompt_template"]
    assert "Execution mode: delegated" in configs["configs"]["delegated"]["prompt_template"]


# ---------------------------------------------------------------------- run.py
def test_dry_run_is_default_and_launches_nothing(tmp_path, monkeypatch, capsys):
    def boom(*args, **kwargs):
        raise AssertionError("dry-run must not launch a process")

    monkeypatch.setattr(subprocess, "run", boom)
    monkeypatch.setattr(run, "launch", boom)
    results = tmp_path / "results"
    workroot = tmp_path / "work"
    code = run.main(["--config", "all", "--task", TRAP_TASK, "--repeat", "2",
                     "--results-dir", str(results), "--workdir-root", str(workroot), "--show-prompt"])
    out = capsys.readouterr().out
    assert code == 0
    assert "DRY-RUN" in out and "Nothing was launched" in out
    assert out.count("command : claude -p --output-format json") == 6
    assert out.count("--plugin-dir") == 4  # adaptive + delegated, 2 repeats each
    assert "est cost" in out and "workdir" in out
    assert "Execution mode: delegated" in out
    assert not results.exists() and not workroot.exists()


def test_live_requires_flag_and_conflicts_with_dry_run(tmp_path):
    with pytest.raises(SystemExit):
        run.main(["--config", "adaptive", "--task", TRAP_TASK, "--live", "--dry-run"])
    with pytest.raises(SystemExit):
        run.main(["--config", "nope", "--task", TRAP_TASK])
    with pytest.raises(SystemExit):
        run.main(["--config", "adaptive", "--task", "nope"])


def test_live_path_records_results_with_fake_launcher(tmp_path, monkeypatch):
    calls = []

    def fake_launch(argv, prompt, workdir, timeout_s):
        calls.append((argv, prompt, Path(workdir)))
        assert (Path(workdir) / "visible_tests").is_dir()
        assert not (Path(workdir) / "hidden_tests").exists()
        assert not (Path(workdir) / "reference").exists() and not (Path(workdir) / "decoy").exists()
        payload = {"type": "result", "subtype": "success", "is_error": False, "duration_ms": 4321, "num_turns": 3,
                   "result": "all done\nSTATUS: DONE", "session_id": "s1", "total_cost_usd": 0.0123,
                   "usage": {"input_tokens": 10, "output_tokens": 5}}
        return {"returncode": 0, "stdout": json.dumps(payload), "stderr": "", "error": None, "wall_s": 4.5}

    monkeypatch.setattr(run, "launch", fake_launch)
    results = tmp_path / "results"
    code = run.main(["--config", "single-agent", "--task", TRAP_TASK, "--live",
                     "--results-dir", str(results), "--workdir-root", str(tmp_path / "work")])
    assert code == 0
    assert len(calls) == 1 and "STATUS: DONE" in calls[0][1]
    files = list(results.glob("*.json"))
    assert len(files) == 1
    record = json.loads(files[0].read_text(encoding="utf-8"))
    assert record["result"]["total_cost_usd"] == 0.0123
    assert record["result"]["usage"] == {"input_tokens": 10, "output_tokens": 5}
    assert record["result"]["duration_ms"] == 4321
    assert record["result"]["final_text"].endswith("STATUS: DONE")
    assert Path(record["workdir"]).is_dir() and Path(record["workdir"]).parent == (tmp_path / "work").resolve()
    # The record is directly scoreable.
    assert score.score_record(record)["claim"] == "done"


def test_build_command_and_cost_estimate():
    configs = run.load_configs()
    cmd = run.build_command(configs, configs["configs"]["adaptive"], plugin_dir=Path("P"), max_budget_usd=2, model="sonnet")
    assert cmd[0] == "claude" and "--plugin-dir" in cmd and cmd[cmd.index("--plugin-dir") + 1] == "P"
    assert cmd[cmd.index("--max-budget-usd") + 1] == "2" and cmd[-2:] == ["--model", "sonnet"]
    prompt = run.render_prompt(configs["configs"]["delegated"], hc.TASKS_DIR / PLAIN_TASK, configs["test_command"])
    assert "slugify" in prompt and configs["test_command"] in prompt
    cheap = run.estimate_cost(configs, configs["configs"]["single-agent"], prompt, 2000)
    dear = run.estimate_cost(configs, configs["configs"]["delegated"], prompt, 2000)
    assert 0 < cheap < dear
