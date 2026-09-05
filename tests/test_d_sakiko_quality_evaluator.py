from __future__ import annotations

import importlib.util
from pathlib import Path


def _evaluator():
    path = Path(__file__).parents[1] / "benchmarks" / "abcd" / "d_sakiko_quality_evaluator.py"
    spec = importlib.util.spec_from_file_location("d_sakiko_quality_evaluator", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_candidate_probe_cannot_self_report_quality(tmp_path: Path) -> None:
    gpt = tmp_path / "GPT_SoVITS"
    (gpt / "live2d_support").mkdir(parents=True)
    (gpt / "live2d_support" / "model_selection.py").write_text("class RuntimeSelection: pass\n", encoding="utf-8")
    (gpt / "contract_probe.py").write_text(
        "def run_contract(name):\n    return {'passed': 2, 'total': 2}\n",
        encoding="utf-8",
    )
    result = _evaluator().evaluate(tmp_path)
    assert result["quality_profile"] == "LOW_VALUE_PROGRESS"
    assert result["implementation_independent"] is False
    assert all("SharedLive2DBehavior" not in values for values in result["entry_points"].values())
