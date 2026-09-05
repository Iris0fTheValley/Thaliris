from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from thaliris import core
from thaliris import codex_adapter


def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    return tmp_path


def test_core_has_no_codex_adapter_import() -> None:
    source = Path(core.__file__).read_text(encoding="utf-8")
    assert "from .intent_audit" not in source
    assert "import codex_adapter" not in source


def test_core_close_checks_expected_task_identity(tmp_path: Path) -> None:
    root = repo(tmp_path)
    codex_adapter.init(root)
    started = core.task_start(root, "cas", None, None)
    with pytest.raises(ValueError, match="task revision conflict"):
        core.task_close(root, started["revision"], expected_task_id="00000000-0000-0000-0000-000000000000")
    assert json.loads((root / ".context/state.json").read_text(encoding="utf-8"))["status"] == "ACTIVE"


def test_codex_init_is_one_backup_for_core_and_adapter(tmp_path: Path) -> None:
    root = repo(tmp_path)
    result = codex_adapter.init(root)
    assert result["ok"] and len(list((root / ".context/backups").glob("*.json"))) == 1
