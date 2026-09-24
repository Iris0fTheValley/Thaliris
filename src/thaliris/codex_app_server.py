"""Small official Codex app-server client for exact Host hook trust updates."""

from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable

from . import lifecycle


class CodexAppServerError(RuntimeError):
    """The official Codex app-server protocol did not complete safely."""


_EVENT_NAMES = {
    "SessionStart": "sessionStart",
    "UserPromptSubmit": "userPromptSubmit",
    "PreToolUse": "preToolUse",
    "PostToolUse": "postToolUse",
    "SubagentStart": "subagentStart",
    "SubagentStop": "subagentStop",
    "Stop": "stop",
}
_EXPECTED_HOOK_COUNT = len(lifecycle.HOOK_EVENTS)


def _same_path(left: object, right: Path) -> bool:
    if not isinstance(left, str) or not left:
        return False
    try:
        return os.path.normcase(os.path.normpath(str(Path(left).resolve(strict=False)))) == os.path.normcase(
            os.path.normpath(str(right.resolve(strict=False)))
        )
    except (OSError, RuntimeError, ValueError):
        return False


class CodexAppServer:
    """Run a short-lived official ``codex app-server --stdio`` session."""

    def __init__(self, codex_home: Path, timeout_seconds: float = 45.0) -> None:
        self.codex_home = codex_home.resolve(strict=True)
        self.timeout_seconds = timeout_seconds
        executable = shutil.which("codex")
        if executable is None:
            raise CodexAppServerError("codex CLI was not found on PATH")
        self.executable = str(Path(executable).resolve(strict=True))
        self._stderr = tempfile.TemporaryFile(mode="w+b")
        env = os.environ.copy()
        env["CODEX_HOME"] = str(self.codex_home)
        try:
            self._process = subprocess.Popen(
                [self.executable, "app-server", "--stdio"],
                cwd=str(self.codex_home),
                env=env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=self._stderr,
                text=True,
                encoding="utf-8",
                bufsize=1,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            self._stderr.close()
            raise CodexAppServerError("could not start codex app-server") from exc
        self._responses: queue.Queue[str | None] = queue.Queue()
        self._request_id = 0
        self._reader = threading.Thread(target=self._read_stdout, name="thaliris-codex-app-server", daemon=True)
        self._reader.start()

    def __enter__(self) -> CodexAppServer:
        try:
            result = self.request(
                "initialize",
                {"clientInfo": {"name": "thaliris-codex-install", "version": "1"}},
            )
            reported_home = result.get("codexHome") if isinstance(result, dict) else None
            if not _same_path(reported_home, self.codex_home):
                raise CodexAppServerError("app-server initialized with a different CODEX_HOME")
            self._notify("initialized", {})
            return self
        except BaseException:
            self._close()
            raise

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        self._close()
        if exc_type is None and self._process.returncode != 0:
            raise CodexAppServerError(f"codex app-server exited with status {self._process.returncode}")
        return False

    def _close(self) -> None:
        process = self._process
        if process.stdin is not None:
            try:
                process.stdin.close()
            except OSError:
                pass
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        self._reader.join(timeout=2)
        self._stderr.close()

    def _read_stdout(self) -> None:
        assert self._process.stdout is not None
        try:
            for line in self._process.stdout:
                self._responses.put(line)
        finally:
            self._responses.put(None)

    def _notify(self, method: str, params: dict[str, Any]) -> None:
        assert self._process.stdin is not None
        try:
            self._process.stdin.write(json.dumps({"method": method, "params": params}, separators=(",", ":")) + "\n")
            self._process.stdin.flush()
        except (OSError, BrokenPipeError) as exc:
            raise CodexAppServerError(f"codex app-server notification failed: {method}") from exc

    def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self._request_id += 1
        request_id = self._request_id
        assert self._process.stdin is not None
        request = {"method": method, "id": request_id, "params": params}
        try:
            self._process.stdin.write(json.dumps(request, ensure_ascii=False, separators=(",", ":")) + "\n")
            self._process.stdin.flush()
        except (OSError, BrokenPipeError) as exc:
            raise CodexAppServerError(f"codex app-server request failed: {method}") from exc

        deadline = time.monotonic() + self.timeout_seconds
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise CodexAppServerError(f"codex app-server timed out: {method}")
            try:
                line = self._responses.get(timeout=remaining)
            except queue.Empty as exc:
                raise CodexAppServerError(f"codex app-server timed out: {method}") from exc
            if line is None:
                raise CodexAppServerError(f"codex app-server exited before replying: {method}")
            try:
                response = json.loads(line)
            except json.JSONDecodeError as exc:
                raise CodexAppServerError("codex app-server returned invalid JSON") from exc
            if not isinstance(response, dict) or response.get("id") != request_id:
                continue
            error = response.get("error")
            if isinstance(error, dict):
                code = error.get("code")
                raise CodexAppServerError(f"codex app-server {method} failed (code {code})")
            result = response.get("result")
            if not isinstance(result, dict):
                raise CodexAppServerError(f"codex app-server returned an invalid {method} result")
            return result


def _app_server_client(codex_home: Path) -> CodexAppServer:
    return CodexAppServer(codex_home)


def _request(client: Any, method: str, params: dict[str, Any]) -> dict[str, Any]:
    result = client.request(method, params)
    if not isinstance(result, dict):
        raise CodexAppServerError(f"codex app-server returned an invalid {method} result")
    return result


def _hooks_for_home(client: Any, codex_home: Path) -> list[dict[str, Any]]:
    result = _request(client, "hooks/list", {"cwds": [str(codex_home)]})
    data = result.get("data")
    if not isinstance(data, list):
        raise CodexAppServerError("hooks/list returned no data")
    entry = next((item for item in data if isinstance(item, dict) and _same_path(item.get("cwd"), codex_home)), None)
    if entry is None or entry.get("errors"):
        raise CodexAppServerError("hooks/list did not return a clean CODEX_HOME entry")
    hooks = entry.get("hooks")
    if not isinstance(hooks, list) or not all(isinstance(item, dict) for item in hooks):
        raise CodexAppServerError("hooks/list returned invalid handler metadata")
    return hooks


def _expected_handlers(codex_home: Path, executable: Path, executable_sha256: str) -> dict[str, dict[str, Any]]:
    fragment = lifecycle.host_hook_spec(codex_home, executable, executable_sha256)["hooks"]
    expected: dict[str, dict[str, Any]] = {}
    for event in lifecycle.HOOK_EVENTS:
        group = fragment.get(event)
        if not isinstance(group, list) or len(group) != 1 or not isinstance(group[0], dict):
            raise CodexAppServerError("generated Host hook definition is invalid")
        handlers = group[0].get("hooks")
        if not isinstance(handlers, list) or len(handlers) != 1 or not isinstance(handlers[0], dict):
            raise CodexAppServerError("generated Host hook handler is invalid")
        expected[event] = {"command": handlers[0].get("command"), "matcher": group[0].get("matcher")}
    return expected


def _exact_installed_handlers(
    hooks: list[dict[str, Any]],
    codex_home: Path,
    expected: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    source_path = codex_home / "hooks.json"
    script_token = str(codex_home / lifecycle.HOST_HOOK_SCRIPT_NAME).casefold()
    by_event: dict[str, dict[str, Any]] = {}
    candidates = [
        hook for hook in hooks
        if _same_path(hook.get("sourcePath"), source_path)
        and hook.get("handlerType") == "command"
        and isinstance(hook.get("command"), str)
        and script_token in hook["command"].casefold()
    ]
    if len(candidates) != _EXPECTED_HOOK_COUNT:
        raise CodexAppServerError("HOST_HOOK_TRUST_INSTALL_FAILED: Host returned an unexpected Thaliris handler count")
    for event in lifecycle.HOOK_EVENTS:
        host_event = _EVENT_NAMES[event]
        event_candidates = [hook for hook in candidates if hook.get("eventName") == host_event]
        exact = [
            hook for hook in event_candidates
            if hook.get("command") == expected[event]["command"]
            and hook.get("matcher") == expected[event]["matcher"]
            and hook.get("timeoutSec") == 60
            and hook.get("source") == "user"
            and hook.get("isManaged") is False
        ]
        if len(event_candidates) != 1 or len(exact) != 1:
            raise CodexAppServerError(f"HOST_HOOK_TRUST_INSTALL_FAILED: Host handler mismatch for {event}")
        hook = exact[0]
        if not isinstance(hook.get("key"), str) or not hook["key"]:
            raise CodexAppServerError(f"HOST_HOOK_TRUST_INSTALL_FAILED: Host omitted the handler key for {event}")
        if not isinstance(hook.get("currentHash"), str) or not hook["currentHash"]:
            raise CodexAppServerError(f"HOST_HOOK_TRUST_INSTALL_FAILED: Host omitted currentHash for {event}")
        if not isinstance(hook.get("enabled"), bool) or not isinstance(hook.get("trustStatus"), str):
            raise CodexAppServerError(f"HOST_HOOK_TRUST_INSTALL_FAILED: Host metadata is incomplete for {event}")
        by_event[event] = hook
    if len(by_event) != _EXPECTED_HOOK_COUNT:
        raise CodexAppServerError("HOST_HOOK_TRUST_INSTALL_FAILED: Host did not return all expected handlers")
    return by_event


def _is_dispatchable(hook: dict[str, Any]) -> bool:
    trust = hook.get("trustStatus")
    return hook.get("enabled") is True and trust in {"trusted", "managed"}


def trust_installed_host_hooks(
    codex_home: Path,
    executable: Path,
    executable_sha256: str,
    *,
    client_factory: Callable[[Path], Any] | None = None,
) -> dict[str, Any]:
    """Trust only the seven exact Host-returned Thaliris handler identities."""
    home = codex_home.resolve(strict=True)
    expected = _expected_handlers(home, executable, executable_sha256)
    client_factory = client_factory or _app_server_client
    with client_factory(home) as client:
        before = _exact_installed_handlers(_hooks_for_home(client, home), home, expected)
        updates = {
            hook["key"]: {"trusted_hash": hook["currentHash"]}
            for hook in before.values()
            if hook.get("trustStatus") not in {"trusted", "managed"}
        }
        changed = False
        config_path: str | None = None
        if updates:
            result = _request(client, "config/batchWrite", {
                "edits": [{"keyPath": "hooks.state", "value": updates, "mergeStrategy": "upsert"}],
                "filePath": None,
                "expectedVersion": None,
                "reloadUserConfig": True,
            })
            if result.get("status") != "ok":
                raise CodexAppServerError("HOST_HOOK_TRUST_INSTALL_FAILED: config/batchWrite did not succeed")
            config_path = result.get("filePath") if isinstance(result.get("filePath"), str) else None
            expected_config = home / "config.toml"
            if config_path is None or not _same_path(config_path, expected_config):
                raise CodexAppServerError("HOST_HOOK_TRUST_INSTALL_FAILED: Host wrote hook trust to an unexpected file")
            changed = True
        after = _exact_installed_handlers(_hooks_for_home(client, home), home, expected)
        trusted_count = sum(hook.get("trustStatus") == "trusted" for hook in after.values())
        dispatchable_count = sum(_is_dispatchable(hook) for hook in after.values())
        if trusted_count != _EXPECTED_HOOK_COUNT:
            raise CodexAppServerError("HOST_HOOK_TRUST_INSTALL_FAILED: Host trust verification did not reach 7/7")
        return {
            "status": "TRUSTED",
            "trusted_count": trusted_count,
            "enabled_count": sum(hook.get("enabled") is True for hook in after.values()),
            "dispatchable_count": dispatchable_count,
            "expected_count": _EXPECTED_HOOK_COUNT,
            "changed": changed,
            "config_path": config_path,
            "keys": [hook["key"] for hook in after.values()],
        }


def owned_hook_keys_from_host(
    codex_home: Path,
    commands_by_event: dict[str, set[str]],
    *,
    client_factory: Callable[[Path], Any] | None = None,
) -> list[str]:
    """Return Host keys for exact Thaliris commands present in hooks.json."""
    home = codex_home.resolve(strict=True)
    client_factory = client_factory or _app_server_client
    with client_factory(home) as client:
        hooks = _hooks_for_home(client, home)
        keys: list[str] = []
        for event in lifecycle.HOOK_EVENTS:
            commands = commands_by_event.get(event, set())
            if not commands:
                continue
            matches = [
                hook for hook in hooks
                if _same_path(hook.get("sourcePath"), home / "hooks.json")
                and hook.get("eventName") == _EVENT_NAMES[event]
                and hook.get("handlerType") == "command"
                and hook.get("source") == "user"
                and hook.get("isManaged") is False
                and hook.get("command") in commands
            ]
            if len(matches) != len(commands) or any(not isinstance(hook.get("key"), str) for hook in matches):
                raise CodexAppServerError(f"could not identify exact Host keys for installed Thaliris {event} handlers")
            keys.extend(hook["key"] for hook in matches)
        if len(keys) != len(set(keys)):
            raise CodexAppServerError("Host returned duplicate hook keys during Thaliris uninstall")
        return keys


def _user_state_layer(config_result: dict[str, Any], home: Path) -> dict[str, Any] | None:
    layers = config_result.get("layers")
    if not isinstance(layers, list):
        raise CodexAppServerError("config/read omitted config layers")
    matches = [
        layer for layer in layers
        if isinstance(layer, dict)
        and isinstance(layer.get("name"), dict)
        and layer["name"].get("type") == "user"
        and _same_path(layer["name"].get("file"), home / "config.toml")
    ]
    if len(matches) > 1:
        raise CodexAppServerError("config/read returned ambiguous user config layers")
    return matches[0] if matches else None


def remove_owned_hook_trust(
    codex_home: Path,
    hook_keys: list[str],
    *,
    client_factory: Callable[[Path], Any] | None = None,
) -> int:
    """Remove exact Thaliris trust keys while preserving all other hook state."""
    unique_keys = list(dict.fromkeys(key for key in hook_keys if isinstance(key, str) and key))
    if not unique_keys:
        return 0
    home = codex_home.resolve(strict=True)
    client_factory = client_factory or _app_server_client
    with client_factory(home) as client:
        config = _request(client, "config/read", {"includeLayers": True, "cwd": str(home)})
        layer = _user_state_layer(config, home)
        if layer is None:
            return 0
        version = layer.get("version")
        layer_config = layer.get("config")
        hooks = layer_config.get("hooks") if isinstance(layer_config, dict) else None
        state = hooks.get("state") if isinstance(hooks, dict) else {}
        if state is None:
            state = {}
        if not isinstance(state, dict):
            raise CodexAppServerError("config/read returned invalid hooks.state")
        remaining = {key: value for key, value in state.items() if key not in unique_keys}
        removed = len(state) - len(remaining)
        if removed == 0:
            return 0
        if not isinstance(version, str) or not version:
            raise CodexAppServerError("config/read omitted the user config version")
        write = _request(client, "config/batchWrite", {
            "edits": [{"keyPath": "hooks.state", "value": remaining, "mergeStrategy": "replace"}],
            "filePath": None,
            "expectedVersion": version,
            "reloadUserConfig": True,
        })
        if write.get("status") != "ok":
            raise CodexAppServerError("config/batchWrite did not remove Thaliris hook trust state")
        verified = _request(client, "config/read", {"includeLayers": True, "cwd": str(home)})
        verified_layer = _user_state_layer(verified, home)
        if verified_layer is not None:
            verified_config = verified_layer.get("config")
            verified_hooks = verified_config.get("hooks") if isinstance(verified_config, dict) else None
            verified_state = verified_hooks.get("state") if isinstance(verified_hooks, dict) else {}
            if not isinstance(verified_state, dict) or any(key in verified_state for key in unique_keys):
                raise CodexAppServerError("Thaliris hook trust cleanup could not be verified")
        return removed
