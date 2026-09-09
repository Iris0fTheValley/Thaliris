import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "benchmarks" / "abcd" / "summarize_sessions.py"
SPEC = importlib.util.spec_from_file_location("summarize_sessions", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _args(tmp_path: Path) -> list[str]:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"runs": [{"run": "r", "root_file": "root.jsonl"}]}))
    return [
        "--session-root", str(tmp_path / "sessions"),
        "--manifest", str(manifest),
        "--output", str(tmp_path / "out.json"),
    ]


def test_missing_root_fails_closed(tmp_path: Path):
    (tmp_path / "sessions").mkdir()
    with pytest.raises(SystemExit, match="ROOT_MISSING"):
        MODULE.main(_args(tmp_path))


def test_persistent_state_arguments_must_be_a_pair(tmp_path: Path):
    (tmp_path / "sessions").mkdir()
    args = _args(tmp_path) + ["--state-db", str(tmp_path / "state.sqlite")]
    with pytest.raises(SystemExit):
        MODULE.main(args)
