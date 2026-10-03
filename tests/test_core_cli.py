import json
from pathlib import Path
import subprocess
import sys

from thaliris import cli, core


def test_neutral_cli_uses_opaque_actor_and_has_no_host_commands(tmp_path, capsys):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    assert cli.main(["--root", str(tmp_path), "init"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"]
    assert cli.main(["--root", str(tmp_path), "task-start", "Shared records", "--actor", "external:42"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "ACTIVE"
    assert core.task_show(tmp_path)["state"]["goal"] == "Shared records"
    assert cli.main(["--root", str(tmp_path), "codex-bootstrap"]) == 2
    assert "invalid choice" in json.loads(capsys.readouterr().out)["error"]


def test_core_import_and_cli_work_when_all_adapter_imports_are_denied():
    script = '''
import importlib.abc, sys
class DenyHost(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(('thaliris_codex', 'thaliris_dsh')):
            raise AssertionError('Core attempted a Host import')
sys.meta_path.insert(0, DenyHost())
from thaliris import authority, core, cli, markdown, models
raise SystemExit(cli.main(['version']))
'''
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, check=True)
    assert json.loads(result.stdout)["version"] == "0.4.3"
