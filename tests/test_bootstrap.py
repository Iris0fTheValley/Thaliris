import json
from pathlib import Path

from thaliris import codex_bootstrap as bootstrap
from thaliris import cli


def test_zero_state_invokes_init_once_and_requires_fresh_session(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(bootstrap, "_repo_root", lambda path: tmp_path)
    monkeypatch.setattr(bootstrap, "_trusted_executable", lambda: ["thaliris"])
    calls = []

    def invoke(executable, root, command):
        calls.append(command)
        if command == "bootstrap-check":
            return {"ok": True, "project_definition_present": "NO"}
        return {"ok": True, "project_definition_present": "YES", "session_restart_required": True, "manual_action_required": []}

    monkeypatch.setattr(bootstrap, "_invoke", invoke)
    result = bootstrap.bootstrap(tmp_path)
    assert result["status"] == "SESSION_RESTART_REQUIRED"
    assert calls == ["bootstrap-check", "init"]


def test_manual_action_is_terminal_without_retry(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(bootstrap, "_repo_root", lambda path: tmp_path)
    monkeypatch.setattr(bootstrap, "_trusted_executable", lambda: ["thaliris"])
    calls = []

    def invoke(executable, root, command):
        calls.append(command)
        if command == "bootstrap-check":
            return {"ok": True, "project_definition_present": "NO"}
        return {"ok": True, "project_definition_present": "NO", "manual_action_required": [".codex/hooks.json"]}

    monkeypatch.setattr(bootstrap, "_invoke", invoke)
    result = bootstrap.bootstrap(tmp_path)
    assert result["status"] == "MANUAL_ACTION_REQUIRED"
    assert calls == ["bootstrap-check", "init"]


def test_initialized_workspace_does_not_init(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(bootstrap, "_repo_root", lambda path: tmp_path)
    monkeypatch.setattr(bootstrap, "_trusted_executable", lambda: ["thaliris"])
    calls = []
    monkeypatch.setattr(bootstrap, "_invoke", lambda executable, root, command: calls.append(command) or {"ok": True, "project_definition_present": "YES"})
    result = bootstrap.bootstrap(tmp_path)
    assert result == {"ok": True, "status": "READY", "project_definition_present": "YES", "init_invoked": False}
    assert calls == ["bootstrap-check"]


def test_untrusted_executable_stops_before_probe(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(bootstrap, "_repo_root", lambda path: tmp_path)
    monkeypatch.setattr(bootstrap, "_trusted_executable", lambda: None)
    result = bootstrap.bootstrap(tmp_path)
    assert result["status"] == "BOOTSTRAP_UNAVAILABLE"
    assert result["manual_action_required"] == ["canonical_executable_unavailable"]


def test_cli_non_git_root_returns_structured_bootstrap_failure(tmp_path: Path, capsys):
    exit_code = cli.main(["--root", str(tmp_path), "codex-bootstrap"])

    captured = capsys.readouterr()
    assert exit_code == 3
    assert captured.err == ""
    assert captured.out.count("\n") == 1
    assert json.loads(captured.out) == {
        "error": "not a Git workspace",
        "ok": False,
        "status": "BOOTSTRAP_UNAVAILABLE",
    }
