"""Codex hook adapter for mechanical lifecycle, delivery, and telemetry."""
from __future__ import annotations

import hashlib
import json
import os
import ntpath
from pathlib import Path
import re
import secrets
import shlex
import shutil
import subprocess
import time
from typing import Any

from . import core, roles

HOOK_COMMAND_PREFIX = "thaliris audit-hook"
HOOK_EVENTS = ("SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "SubagentStart", "SubagentStop", "Stop")
CODEX_ADAPTER_PROTOCOL_VERSION = 9
# This literal travels in installed command bytes. An old Host registration
# invoking a newer executable cannot manufacture the current hook ABI.
MANAGED_HOOK_ABI = "thaliris-hook-abi-10"
HOST_HOOK_SCRIPT_NAME = "thaliris-hook.cmd"
PROJECT_ACTIVATION_MARKER = ".codex\\thaliris.json"
# Private adapter lifecycle state. This is deliberately separate from Core
# state/schema and records only bounded native child provenance.
LIFECYCLE_STATE_VERSION = 12
MANAGED_HOOKS_DESCRIPTION = "Thaliris managed lifecycle hooks"
MAX_RAW_RECORDS = 64
THALIRIS_EXECUTABLE_ENV = "THALIRIS_EXECUTABLE"
THALIRIS_EXECUTABLE_SHA256_ENV = "THALIRIS_EXECUTABLE_SHA256"
# Older pin names remain readable only as a configuration compatibility aid.
CONTEXT_EXECUTABLE_ENV = "THALIRIS_CONTEXT_EXECUTABLE"
CONTEXT_EXECUTABLE_SHA256_ENV = "THALIRIS_CONTEXT_EXECUTABLE_SHA256"
_COLLABORATION_TOOL_NAMES = (
    "spawn_agent",
    "Agent",
    "followup_task",
    "send_input",
    "send_message",
    "list_agents",
    "wait_agent",
    "interrupt_agent",
)
_COLLABORATION_TOOL_PATTERN = "(?:" + "|".join(re.escape(name) for name in _COLLABORATION_TOOL_NAMES) + ")"
# Keep legacy spellings observable for diagnostics, but do not confuse them
# with the only current Codex stable shell hook surface.  In particular, an
# ``exec`` payload from another runtime must never reach Core's trusted ingress.
_OBSERVED_EXECUTION_TOOL_NAMES = ("Bash", "Shell", "exec", "exec_command", "command_execution", "functions.exec_command")
_TRUSTED_CODEX_SHELL_TOOL_NAMES = ("Bash",)
_CONTROLLER_EXECUTION_TOOL_NAMES = _OBSERVED_EXECUTION_TOOL_NAMES
_CONTROLLER_EXECUTION_TOOL_PATTERN = "(?:" + "|".join(re.escape(name) for name in _OBSERVED_EXECUTION_TOOL_NAMES) + ")"

def _native_agent_roles() -> dict[str, str]:
    """Return exact generated native identities from the role registry."""
    return roles.native_agent_roles()


def _native_role_names() -> str:
    """Return registry-derived names for mechanical denial diagnostics."""
    names = [
        spec.id.replace("-", " ").title()
        for role in roles.role_choices()
        for spec in (roles.get_role(role),)
        for binding in (roles.get_codex_binding(role),)
        if spec is not None and binding is not None and binding.native_profile is not None
    ]
    if len(names) <= 1:
        return " and ".join(names)
    return ", ".join(names[:-1]) + ", and " + names[-1]


# Compatibility alias for existing adapter callers. Runtime checks use the
# accessor so registry additions do not require lifecycle edits.
_NATIVE_AGENT_ROLES = _native_agent_roles()
_CONTROLLER_MUTATION_TOOL_NAMES = ("apply_patch", "file_change", "functions.apply_patch", "functions.file_change")
_CONTROLLER_MUTATION_TOOL_PATTERN = "(?:" + "|".join(re.escape(name) for name in _CONTROLLER_MUTATION_TOOL_NAMES) + ")"
_CHILD_CONTROL_MUTATION_ACTIONS = frozenset({
    "write", "edit", "update", "replace", "patch", "append", "create", "delete", "remove",
    "move", "rename", "copy",
})
# Codex 0.146 Multi-Agent V2 exposes both dotted names and flattened
# `collaboration<tool>` names to hooks. Keep execution surfaces explicit too:
# a PostToolUse callback is the only possible completion observation.
POST_TOOL_MATCHER = rf"^(?:{_COLLABORATION_TOOL_PATTERN}|(?:[A-Za-z0-9_]+\.)+{_COLLABORATION_TOOL_PATTERN}|collaboration{_COLLABORATION_TOOL_PATTERN}|{_CONTROLLER_EXECUTION_TOOL_PATTERN})$"
# Codex 0.154 routes local function tools through this hook surface. Managed
# policy therefore starts from a transparent NO_TASK state and an explicit
# ACTIVE allow-set instead of attempting to enumerate dangerous tool names.
PRE_TOOL_MATCHER = "*"
_DELEGATION_TOOL_NAMES = frozenset({"spawn_agent", "Agent", "followup_task", "send_input", "send_message"})
_FRESH_CHILD_REUSE_TOOL_NAMES = frozenset({"followup_task", "send_input", "send_message"})
_ROOT_MANAGED_TOOL_NAMES = frozenset({"spawn_agent", "wait_agent", "list_agents", "interrupt_agent"})
_CONTROLLER_BOUNDARY_REASON = "THALIRIS_CONTROLLER_BOUNDARY: delegate investigation to a fresh Investigator session and edits to a fresh Implementer session; the Controller may run only bounded control-plane or acceptance checks."
_OBVIOUS_WRITE = re.compile(
    r"(?i)(?:apply_patch|git\s+(?:apply|commit|reset|checkout|restore|rebase)|(?:set|add|clear|out|remove|move|copy|rename|new)-content|(?:set|add|remove|move|copy|rename|new)-item|\b(?:ni|mkdir)\b|(?<![<>])>{1,2}(?![&]))"
)
_COMMAND_SEPARATOR = re.compile(r"(?:\r?\n|&&|\|\||\||&|;)")
_CONTEXT_OPERATIONS = frozenset({
    "init", "codex-install", "codex-uninstall", "doctor", "stale", "milestone-check", "memory-status", "uninstall",
    "task-start", "task-update", "task-show",
    "task-status", "task-get", "artifact-get", "catalog", "document-get",
    "task-artifact", "task-close", "task-promote", "recover-pending-spawn", "rollback", "version",
})
_ACTIVE_ROOT_CONTEXT_OPERATIONS = frozenset({
    "doctor", "milestone-check", "memory-status", "task-update", "task-status", "task-get", "artifact-get",
    "catalog", "document-get", "task-artifact", "task-close", "task-promote",
    "recover-pending-spawn", "version",
})
_CHILD_CONTEXT_READS = frozenset({
    "task-show", "task-status", "stale",
    "memory-status", "milestone-check", "task-get", "artifact-get", "catalog",
    "document-get",
})
_CHILD_CONTEXT_MUTATIONS = frozenset({
    "task-start", "task-update", "task-artifact", "task-close", "task-promote", "codex-install",
    "recover-pending-spawn", "rollback", "init", "uninstall", "codex-uninstall",
})
_CONTROL_STATE_TARGET = re.compile(r"(?i)\.context[\\/](?:state\.json|audit[\\/]lifecycle(?:[\\/][^\s\"']+)?)")
_DURABLE_PATH_TARGET = re.compile(r"(?i)(?:^|[\s\"'=])((?:\.agent-memory|\.milestones)(?:[\\/][^\s\"'|;&<>]*)?)")
_START_ATTESTATION_TTL_NS = 120 * 1_000_000_000

# Role filenames visible on disk are configuration observations only.  The
# current Codex hook payload has no native role-catalog observation, so the
# catalog status remains UNKNOWN unless a future Host contract supplies one.
HOST_ROLE_CATALOG_OBSERVED = "HOST_ROLE_CATALOG_OBSERVED"
HOST_ROLE_CATALOG_UNKNOWN = "HOST_ROLE_CATALOG_UNKNOWN"
NEW_ROLE_CATALOG_IDENTITY_NOT_ACTIVE = "NEW_ROLE_CATALOG_IDENTITY_NOT_ACTIVE"
PROFILE_BYTES_CHANGED_SINCE_SESSION_START = "PROFILE_BYTES_CHANGED_SINCE_SESSION_START"
_PROFILE_FILES_PRESENT_AT_SESSION_START = "profile_files_present_at_session_start"
_HOST_ROLE_CATALOG_STATUS = "host_role_catalog_status"
_HOST_RUNTIME_PROFILE_STATUS = "host_runtime_profile_status"
def hook_spec() -> dict[str, Any]:
    """Return the exact managed hooks fragment; callers merge it conservatively."""
    hooks: dict[str, list[dict[str, Any]]] = {}
    prefix = _hook_command_prefix()
    for event in HOOK_EVENTS:
        handler: dict[str, Any] = {"type": "command", "command": f"{prefix} {event} --managed-hook-abi {MANAGED_HOOK_ABI}", "timeout": 60}
        entry: dict[str, Any] = {"hooks": [handler]}
        if event == "PostToolUse":
            # Codex treats a matcher made only of word characters and `|` as
            # an exact-name set.  Regex anchors and escaping deliberately opt
            # into regex semantics for the MultiAgentV2 namespaced tools.
            entry["matcher"] = POST_TOOL_MATCHER
        elif event == "PreToolUse":
            entry["matcher"] = PRE_TOOL_MATCHER
        hooks[event] = [entry]
    return {"hooks": hooks}


def managed_hook_spec_hash() -> str:
    """Fingerprint the logical managed fragment, not a local executable path."""
    logical = hook_spec()
    hooks = logical.get("hooks")
    if isinstance(hooks, dict):
        for event, entries in hooks.items():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict) or not isinstance(entry.get("hooks"), list):
                    continue
                for handler in entry["hooks"]:
                    if isinstance(handler, dict) and handler.get("type") == "command":
                        handler["command"] = f"{HOOK_COMMAND_PREFIX} {event} --managed-hook-abi {MANAGED_HOOK_ABI}"
    encoded = json.dumps(logical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _managed_handler(event: str) -> dict[str, Any]:
    return {"type": "command", "command": f"{_hook_command_prefix()} {event} --managed-hook-abi {MANAGED_HOOK_ABI}", "timeout": 60}


def host_hook_script_bytes() -> bytes:
    """Render the stable Windows trampoline; inactive projects stop before Python."""
    return (
        "@echo off\r\n"
        "setlocal DisableDelayedExpansion\r\n"
        "set \"_thaliris_search_dir=%CD%\"\r\n"
        ":thaliris_find_activation_marker\r\n"
        f"if exist \"%_thaliris_search_dir%\\{PROJECT_ACTIVATION_MARKER}\" goto thaliris_dispatch\r\n"
        "for %%I in (\"%_thaliris_search_dir%\\..\") do set \"_thaliris_parent=%%~fI\"\r\n"
        "if /i \"%_thaliris_parent%\"==\"%_thaliris_search_dir%\" exit /b 0\r\n"
        "set \"_thaliris_search_dir=%_thaliris_parent%\"\r\n"
        "goto thaliris_find_activation_marker\r\n"
        ":thaliris_dispatch\r\n"
        f"set \"{THALIRIS_EXECUTABLE_ENV}=%~1\"\r\n"
        f"set \"{THALIRIS_EXECUTABLE_SHA256_ENV}=%~2\"\r\n"
        "shift\r\n"
        "shift\r\n"
        f"\"%{THALIRIS_EXECUTABLE_ENV}%\" audit-hook %~1 --managed-hook-abi %~2\r\n"
        "exit /b %ERRORLEVEL%\r\n"
    ).encode("ascii")


def _legacy_host_hook_script_bytes() -> bytes:
    """Exact previous trampoline bytes, retained only for safe migration/removal."""
    return (
        "@echo off\r\n"
        "setlocal DisableDelayedExpansion\r\n"
        f"if not exist \"{PROJECT_ACTIVATION_MARKER}\" exit /b 0\r\n"
        f"set \"{THALIRIS_EXECUTABLE_ENV}=%~1\"\r\n"
        f"set \"{THALIRIS_EXECUTABLE_SHA256_ENV}=%~2\"\r\n"
        "shift\r\n"
        "shift\r\n"
        f"\"%{THALIRIS_EXECUTABLE_ENV}%\" audit-hook %~1 --managed-hook-abi %~2\r\n"
        "exit /b %ERRORLEVEL%\r\n"
    ).encode("ascii")


def host_hook_spec(
    codex_home: Path,
    executable: Path,
    executable_sha256: str,
) -> dict[str, Any]:
    """Return Host-global registration that dispatches through the cheap marker trampoline."""
    script = codex_home / HOST_HOOK_SCRIPT_NAME
    hooks: dict[str, list[dict[str, Any]]] = {}
    for event in HOOK_EVENTS:
        command = subprocess.list2cmdline([
            "cmd.exe", "/d", "/c", "call", str(script), str(executable),
            executable_sha256, event, MANAGED_HOOK_ABI,
        ])
        entry: dict[str, Any] = {
            "hooks": [{"type": "command", "command": command, "timeout": 60}]
        }
        if event == "PostToolUse":
            entry["matcher"] = POST_TOOL_MATCHER
        elif event == "PreToolUse":
            entry["matcher"] = PRE_TOOL_MATCHER
        hooks[event] = [entry]
    return {"hooks": hooks}


def _host_hook_command_is_managed(
    value: object,
    event: str,
    codex_home: Path,
    *,
    require_current_pin: bool = False,
) -> bool:
    """Recognize only complete direct legacy or generated trampoline handlers."""
    if event not in HOOK_EVENTS:
        return False
    if _owned_managed_handler(value, event):
        return True
    if not isinstance(value, dict) or set(value) != {"type", "command", "timeout"}:
        return False
    if value.get("type") != "command" or value.get("timeout") != 60:
        return False
    command = value.get("command")
    if not isinstance(command, str):
        return False
    script_token_pattern = rf'(?P<script_token>"[^"]+"|[^\s]+)'
    executable_token_pattern = rf'(?P<executable_token>"[^"]+"|[^\s]+)'
    match = re.fullmatch(
        rf"(?i)cmd\.exe /d /c call {script_token_pattern} {executable_token_pattern} (?P<sha>[0-9a-f]{{64}}) {re.escape(event)} (?P<abi>thaliris-hook-abi-[0-9]+)",
        command,
    )
    if match is None:
        return False
    script_token, executable_token = match.group("script_token"), match.group("executable_token")
    script_path = script_token[1:-1] if script_token.startswith('"') else script_token
    executable_path = executable_token[1:-1] if executable_token.startswith('"') else executable_token
    try:
        script = Path(script_path)
        executable = Path(executable_path)
        if not script.is_absolute() or script.resolve(strict=True) != (codex_home / HOST_HOOK_SCRIPT_NAME).resolve(strict=True):
            return False
        if script.is_symlink() or script.read_bytes() not in {
            host_hook_script_bytes(), _legacy_host_hook_script_bytes()
        }:
            return False
        if not executable.is_absolute() or executable.is_symlink():
            return False
        if not require_current_pin:
            # The exact generated command remains Thaliris-owned after its
            # executable is upgraded in place. This lets codex-install replace
            # only that stale registration with the new byte pin.
            return True
        return (
            executable.is_file()
            and hashlib.sha256(executable.read_bytes()).hexdigest() == match.group("sha").lower()
            and match.group("abi") == MANAGED_HOOK_ABI
        )
    except (OSError, RuntimeError):
        return False


def merge_host_hooks(
    data: dict[str, Any],
    codex_home: Path,
    executable: Path,
    executable_sha256: str,
) -> tuple[dict[str, Any], bool, list[str]]:
    """Merge the exact stable trampoline registrations without replacing user hooks."""
    merged = json.loads(json.dumps(data))
    hooks = merged.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError("Host hooks.json hooks must be an object")
    wanted = host_hook_spec(codex_home, executable, executable_sha256)["hooks"]
    changed = False
    manual: list[str] = []
    for event, wanted_entries in wanted.items():
        entries = hooks.setdefault(event, [])
        if not isinstance(entries, list):
            raise ValueError(f"Host hooks.json hooks.{event} must be an array")
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("hooks"), list):
                continue
            for handler in entry["hooks"]:
                if not isinstance(handler, dict) or handler.get("type") != "command":
                    continue
                command = handler.get("command")
                if isinstance(command, str) and HOST_HOOK_SCRIPT_NAME.lower() in command.lower():
                    if not _host_hook_command_is_managed(handler, event, codex_home):
                        manual.append(f"hooks.{event}")
        if manual:
            continue
        present = False
        normalized: list[Any] = []
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("hooks"), list):
                normalized.append(entry)
                continue
            managed = [item for item in entry["hooks"] if _host_hook_command_is_managed(item, event, codex_home)]
            if not managed:
                normalized.append(entry)
                continue
            user_handlers = [item for item in entry["hooks"] if not _host_hook_command_is_managed(item, event, codex_home)]
            if entry == wanted_entries[0] and len(managed) == 1 and not user_handlers:
                present = True
                normalized.append(entry)
                continue
            if user_handlers:
                copied = dict(entry)
                copied["hooks"] = user_handlers
                normalized.append(copied)
            changed = True
        if not present:
            normalized.append(wanted_entries[0])
            changed = True
        hooks[event] = normalized
    if manual:
        return json.loads(json.dumps(data)), False, sorted(set(manual))
    return merged, changed, []


def remove_host_hooks(data: dict[str, Any], codex_home: Path) -> tuple[dict[str, Any], bool, list[str]]:
    """Remove only exact generated Host trampoline and known direct legacy handlers."""
    cleaned = json.loads(json.dumps(data))
    hooks = cleaned.get("hooks")
    if not isinstance(hooks, dict):
        return cleaned, False, []
    changed = False
    manual: list[str] = []
    for event in list(hooks):
        entries = hooks[event]
        if not isinstance(entries, list):
            continue
        kept: list[Any] = []
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("hooks"), list):
                kept.append(entry)
                continue
            handlers = []
            for handler in entry["hooks"]:
                command = handler.get("command") if isinstance(handler, dict) else None
                looks_trampoline = isinstance(command, str) and HOST_HOOK_SCRIPT_NAME.lower() in command.lower()
                if looks_trampoline and not _host_hook_command_is_managed(handler, event, codex_home):
                    manual.append(f"hooks.{event}")
                    handlers.append(handler)
                elif event in HOOK_EVENTS and _host_hook_command_is_managed(handler, event, codex_home):
                    changed = True
                else:
                    handlers.append(handler)
            if handlers:
                copied = dict(entry)
                copied["hooks"] = handlers
                kept.append(copied)
        if kept:
            hooks[event] = kept
        elif entries:
            del hooks[event]
    if manual:
        return json.loads(json.dumps(data)), False, sorted(set(manual))
    return cleaned, changed, []


def _hook_command_prefix() -> str:
    """Return the installed-hook command for the current trust boundary."""
    pinned = _trusted_thaliris_executable()
    # list2cmdline provides deterministic Windows-compatible quoting, including
    # an executable path containing spaces.  The logical hook hash replaces this
    # local rendering with HOOK_COMMAND_PREFIX before hashing.
    return f"{subprocess.list2cmdline([str(pinned)])} audit-hook" if pinned is not None else HOOK_COMMAND_PREFIX


def _digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _trusted_thaliris_executable() -> Path | None:
    """Return a host-pinned executable only when its bytes match the pin.

    A configured path by itself is not trust.  The canonical PATH-relative
    ``thaliris`` invocation remains valid; an absolute/local executable requires
    both an explicit path and an exact host-provided SHA-256 pin.
    """
    configured = os.environ.get(THALIRIS_EXECUTABLE_ENV) or os.environ.get(CONTEXT_EXECUTABLE_ENV)
    expected = (os.environ.get(THALIRIS_EXECUTABLE_SHA256_ENV) or os.environ.get(CONTEXT_EXECUTABLE_SHA256_ENV, "")).lower()
    if not configured or not re.fullmatch(r"[0-9a-f]{64}", expected):
        return None
    path = Path(configured)
    try:
        if not path.is_absolute() or not path.is_file() or path.is_symlink():
            return None
        resolved = path.resolve(strict=True)
        return resolved if _digest_file(resolved) == expected else None
    except (OSError, RuntimeError):
        return None


def managed_context_executable_pinned() -> bool:
    """Whether managed control-plane trust has an explicit path+byte pin."""
    return _trusted_thaliris_executable() is not None


def managed_executable_health() -> dict[str, str]:
    """Report diagnostic-process command resolution and a byte-pinned identity."""
    pinned = _trusted_thaliris_executable()
    if pinned is not None:
        return {
            "canonical_executable_available": "YES",
            "canonical_executable_identity": "SHA256_PINNED",
            "diagnostic_process_executable_resolution": "SHA256_PINNED",
        }
    available = shutil.which("thaliris") is not None
    return {
        "canonical_executable_available": "YES" if available else "NO",
        "canonical_executable_identity": "PATH_UNPINNED" if available else "UNAVAILABLE",
        "diagnostic_process_executable_resolution": "PATH_UNPINNED" if available else "UNAVAILABLE",
    }


def _context_arguments(command: str) -> str | None:
    """Extract arguments only from direct thaliris or a byte-pinned executable."""
    command = command.lstrip()
    # Codex's Windows shell tool submits native PowerShell invocations with
    # its call operator (for example: & 'C:\\path\\thaliris.exe' ...).
    # Accept only that leading operator; _context_call still rejects any
    # subsequent command separator before trusting the direct invocation.
    if command.startswith("&"):
        if len(command) < 2 or not command[1].isspace():
            return None
        command = command[1:].lstrip()
    match = re.match(r"^\s*(\"[^\"]+\"|'[^']+'|[^\s]+)(?:\s+(.*?))?\s*$", command)
    if not match:
        return None
    token = match.group(1)
    executable = token[1:-1] if len(token) >= 2 and token[0] == token[-1] and token[0] in {'\"', "'"} else token
    lowered = executable.lower()
    canonical = lowered in {"thaliris", "thaliris.exe", "thaliris.cmd"} and not any(char in executable for char in "\\/")
    pinned = False
    trusted = _trusted_thaliris_executable()
    if trusted is not None:
        try:
            pinned = Path(executable).resolve(strict=True) == trusted
        except (OSError, RuntimeError):
            pinned = False
    if not (canonical or pinned):
        return None
    return match.group(2) or ""


def is_managed_handler(value: object, event: str) -> bool:
    return value == _managed_handler(event)


def _legacy_managed_handler(value: object, event: str) -> bool:
    """Recognize only the exact legacy handler we generated, never wrappers."""
    expected = {"type": "command", "command": f"context audit-hook {event}", "timeout": 60}
    if value == expected:
        return True
    # Before executable pins were introduced, the generated canonical form
    # used the PATH-relative command.  It remains mechanically identifiable
    # by its complete generated shape and can therefore be upgraded safely.
    if value == {"type": "command", "command": f"{HOOK_COMMAND_PREFIX} {event}", "timeout": 60}:
        return True
    if value == {
        "type": "command",
        "command": f"{HOOK_COMMAND_PREFIX} {event} --managed-hook-abi thaliris-hook-abi-9",
        "timeout": 60,
    }:
        return True
    # A prior generated hook used the then-valid, byte-pinned absolute
    # executable.  Migrate only that exact no-wrapper command after proving the
    # same current pin; do not make a path spelling into a trust decision.
    if isinstance(value, dict) and set(value) == {"type", "command", "timeout"} and value.get("type") == "command" and value.get("timeout") == 60 and isinstance(value.get("command"), str):
        arguments = _context_arguments(value["command"])
        trusted = _trusted_thaliris_executable()
        if arguments == f"audit-hook {event}" and trusted is not None:
            token = _command_token(value["command"])
            if token is not None:
                try:
                    if Path(token).resolve(strict=True) == trusted:
                        return True
                except (OSError, RuntimeError):
                    pass
    # Historical generated SubagentStart entries carried this no-injection
    # marker. It is also recognized only as the exact generated shape.
    return event == "SubagentStart" and value == {**expected, "additionalContextLimit": 0}


def _owned_managed_handler(value: object, event: str) -> bool:
    return is_managed_handler(value, event) or _legacy_managed_handler(value, event)


def _command_token(command: str) -> str | None:
    match = re.match(r"^\s*(\"[^\"]+\"|'[^']+'|[^\s]+)(?:\s+.*?)?\s*$", command)
    if not match:
        return None
    token = match.group(1)
    return token[1:-1] if len(token) >= 2 and token[0] == token[-1] and token[0] in {'\"', "'"} else token


def _absolute_command_token(command: str) -> str | None:
    token = _command_token(command)
    return token if token is not None and (Path(token).is_absolute() or ntpath.isabs(token)) else None


def _wrapped_audit_hook_signature(command: str, event: str) -> bool:
    """Recognize, but never interpret, common shell wrappers around old hooks."""
    wrapper = re.match(
        r"(?is)^\s*(?:cmd(?:\.exe)?(?:\s+/[a-z]+)*\s+/[ck]|(?:powershell|pwsh)(?:\.exe)?\b.*?\s-(?:command|c)\b)",
        command,
    )
    if wrapper is None:
        return False
    # This is deliberately a signature search, not shell parsing: it requires
    # a recognizable Thaliris/context executable and the exact hook event.
    # This recognizes an executable token, not an arbitrary wrapper body. In
    # particular, quoted paths may contain spaces, but their basename must be
    # one we historically generated.  It intentionally does not parse or run
    # the wrapper.
    basename = r"(?:context(?:\.exe)?|thaliris(?:\.exe)?)"
    executable = rf"(?:\"[^\"]*[\\/]{basename}\"|'[^']*[\\/]{basename}'|{basename}(?=$|[\s\"'&])|[a-z]:[^\r\n\"']*[\\/]{basename})"
    signature = rf"(?i)(?:^|[\s\"'&]){executable}\s+audit-hook\s+{re.escape(event)}(?=$|[\s\"'])"
    return re.search(signature, command) is not None


def _ambiguous_legacy_managed_handler(value: object, event: str) -> bool:
    """Identify possible old generated commands that are unsafe to migrate."""
    if is_managed_handler(value, event):
        return False
    if not isinstance(value, dict) or value.get("type") != "command" or not isinstance(value.get("command"), str):
        return False
    command = value["command"]
    # A direct legacy command with a recognizable Thaliris basename and a
    # non-exact shape is never removed automatically. Absolute candidates
    # deliberately do not require a currently valid pin: that is precisely
    # why they need human cleanup. Arbitrary executables are unrelated.
    if re.match(rf"(?i)^\s*(?:context(?:\.exe)?|thaliris(?:\.exe)?)\s+audit-hook\s+{re.escape(event)}(?=$|\s)", command):
        return not _legacy_managed_handler(value, event)
    if _wrapped_audit_hook_signature(command, event):
        return True
    token = _absolute_command_token(command)
    if token is None or ntpath.basename(token).lower() not in {"context", "context.exe", "thaliris", "thaliris.exe"}:
        return False
    tail = re.sub(r"^\s*(?:\"[^\"]+\"|'[^']+'|[^\s]+)\s*", "", command)
    return tail.startswith(f"audit-hook {event}") and not _legacy_managed_handler(value, event)


def legacy_managed_handler_cleanup_required(data: object) -> bool:
    """Whether hooks contain an old-looking command that needs manual cleanup."""
    if not isinstance(data, dict) or not isinstance(data.get("hooks"), dict):
        return False
    for event, entries in data["hooks"].items():
        if event not in HOOK_EVENTS or not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("hooks"), list):
                continue
            if any(_ambiguous_legacy_managed_handler(handler, event) for handler in entry["hooks"]):
                return True
    return False


def merge_hooks(data: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Append only missing managed handlers, preserving all user JSON values."""
    merged = json.loads(json.dumps(data))
    hooks = merged.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError(".codex/hooks.json hooks must be an object")
    changed = False
    for event, wanted_entries in hook_spec()["hooks"].items():
        entries = hooks.setdefault(event, [])
        if not isinstance(entries, list):
            raise ValueError(f".codex/hooks.json hooks.{event} must be an array")
        present = False
        normalized_entries: list[Any] = []
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("hooks"), list):
                normalized_entries.append(entry)
                continue
            managed = [item for item in entry["hooks"] if _owned_managed_handler(item, event)]
            if not managed:
                normalized_entries.append(entry)
                continue
            if entry == wanted_entries[0]:
                present = True
                normalized_entries.append(entry)
                continue
            # A matcher applies to every handler in an entry. Preserve user
            # handlers unchanged, and isolate the canonical generated entry.
            user_handlers = [item for item in entry["hooks"] if not _owned_managed_handler(item, event)]
            if user_handlers:
                copied = dict(entry)
                copied["hooks"] = user_handlers
                normalized_entries.append(copied)
            changed = True
        if not present:
            normalized_entries.append(wanted_entries[0])
            changed = True
        hooks[event] = normalized_entries
    return merged, changed


def remove_hooks(data: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Remove only Thaliris command handlers, retaining surrounding user entries."""
    cleaned = json.loads(json.dumps(data))
    hooks = cleaned.get("hooks")
    if not isinstance(hooks, dict):
        return cleaned, False
    changed = False
    for event in list(hooks):
        entries = hooks[event]
        if not isinstance(entries, list):
            continue
        kept_entries: list[Any] = []
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("hooks"), list):
                kept_entries.append(entry)
                continue
            handlers = [handler for handler in entry["hooks"] if not _owned_managed_handler(handler, event)]
            if len(handlers) != len(entry["hooks"]):
                changed = True
            if handlers:
                copied = dict(entry)
                copied["hooks"] = handlers
                kept_entries.append(copied)
        if kept_entries:
            hooks[event] = kept_entries
        else:
            del hooks[event]
    return cleaned, changed


def host_hooks_health(codex_home: Path) -> dict[str, str]:
    """Report disk registration for the stable Host trampoline, never runtime load."""
    path = codex_home / "hooks.json"
    script = codex_home / HOST_HOOK_SCRIPT_NAME
    if codex_home.is_symlink() or path.is_symlink() or script.is_symlink():
        return {"hooks_configured": "UNKNOWN", "host_hook_manual_action_required": "YES"}
    if not path.is_file() or not script.is_file():
        return {"hooks_configured": "NO", "host_hook_manual_action_required": "NO"}
    try:
        if script.read_bytes() != host_hook_script_bytes():
            return {"hooks_configured": "NO", "host_hook_manual_action_required": "YES"}
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("hooks"), dict):
            return {"hooks_configured": "UNKNOWN", "host_hook_manual_action_required": "YES"}
    except (OSError, ValueError, json.JSONDecodeError):
        return {"hooks_configured": "UNKNOWN", "host_hook_manual_action_required": "YES"}
    present = True
    manual = False
    for event in HOOK_EVENTS:
        entries = data["hooks"].get(event)
        if not isinstance(entries, list):
            present = False
            continue
        count = sum(
            1 for entry in entries
            if isinstance(entry, dict) and isinstance(entry.get("hooks"), list)
            for handler in entry["hooks"]
            if _host_hook_command_is_managed(
                handler, event, codex_home, require_current_pin=True
            )
        )
        present = present and count == 1
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("hooks"), list):
                continue
            for handler in entry["hooks"]:
                command = handler.get("command") if isinstance(handler, dict) else None
                if isinstance(command, str) and HOST_HOOK_SCRIPT_NAME.lower() in command.lower() and not _host_hook_command_is_managed(handler, event, codex_home):
                    manual = True
    return {
        "hooks_configured": "YES" if present else "NO",
        "host_hook_manual_action_required": "YES" if manual else "NO",
    }


def legacy_project_hook_registration_present(root: Path) -> str:
    """Distinguish old project-scoped Thaliris registration from Host setup."""
    path = root / ".codex" / "hooks.json"
    if not path.exists():
        return "NO"
    if path.is_symlink():
        return "UNKNOWN"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("hooks", {}), dict):
            return "UNKNOWN"
    except (OSError, ValueError, json.JSONDecodeError):
        return "UNKNOWN"
    hooks = data.get("hooks", {})
    for event in HOOK_EVENTS:
        entries = hooks.get(event)
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("hooks"), list):
                continue
            for handler in entry["hooks"]:
                if _owned_managed_handler(handler, event) or _ambiguous_legacy_managed_handler(handler, event):
                    return "YES"
    return "NO"


def hooks_health(root: Path) -> dict[str, str]:
    """Report the effective user Host hook registration and local legacy residue."""
    host = host_hooks_health(_host_home_path())
    configured = host["hooks_configured"]
    observed = _observed_health(root)
    status = "UNAVAILABLE" if configured == "NO" else (
        "HEALTHY" if configured == "YES" and observed["runtime_observed"] == "YES" else "UNKNOWN"
    )
    return {
        "status": status,
        "hooks_configured": configured,
        "installed_hook_spec": "CURRENT" if configured == "YES" else ("UNAVAILABLE" if configured == "NO" else "UNKNOWN"),
        "runtime_observed": observed["runtime_observed"],
        "current_hook_hash_observed": observed["current_hook_hash_observed"],
        "pretool_child_identity_corroborated": child_identity_corroboration(root),
        "hook_trust_runtime_status": "UNKNOWN",
        "legacy_managed_handler_cleanup": "MANUAL_CLEANUP_REQUIRED" if host["host_hook_manual_action_required"] == "YES" else "NO",
        "legacy_project_hook_registration_present": legacy_project_hook_registration_present(root),
        **managed_executable_health(),
    }


def _observed_health(root: Path) -> dict[str, str]:
    base = root / ".context" / "audit"
    observed = "UNKNOWN"
    current_hash = "UNKNOWN"
    if not base.is_dir():
        return {"runtime_observed": observed, "current_hook_hash_observed": current_hash}
    expected = managed_hook_spec_hash()
    runtime_files = []
    stale = False
    for path in base.glob("*/runtime.json"):
        try:
            runtime = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(runtime, dict) and runtime.get("managed_hook_spec_hash") == expected and runtime.get("adapter_protocol_version") == CODEX_ADAPTER_PROTOCOL_VERSION:
            runtime_files.append(path)
        else:
            stale = True
    if runtime_files:
        observed = "YES"
    current_hash = "YES" if runtime_files else ("STALE" if stale else "UNKNOWN")
    return {"runtime_observed": observed, "current_hook_hash_observed": current_hash}


def handle_hook(root: Path, event: str, payload: object, managed_hook_abi: str | None = None, controller_bridge_sha256: str | None = None) -> str:
    """Apply mechanical guard/lifecycle rules and record hash-only telemetry."""
    try:
        if event not in HOOK_EVENTS or not isinstance(payload, dict):
            return ""
        root = _hook_repository_root(root, payload)
        if event == "SubagentStart":
            return _subagent_start_output(root, payload)
        if event == "SubagentStop":
            _best_effort_record(_record_subagent_stop, root, payload)
            return ""
        if payload.get("agent_id") is not None or payload.get("agent_type") is not None:
            if event == "PreToolUse":
                return _child_pre_tool_output(root, payload)
            _best_effort_record(_record_child_runtime_event, root, payload, event)
            tool = payload.get("tool_name") or payload.get("tool")
            if event == "PostToolUse" and isinstance(tool, str) and _bound_managed_child(root, payload):
                _best_effort_record(_reconcile_lifecycle_post_tool, root, payload, _tool_basename(tool))
            return ""
        if event == "PreToolUse":
            tool = payload.get("tool_name") or payload.get("tool")
            if isinstance(tool, str) and _tool_basename(tool) == "spawn_agent":
                decision = _pre_tool_output(payload, root, managed_hook_abi, controller_bridge_sha256)
                _best_effort_record(_record_runtime_event, root, payload, event, tool)
                return decision
            return _pre_tool_output(payload, root, managed_hook_abi, controller_bridge_sha256)
        if event == "SessionStart":
            _record_session_start(root, payload)
            return _session_start_output(root, payload)
        if event == "UserPromptSubmit":
            _best_effort_record(_record_prompt_telemetry, root, payload)
            return ""
        if event == "PostToolUse":
            tool = payload.get("tool_name") or payload.get("tool")
            if isinstance(tool, str) and _tool_basename(tool) in _COLLABORATION_TOOL_NAMES:
                _best_effort_record(_record_runtime_event, root, payload, event, tool)
                _best_effort_record(_reconcile_lifecycle_post_tool, root, payload, _tool_basename(tool))
                if _tool_basename(tool) in _DELEGATION_TOOL_NAMES:
                    _best_effort_record(_record_delegation_telemetry, root, payload)
            if isinstance(tool, str) and _tool_basename(tool) in _OBSERVED_EXECUTION_TOOL_NAMES:
                _best_effort_record(_record_execution_observation, root, payload)
            if isinstance(tool, str) and _tool_basename(tool) == "Bash":
                return _post_init_attestation(root, payload, managed_hook_abi, controller_bridge_sha256)
            return ""
        # Stop has no production policy role. It neither invokes a model nor
        # blocks or corrects the Controller.
        return ""
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return ""


def _best_effort_record(function: Any, *args: Any, **kwargs: Any) -> None:
    """Persist observation without coupling audit availability to policy."""
    try:
        function(*args, **kwargs)
    except Exception:
        pass


def _hook_repository_root(root: Path, payload: dict[str, Any]) -> Path:
    """Resolve the worktree named by the hook payload, not the shell cwd."""
    candidate = payload.get("cwd")
    cwd = Path(candidate) if isinstance(candidate, str) and candidate else root
    if not cwd.is_absolute():
        cwd = root / cwd
    cwd = cwd.resolve(strict=False)
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
            timeout=2,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return Path(proc.stdout.strip()).resolve()
    except (OSError, subprocess.SubprocessError):
        pass
    return root.resolve()


def _state_path(root: Path, payload: dict[str, Any], partition: str) -> Path:
    session_dir = _session_dir(root, payload)
    directory = hashlib.sha256(partition.encode("utf-8")).hexdigest()[:24]
    return session_dir / directory / "capture.json"


def _session_dir(root: Path, payload: dict[str, Any]) -> Path:
    session = payload.get("session_id")
    identity = session if isinstance(session, str) and session else "unknown-session"
    directory = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
    return root / ".context" / "audit" / directory


def _host_home_path() -> Path:
    configured = os.environ.get("CODEX_HOME")
    return (Path(configured).expanduser() if configured else Path.home() / ".codex").absolute()


def _host_role_profile_dir() -> Path:
    """Return the effective user Host role directory.

    Stable Thaliris role identities are installed under the user's Codex home,
    while project-local ``.codex/agents`` is retained as a separate file
    observation for compatibility.  This helper deliberately reports a path,
    not a native Host catalog, because the current hook payload has no such
    observation.
    """
    return _host_home_path() / "agents"


def _profile_files_present_at_session_start(root: Path) -> dict[str, dict[str, object]]:
    """Capture names and byte digests for known Thaliris role profiles."""
    project_dir = root / ".codex" / "agents"
    host_dir = _host_role_profile_dir()

    def snapshot(directory: Path, *, recorded_directory: str | None = None) -> dict[str, object]:
        files: dict[str, str | None] = {}
        for name in roles.agent_profiles():
            path = directory / name
            try:
                if path.is_file():
                    try:
                        files[name] = hashlib.sha256(path.read_bytes()).hexdigest()
                    except OSError:
                        # Preserve the observed filename while making the
                        # missing byte evidence explicit for later comparison.
                        files[name] = None
            except OSError:
                continue
        return {"directory": recorded_directory or str(directory), "files": files}

    return {
        "project": snapshot(project_dir, recorded_directory=".codex/agents"),
        "user_host": snapshot(host_dir),
    }


def _record_session_start(root: Path, payload: dict[str, Any]) -> None:
    with core._lock(root):
        path = _session_dir(root, payload) / "runtime.json"
        state = _load_runtime(path)
        if payload.get("source") in {"startup", "clear"}:
            state.pop("expected_continuation_sha256", None)
        _runtime_metadata(state, payload)
        state.update({"version": 4, "session_start_observed": True, "root_classification": "UNKNOWN"})
        if payload.get("source") == "startup":
            state["session_start_at_ns"] = time.time_ns()
            state["session_start_monotonic_ns"] = time.monotonic_ns()
            # These name and byte-digest observations describe disk only.
            # They do not establish what the Host loaded into its native role
            # catalog or whether the Host runtime profile bytes are active.
            state.pop("native_role_profile_names_at_start", None)
            state[_PROFILE_FILES_PRESENT_AT_SESSION_START] = _profile_files_present_at_session_start(root)
            # No current Codex SessionStart payload carries native role
            # catalog evidence.  Keep the field explicit so a later Host
            # contract can populate it without reinterpreting disk state.
            state[_HOST_ROLE_CATALOG_STATUS] = HOST_ROLE_CATALOG_UNKNOWN
            state[_HOST_RUNTIME_PROFILE_STATUS] = "UNKNOWN"
        _write_capture(path, state)


def _session_start_output(root: Path, payload: dict[str, Any]) -> str:
    """Point the Controller at durable navigation without injecting its contents."""
    if payload.get("source") not in {"startup", "resume", "clear", "compact"}:
        return ""
    context = (
        "Durable navigation is available at:\n"
        ".agent-memory/INDEX.md\n"
        ".milestones/INDEX.md\n\n"
        "Before starting managed work, explicitly read the root navigation; "
        "if either map is missing, establish a minimal thin INDEX first."
    )
    return json.dumps({"hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": context,
    }}, ensure_ascii=False, separators=(",", ":"))


def _record_prompt_telemetry(root: Path, payload: dict[str, Any]) -> None:
    """Record only a root-prompt identity; prompt text never enters telemetry."""
    prompt = payload.get("prompt")
    if not isinstance(prompt, str):
        return
    with core._lock(root):
        path = _session_dir(root, payload) / "runtime.json"
        state = _load_runtime(path)
        _runtime_metadata(state, payload)
        state.setdefault("events_observed", {})["UserPromptSubmit"] = True
        _bounded_append(state, "root_prompt_hashes", hashlib.sha256(prompt.encode("utf-8")).hexdigest())
        _write_capture(path, state)


def _record_delegation_telemetry(root: Path, payload: dict[str, Any]) -> None:
    """Record bounded delegation identity and hash metadata, never its text."""
    tool = payload.get("tool_name") or payload.get("tool")
    if not isinstance(tool, str):
        return
    tool_input = _delegation_input(payload)
    text = _delegation_text(tool_input)
    item = {
        "tool": _tool_basename(tool),
        "role": _normalized_agent_role(tool_input, payload),
        "payload_hash": hashlib.sha256(text.encode("utf-8")).hexdigest() if isinstance(text, str) else None,
        "child_identity_hash": _child_identity_hash(tool, tool_input),
        "dispatch_status": _dispatch_status(_post_tool_response(payload)),
    }
    with core._lock(root):
        path = _session_dir(root, payload) / "runtime.json"
        state = _load_runtime(path)
        _runtime_metadata(state, payload)
        records = state.setdefault("delegation_telemetry", [])
        if isinstance(records, list) and len(records) < MAX_RAW_RECORDS:
            records.append(item)
        _write_capture(path, state)


def _runtime_metadata(state: dict[str, Any], payload: dict[str, Any]) -> None:
    """Attach only compatibility metadata, never prompts, output, or IDs."""
    state["managed_hook_spec_hash"] = managed_hook_spec_hash()
    state["adapter_protocol_version"] = CODEX_ADAPTER_PROTOCOL_VERSION
    state["thaliris_version"] = getattr(__import__("thaliris"), "__version__", "UNKNOWN")
    session = payload.get("session_id")
    if isinstance(session, str) and session:
        state["session_id_hash"] = _identity_hash(session)
    state["observation_sequence"] = int(state.get("observation_sequence", 0)) + 1
    state["observed_at_ns"] = time.time_ns()


def _record_runtime_event(root: Path, payload: dict[str, Any], event: str, tool: str) -> None:
    """Persist bounded evidence that a root hook event reached this adapter."""
    with core._lock(root):
        path = _session_dir(root, payload) / "runtime.json"
        state = _load_runtime(path)
        _runtime_metadata(state, payload)
        observed = state.setdefault("events_observed", {})
        observed[event] = True
        tools = state.setdefault("tools_observed", [])
        normalized = _tool_basename(tool)
        if normalized not in tools and len(tools) < 16:
            tools.append(normalized)
        raw_tools = state.setdefault("tool_names_observed", [])
        if tool not in raw_tools and len(raw_tools) < 16:
            raw_tools.append(tool)
        if event == "PreToolUse":
            tool_input = _delegation_input(payload)
            state.pop("pre_dispatch_rewrite", None)
            state["pre_dispatch_isolation"] = (
                "EXPLICIT" if tool_input.get("fork_turns") == "none" else "NONCOMPLIANT"
            )
        if event == "PostToolUse":
            metrics = state.setdefault("orchestration_metrics", {})
            key = _tool_basename(tool)
            if key in {"wait_agent", "list_agents", "spawn_agent"}:
                counter = f"{key}_calls"
                metrics[counter] = int(metrics.get(counter, 0)) + 1
            response = _post_tool_response(payload)
            if key == "wait_agent" and isinstance(response, dict) and response.get("timed_out") is True:
                metrics["wait_timeouts"] = int(metrics.get("wait_timeouts", 0)) + 1
        _write_capture(path, state)


def _record_controller_guard_event(root: Path, payload: dict[str, Any], action: str, decision: str) -> None:
    """Persist bounded, causal identity for one guarded tool operation.

    The command itself is never retained.  A stable operation hash lets the
    host collector bind PreToolUse, the deny decision, and the absence of a
    side effect to the same call instead of combining unrelated observations.
    """
    with core._lock(root):
        path = _session_dir(root, payload) / "runtime.json"
        state = _load_runtime(path)
        _runtime_metadata(state, payload)
        state.setdefault("events_observed", {})["PreToolUse"] = True
        tool = payload.get("tool_name") or payload.get("tool")
        normalized = _tool_basename(tool) if isinstance(tool, str) else "UNKNOWN"
        tools = state.setdefault("tools_observed", [])
        if normalized not in tools and len(tools) < 16:
            tools.append(normalized)
        raw_name = tool if isinstance(tool, str) else "UNKNOWN"
        raw_tools = state.setdefault("tool_names_observed", [])
        if raw_name not in raw_tools and len(raw_tools) < 16:
            raw_tools.append(raw_name)
        counters = state.setdefault("controller_guard", {"allowed": 0, "blocked": 0, "unknown": 0})
        if decision in counters:
            counters[decision] = int(counters[decision]) + 1
        actions = state.setdefault("controller_actions_observed", [])
        if action not in actions and len(actions) < 16:
            actions.append(action)
        call_id = payload.get("tool_call_id") or payload.get("call_id") or payload.get("id")
        command = _bash_command(payload)
        operation_id = hashlib.sha256(json.dumps({
            "session_id": payload.get("session_id"),
            "call_id": call_id,
            "tool": raw_name,
            "command": command,
        }, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        operations = state.setdefault("controller_guard_operations", [])
        if not any(isinstance(item, dict) and item.get("operation_id") == operation_id for item in operations) and len(operations) < 32:
            operations.append({
                "operation_id": operation_id,
                "tool_call_id": str(call_id) if call_id is not None else None,
                "tool": raw_name,
                "command_sha256": hashlib.sha256(command.encode("utf-8")).hexdigest() if command else None,
                "action": action,
                "decision": decision,
            })
        _write_capture(path, state)


def _record_child_runtime_event(root: Path, payload: dict[str, Any], event: str) -> None:
    """Persist bounded child/tool identities, never payloads or semantic classes."""
    if event != "PreToolUse":
        return
    agent_id = payload.get("agent_id")
    if not isinstance(agent_id, str) or not agent_id:
        return
    tool = payload.get("tool_name") or payload.get("tool")
    if not isinstance(tool, str):
        return
    with core._lock(root):
        path = _session_dir(root, payload) / "runtime.json"
        state = _load_runtime(path)
        _runtime_metadata(state, payload)
        _bounded_append(state, "pretool_child_agent_id_hashes", _identity_hash(agent_id))
        tools = state.setdefault("child_tools_observed", [])
        normalized = _tool_basename(tool)
        if normalized not in tools and len(tools) < 16:
            tools.append(normalized)
        _write_capture(path, state)


def _record_protocol_deviation(
    root: Path,
    payload: dict[str, Any],
    *,
    operation: str,
    target: str,
    blocked: bool,
    notify_controller: bool = True,
) -> None:
    """Record one bounded mechanical protocol deviation for Controller notice."""
    task_id = _active_task_id(root)
    agent_id = payload.get("agent_id")
    agent_type = payload.get("agent_type")
    tool = payload.get("tool_name") or payload.get("tool")
    if task_id is None or not isinstance(agent_id, str) or not agent_id or not isinstance(tool, str):
        return
    role = _native_agent_roles().get(str(agent_type), "unknown")
    item = {
        "agent_id": agent_id[:128],
        "agent_type": agent_type[:128] if isinstance(agent_type, str) else "unknown",
        "role": role,
        "tool": tool[:128],
        "operation": operation[:128],
        "target": target[:256],
        "blocked": blocked,
        "observed_at_ns": time.time_ns(),
        "notice_delivered": not notify_controller,
    }
    fingerprint = hashlib.sha256(json.dumps({
        key: item[key] for key in ("agent_id", "agent_type", "tool", "operation", "target", "blocked")
    }, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    item["fingerprint"] = fingerprint
    with core._lock(root):
        path = _lifecycle_path(root, task_id)
        state = _load_lifecycle(path, task_id)
        deviations = state.setdefault("protocol_deviations", [])
        if not isinstance(deviations, list):
            return
        if len(deviations) >= 32:
            deviations.pop(0)
            state["protocol_deviation_overflow_count"] = int(state.get("protocol_deviation_overflow_count", 0)) + 1
            state["protocol_deviation_overflow_notice_delivered"] = False
        counters = state.setdefault("protocol_deviation_counts", {})
        if isinstance(counters, dict):
            category = f"{role}:{'blocked' if blocked else 'allowed_read'}"
            counters[category] = int(counters.get(category, 0)) + 1
        if notify_controller:
            pending = state.setdefault("protocol_deviation_pending_counts", {})
            if isinstance(pending, dict):
                category = f"{role}:{'blocked' if blocked else 'extra_read'}"
                pending[category] = int(pending.get(category, 0)) + 1
            targets = state.setdefault("protocol_deviation_pending_targets", [])
            if isinstance(targets, list):
                if target in targets:
                    targets.remove(target)
                targets.append(target)
                del targets[:-4]
        deviations.append(item)
        _runtime_metadata(state, payload)
        _write_capture(path, state)


def consume_protocol_deviation_notice(root: Path, task_id: str) -> str | None:
    """Return one bounded aggregate notice and consume the whole pending batch."""
    with core._lock(root):
        path = _lifecycle_path(root, task_id)
        if not path.is_file():
            return None
        state = _load_lifecycle(path, task_id)
        deviations = state.get("protocol_deviations")
        if not isinstance(deviations, list):
            return None
        pending = state.get("protocol_deviation_pending_counts")
        if not isinstance(pending, dict) or not pending:
            return None
        counts = {str(key): int(value) for key, value in pending.items() if type(value) is int and value > 0}
        targets = [str(value) for value in state.get("protocol_deviation_pending_targets", []) if isinstance(value, str)][-4:]
        for item in deviations:
            if isinstance(item, dict):
                item["notice_delivered"] = True
        state["protocol_deviation_pending_counts"] = {}
        state["protocol_deviation_pending_targets"] = []
        _write_capture(path, state)
    reads = sorted((key.split(":", 1)[0], value) for key, value in counts.items() if key.endswith(":extra_read"))
    blocked = sum(value for key, value in counts.items() if key.endswith(":blocked"))
    parts = []
    if reads:
        parts.append("extra context reads " + ", ".join(f"{role}={count}" for role, count in reads))
    if blocked:
        parts.append(f"blocked control mutations={blocked}")
    if targets:
        parts.append("recent targets: " + ", ".join(f"`{target}`" for target in targets))
    overflow = int(state.get("protocol_deviation_overflow_count", 0))
    if overflow:
        parts.append(f"diagnostic ring overflow={overflow}")
    return "Protocol deviations (batched): " + "; ".join(parts) + "."


def _lifecycle_path(root: Path, task_id: str) -> Path:
    return root / ".context" / "audit" / "lifecycle" / f"{_task_key(task_id)}.json"


def _load_lifecycle(path: Path, task_id: str) -> dict[str, Any]:
    if not path.is_file():
        return {"version": LIFECYCLE_STATE_VERSION, "task_id_hash": _task_key(task_id), "children": [], "pending_authorized_spawn": None, "sequence": 0}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("version") != LIFECYCLE_STATE_VERSION or value.get("task_id_hash") != _task_key(task_id) or not isinstance(value.get("children"), list):
        raise ValueError("invalid lifecycle runtime state")
    pending = value.get("pending_authorized_spawn")
    if pending is not None and (
        not isinstance(pending, dict)
        or set(pending) != {"role", "expected_agent_type", "session_id_hash", "authorized_sequence", "task_name_hash", "handoff_id", "task_revision", "producer", "payload_hash", "created_at_ns", "parent_agent_id_hash", "parent_role", "parent_turn_id_hash", "depth", "root_handoff_id", "spawn_tool_use_id_hash"}
        or pending.get("role") not in set(_native_agent_roles().values())
        or pending.get("expected_agent_type") not in _native_agent_roles()
        or not isinstance(pending.get("session_id_hash"), str)
        or not isinstance(pending.get("authorized_sequence"), int)
        or not isinstance(pending.get("handoff_id"), str)
        or type(pending.get("task_revision")) is not int
        or pending.get("producer") != "controller"
        or not isinstance(pending.get("payload_hash"), str)
        or type(pending.get("created_at_ns")) is not int
        or not _valid_parent_metadata(pending)
    ):
        raise ValueError("invalid lifecycle authorized spawns")
    return value


def _valid_parent_metadata(record: dict[str, Any]) -> bool:
    if record.get("depth") == 1:
        return record.get("parent_role") == "controller" and record.get("parent_agent_id_hash") is None and record.get("parent_turn_id_hash") is None and record.get("root_handoff_id") == record.get("handoff_id")
    return (
        record.get("depth") == 2
        and record.get("parent_role") in {"implementer", "focused-implementer", "reviewer"}
        and record.get("role") == "investigator"
        and all(isinstance(record.get(key), str) and record[key] for key in ("parent_agent_id_hash", "parent_turn_id_hash", "root_handoff_id"))
    )


def _parent_binding_matches(state: dict[str, Any], record: dict[str, Any], *, require_live: bool) -> bool:
    if not _valid_parent_metadata(record):
        return False
    if record["depth"] == 1:
        return True
    return any(isinstance(parent, dict)
        and parent.get("managed") is True and parent.get("handoff_bound") is True
        and parent.get("depth") == 1
        and parent.get("agent_id_hash") == record["parent_agent_id_hash"]
        and parent.get("role") == record["parent_role"]
        and parent.get("turn_id_hash") == record["parent_turn_id_hash"]
        and parent.get("session_id_hash") == record.get("session_id_hash")
        and parent.get("handoff_id") == record["root_handoff_id"]
        and (not require_live or parent.get("terminal_state", "RUNNING") in {"RUNNING", "ORPHANED"})
        for parent in state["children"])


def _pending_parent_live(state: dict[str, Any], record: dict[str, Any]) -> bool:
    return _parent_binding_matches(state, record, require_live=True)


def _spawn_parent_matches(record: dict[str, Any], payload: dict[str, Any]) -> bool:
    """Correlate returned native names to the exact reserving actor, never a path."""
    if record.get("session_id_hash") != _session_id_hash(payload):
        return False
    if record.get("parent_agent_id_hash") != _identity_hash(payload.get("agent_id")):
        return False
    if record.get("depth") == 2 and (
        record.get("parent_turn_id_hash") != _turn_id_hash(payload)
        or record.get("parent_role") != _managed_spawn_role({"tool_input": payload})
    ):
        return False
    expected = record.get("spawn_tool_use_id_hash")
    return expected is None or expected == _identity_hash(payload.get("tool_use_id"))


def _bound_child_record(state: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any] | None:
    agent_id = payload.get("agent_id")
    native_type = _native_spawn_agent_type({"tool_input": payload})
    session, turn = _session_id_hash(payload), _turn_id_hash(payload)
    if not isinstance(agent_id, str) or not agent_id or native_type is None or session is None or turn is None:
        return None
    matches = [child for child in state["children"] if isinstance(child, dict)
        and child.get("agent_id_hash") == _identity_hash(agent_id)
        and child.get("agent_type") == native_type
        and child.get("session_id_hash") == session
        and child.get("turn_id_hash") == turn
        and child.get("role") == _native_agent_roles()[native_type]
        and child.get("managed") is True and child.get("handoff_bound") is True
        and isinstance(child.get("handoff_id"), str)
        and _parent_binding_matches(state, child, require_live=False)
        and child.get("terminal_state", "RUNNING") in {"RUNNING", "ORPHANED"}]
    return matches[0] if len(matches) == 1 else None


def _managed_spawn_role(payload: dict[str, Any]) -> str | None:
    """Map only an explicitly supported native agent_type to a semantic role."""
    native_agent_type = _native_spawn_agent_type(payload)
    return _native_agent_roles().get(native_agent_type) if native_agent_type is not None else None


def _native_spawn_agent_type(payload: dict[str, Any]) -> str | None:
    """Accept one exact supported native profile, never a first-match alias."""
    tool_input = _delegation_input(payload)
    supplied = [tool_input[key] for key in ("agent_type", "agentType") if key in tool_input]
    if not supplied or any(not isinstance(value, str) or value not in _native_agent_roles() for value in supplied):
        return None
    return supplied[0] if all(value == supplied[0] for value in supplied) else None


def _bound_managed_child(root: Path, payload: dict[str, Any]) -> bool:
    """Match a child PreToolUse call to one live, handoff-bound role session."""
    task_id = _active_task_id(root)
    if task_id is None:
        return False
    try:
        with core._lock(root):
            state = _load_lifecycle(_lifecycle_path(root, task_id), task_id)
            return _bound_child_record(state, payload) is not None
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return False


def _bound_child_parent_message(root: Path, payload: dict[str, Any]) -> bool:
    """Permit only an exact bound child's unambiguous native parent target."""
    target = _delegation_input(payload).get("target")
    if not isinstance(target, str) or not target:
        return False
    task_id = _active_task_id(root)
    if task_id is None:
        return False
    try:
        with core._lock(root):
            state = _load_lifecycle(_lifecycle_path(root, task_id), task_id)
            child = _bound_child_record(state, payload)
            if child is None:
                return False
            if child["depth"] == 1:
                return target == "/root"
            if child["depth"] != 2:
                return False
            parents = [parent for parent in state["children"] if isinstance(parent, dict)
                and parent.get("managed") is True and parent.get("handoff_bound") is True
                and parent.get("depth") == 1
                and parent.get("agent_id_hash") == child["parent_agent_id_hash"]
                and parent.get("role") == child["parent_role"]
                and parent.get("turn_id_hash") == child["parent_turn_id_hash"]
                and parent.get("session_id_hash") == child["session_id_hash"]
                and parent.get("handoff_id") == child["root_handoff_id"]]
            if len(parents) != 1:
                return False
            target_hash = _identity_hash(target)
            parent = parents[0]
            if target_hash not in {parent.get("agent_id_hash"), parent.get("task_name_hash")}:
                return False
            return sum(
                target_hash in {record.get("agent_id_hash"), record.get("task_name_hash")}
                for record in state["children"]
                if isinstance(record, dict) and record.get("managed") is True and record.get("handoff_bound") is True
            ) == 1
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return False


def _session_id_hash(payload: dict[str, Any]) -> str | None:
    value = payload.get("session_id")
    return _identity_hash(value) if isinstance(value, str) and value else None


def _turn_id_hash(payload: dict[str, Any]) -> str | None:
    value = payload.get("turn_id")
    return _identity_hash(value) if isinstance(value, str) and value else None


def _reserve_managed_spawn(root: Path, payload: dict[str, Any]) -> str:
    """Atomically reserve the one authorized native Codex role-session slot before allowing spawn."""
    task_id = _active_task_id(root)
    if task_id is None:
        return ""
    expected_agent_type = _native_spawn_agent_type(payload)
    role = _native_agent_roles().get(expected_agent_type) if expected_agent_type is not None else None
    if role is None:
        return _permission_deny("THALIRIS_MANAGED_AGENT_REQUIRED: managed tasks may spawn only a supported Thaliris agent profile.")
    tool_input = _delegation_input(payload)
    if tool_input.get("fork_turns") != "none":
        return _permission_deny('THALIRIS_ISOLATION_REQUIRED: use fork_turns="none".')
    nested = payload.get("agent_id") is not None or payload.get("agent_type") is not None
    overrides = {key: tool_input[key] for key in ("model", "reasoning_effort", "thinking", "model_reasoning_effort") if tool_input.get(key) is not None}
    if overrides:
        return _permission_deny("THALIRIS_ROLE_MODEL_OVERRIDE: named native profiles have fixed model/effort; Controller selects an explicit exceptional xhigh profile instead.")
    target_binding = roles.get_codex_binding(role)
    if nested and target_binding is not None and expected_agent_type == target_binding.exceptional_native_profile:
        return _permission_deny("THALIRIS_ROLE_SESSION_DELEGATION: exceptional profiles are Controller-only.")
    session_id_hash = _session_id_hash(payload)
    if session_id_hash is None:
        return _permission_deny("THALIRIS_MANAGED_SESSION_REQUIRED: managed spawn authorization requires a current session identity.")
    try:
        with core._lock(root):
            # Re-read while holding the same lock used by task mutations.
            if _active_task_id(root) != task_id:
                return _permission_deny("THALIRIS_MANAGED_SPAWN_UNAVAILABLE: the active task changed before authorization.")
            path = _lifecycle_path(root, task_id)
            state = _load_lifecycle(path, task_id)
            parent = _bound_child_record(state, payload) if nested else None
            if nested and (parent is None or parent.get("depth") != 1 or not roles.delegation_allowed(parent["role"], role)):
                return _permission_deny("THALIRIS_ROLE_SESSION_DELEGATION: exact bound depth-one Executor/Reviewer parent and Investigator target required.")
            if not nested and not roles.delegation_allowed("controller", role):
                return _permission_deny("THALIRIS_ROLE_SESSION_DELEGATION: unsupported Controller target.")
            active = any(
                isinstance(child, dict)
                and child.get("managed") is True
                and child.get("terminal_state", "RUNNING") in {"RUNNING", "ORPHANED"}
                and child is not parent
                for child in state["children"]
            )
            if active or state["pending_authorized_spawn"] is not None:
                fingerprint = _lifecycle_block_fingerprint(state)
                stall = state.get("stall")
                repeated = isinstance(stall, dict) and stall.get("fingerprint") == fingerprint
                state["stall"] = {"fingerprint": fingerprint, "blocked_spawn_calls": int(stall.get("blocked_spawn_calls", 0)) + 1 if repeated else 1}
                metrics = state.setdefault("metrics", {})
                metrics["blocked_spawn_calls"] = int(metrics.get("blocked_spawn_calls", 0)) + 1
                _runtime_metadata(state, payload)
                _write_capture(path, state)
                if repeated:
                    return _permission_deny("ORCHESTRATION_STALLED: the managed native Codex session lifecycle has no new terminal information; stop recovery attempts until a native lifecycle event arrives.")
                return _permission_deny("THALIRIS_SERIAL_ROLE_SESSION_REQUIRED: wait for the managed native Codex session reservation to complete before spawning another named-role session.")
            state["sequence"] = int(state.get("sequence", 0)) + 1
            task_state = core._load_state(root, active=True)
            if task_state.get("task_id") != task_id:
                return _permission_deny("THALIRIS_MANAGED_SPAWN_UNAVAILABLE: the active task changed before authorization.")
            handoff_text = _delegation_text(_delegation_input(payload))
            if not isinstance(handoff_text, str) or not handoff_text.strip():
                return _permission_deny("THALIRIS_HANDOFF_REQUIRED: managed spawn requires an explicit Controller handoff message.")
            payload_hash = hashlib.sha256(handoff_text.encode("utf-8")).hexdigest()
            handoff_material = f"{task_id}\0{task_state['revision']}\0{session_id_hash}\0{state['sequence']}\0{payload_hash}"
            handoff_id = f"handoff-{hashlib.sha256(handoff_material.encode('utf-8')).hexdigest()[:32]}"
            state["pending_authorized_spawn"] = {
                "role": role,
                "expected_agent_type": expected_agent_type,
                "session_id_hash": session_id_hash,
                "authorized_sequence": state["sequence"],
                "task_name_hash": None,
                "handoff_id": handoff_id,
                "task_revision": task_state["revision"],
                "producer": "controller",
                "payload_hash": payload_hash,
                "created_at_ns": time.time_ns(),
                "parent_agent_id_hash": parent["agent_id_hash"] if parent else None,
                "parent_role": parent["role"] if parent else "controller",
                "parent_turn_id_hash": parent["turn_id_hash"] if parent else None,
                "depth": 2 if parent else 1,
                "root_handoff_id": parent["handoff_id"] if parent else handoff_id,
                "spawn_tool_use_id_hash": _identity_hash(payload.get("tool_use_id")) if isinstance(payload.get("tool_use_id"), str) else None,
            }
            state["stall"] = None
            _runtime_metadata(state, payload)
            _write_capture(path, state)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return _permission_deny("THALIRIS_MANAGED_SPAWN_UNAVAILABLE: managed authorization could not be reserved.")
    return ""


def recover_pending_spawn(root: Path, handoff_id: str) -> dict[str, object]:
    """Clear one exact unbound reservation after Controller-observed failure."""
    task_id = _active_task_id(root)
    if task_id is None:
        raise ValueError("pending spawn recovery requires an ACTIVE task")
    if not isinstance(handoff_id, str) or not re.fullmatch(r"handoff-[0-9a-f]{32}", handoff_id):
        raise ValueError("invalid pending spawn handoff id")
    with core._lock(root):
        if _active_task_id(root) != task_id:
            raise ValueError("pending spawn recovery task is no longer ACTIVE")
        path = _lifecycle_path(root, task_id)
        if not path.is_file():
            raise ValueError("pending spawn recovery state is unavailable")
        state = _load_lifecycle(path, task_id)
        pending = state.get("pending_authorized_spawn")
        bound_child = any(
            isinstance(child, dict)
            and child.get("managed") is True
            and child.get("handoff_id") == handoff_id
            for child in state.get("children", [])
        )
        if bound_child:
            raise ValueError("pending spawn is already bound to an authorized native Codex role session")
        if not isinstance(pending, dict) or pending.get("handoff_id") != handoff_id:
            raise ValueError("pending spawn handoff id does not match")
        recoveries = state.setdefault("spawn_recoveries", [])
        if not isinstance(recoveries, list):
            raise ValueError("invalid pending spawn recovery state")
        if len(recoveries) < 16:
            recoveries.append({"handoff_id": handoff_id, "observed_at_ns": time.time_ns()})
        state["pending_authorized_spawn"] = None
        state["stall"] = None
        metrics = state.setdefault("metrics", {})
        metrics["spawn_recoveries"] = int(metrics.get("spawn_recoveries", 0)) + 1
        _write_capture(path, state)
    return {"ok": True, "task_id": task_id, "handoff_id": handoff_id, "recovered": True}


def _record_subagent_start(root: Path, payload: dict[str, Any]) -> bool:
    """Bind an authorized native child to its explicit Controller handoff."""
    task_id = _active_task_id(root)
    agent_id = payload.get("agent_id")
    agent_type = payload.get("agent_type")
    native_agent_type = _native_spawn_agent_type({"tool_input": {"agent_type": agent_type}})
    role = _native_agent_roles().get(native_agent_type) if native_agent_type is not None else None
    session_id_hash = _session_id_hash(payload)
    turn_id_hash = _turn_id_hash(payload)
    if task_id is None or not isinstance(agent_id, str) or not agent_id or role is None or session_id_hash is None or turn_id_hash is None:
        return False
    with core._lock(root):
        path = _lifecycle_path(root, task_id)
        state = _load_lifecycle(path, task_id)
        state["sequence"] = int(state.get("sequence", 0)) + 1
        child_hash = _identity_hash(agent_id)
        children = state["children"]
        pending = state["pending_authorized_spawn"]
        authorized = (
            isinstance(pending, dict)
            and pending.get("role") == role
            and pending.get("expected_agent_type") == native_agent_type
            and pending.get("session_id_hash") == session_id_hash
            and _pending_parent_live(state, pending)
        )
        prior = next((item for item in children if item.get("agent_id_hash") == child_hash), None)
        bound = authorized and prior is None
        if prior is None:
            children.append({
                "agent_id_hash": child_hash,
                "agent_type": native_agent_type,
                "session_id_hash": session_id_hash,
                "turn_id_hash": turn_id_hash,
                "role": role,
                "managed": bound,
                "handoff_bound": bound,
                "handoff_id": pending.get("handoff_id") if bound else None,
                "task_revision": pending.get("task_revision") if bound else None,
                "producer": pending.get("producer") if bound else None,
                "payload_hash": pending.get("payload_hash") if bound else None,
                "handoff_created_at_ns": pending.get("created_at_ns") if bound else None,
                "started": state["sequence"],
                "stopped": None,
                "terminal_state": "RUNNING",
                "native_terminal_status": None,
                "task_name_hash": pending.get("task_name_hash") if bound else None,
                **{key: pending.get(key) if bound else None for key in ("parent_agent_id_hash", "parent_role", "parent_turn_id_hash", "depth", "root_handoff_id", "spawn_tool_use_id_hash")},
            })
            if bound:
                state["pending_authorized_spawn"] = None
        else:
            collisions = state.setdefault("identity_collisions", [])
            if isinstance(collisions, list) and len(collisions) < 16:
                collisions.append({
                    "agent_id_hash": child_hash,
                    "agent_type": native_agent_type,
                    "pending_handoff_id": pending.get("handoff_id") if authorized else None,
                    "observed_at_ns": time.time_ns(),
                })
        state["stall"] = None
        _runtime_metadata(state, payload)
        _write_capture(path, state)
    # Keep only the old bounded identity-corroboration sample for diagnostics;
    # completion authority remains exclusively in the task-local lifecycle file.
    with core._lock(root):
        runtime_path = _session_dir(root, payload) / "runtime.json"
        runtime = _load_runtime(runtime_path)
        _runtime_metadata(runtime, payload)
        _bounded_append(runtime, "subagent_start_agent_id_hashes", _identity_hash(agent_id))
        _bounded_append(runtime, "subagent_start_agent_types", agent_type[:80] if isinstance(agent_type, str) else None)
        runtime.setdefault("events_observed", {})["SubagentStart"] = True
        _write_capture(runtime_path, runtime)
    return bound


def _record_subagent_stop(root: Path, payload: dict[str, Any]) -> bool:
    task_id = _active_task_id(root)
    agent_id = payload.get("agent_id")
    native_agent_type = _native_spawn_agent_type({"tool_input": {"agent_type": payload.get("agent_type")}})
    session_id_hash = _session_id_hash(payload)
    turn_id_hash = _turn_id_hash(payload)
    if task_id is None or not isinstance(agent_id, str) or not agent_id or native_agent_type is None or session_id_hash is None or turn_id_hash is None:
        return False
    with core._lock(root):
        path = _lifecycle_path(root, task_id)
        state = _load_lifecycle(path, task_id)
        child_hash = _identity_hash(agent_id)
        for child in state["children"]:
            if (
                child.get("agent_id_hash") == child_hash
                and child.get("agent_type") == native_agent_type
                and child.get("session_id_hash") == session_id_hash
                and child.get("turn_id_hash") == turn_id_hash
                and child.get("managed") is True
                and child.get("terminal_state", "RUNNING") != "STOP_ATTESTED"
            ):
                state["sequence"] = int(state.get("sequence", 0)) + 1
                child["stopped"] = state["sequence"]
                child["terminal_state"] = "STOP_ATTESTED"
                # SubagentStop attests this hook path only. It carries no
                # AgentStatus result, so it must never manufacture completed
                # or overwrite a trusted failed native terminal status.
                if child.get("native_terminal_status") not in {"not_found", "interrupted", "errored", "shutdown"}:
                    child["native_terminal_status"] = child.get("native_terminal_status") if child.get("native_terminal_status") == "completed" else None
                state["stall"] = None
                _runtime_metadata(state, payload)
                _write_capture(path, state)
                return True
    return False


def _lifecycle_block_fingerprint(state: dict[str, Any]) -> str:
    """Hash only mechanical in-flight state for repeated-block detection."""
    active = [
        {
            "agent_id_hash": child.get("agent_id_hash"),
            "terminal_state": child.get("terminal_state", "RUNNING"),
            "task_name_hash": child.get("task_name_hash"),
        }
        for child in state.get("children", [])
        if isinstance(child, dict)
        and child.get("managed") is True
        and child.get("terminal_state", "RUNNING") in {"RUNNING", "ORPHANED"}
    ]
    pending = state.get("pending_authorized_spawn")
    return hashlib.sha256(json.dumps({"active": active, "pending": pending}, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _native_terminal_status(value: object) -> str | None:
    """Parse only Codex V2's documented AgentStatus JSON representation."""
    if isinstance(value, str) and value in {"pending_init", "running", "not_found", "interrupted", "shutdown"}:
        return value
    if isinstance(value, dict) and set(value) == {"completed"}:
        return "completed"
    if isinstance(value, dict) and set(value) == {"errored"} and isinstance(value.get("errored"), str):
        return "errored"
    return None


def _child_for_native_name(children: list[object], name: str) -> dict[str, Any] | None:
    name_hash = _identity_hash(name)
    matches = [
        child for child in children
        if isinstance(child, dict)
        and child.get("managed") is True
        and (child.get("task_name_hash") == name_hash or child.get("agent_id_hash") == name_hash)
    ]
    return matches[0] if len(matches) == 1 else None


def _record_native_terminal(state: dict[str, Any], child: dict[str, Any], status: str) -> bool:
    """Release only a proved terminal execution slot; never accept a result."""
    if status == "not_found":
        child["terminal_state"] = "ORPHANED"
        child["native_terminal_status"] = status
        return True
    if status not in {"completed", "interrupted", "errored", "shutdown"}:
        return False
    if child.get("terminal_state") == "STOP_ATTESTED":
        # Preserve the independent stop attestation, but retain the native
        # result when it naturally arrives afterwards. A failure is sticky.
        prior = child.get("native_terminal_status")
        if prior in {"interrupted", "errored", "shutdown"} or prior == status:
            return False
        child["native_terminal_status"] = status
        return True
    state["sequence"] = int(state.get("sequence", 0)) + 1
    child["stopped"] = state["sequence"]
    child["terminal_state"] = "NATIVE_TERMINAL_RECONCILED"
    child["native_terminal_status"] = status
    state["stall"] = None
    return True


def _reconcile_lifecycle_post_tool(root: Path, payload: dict[str, Any], tool: str) -> None:
    """Use naturally returned, identity-bound native statuses to repair liveness.

    This intentionally does not query or schedule anything.  It consumes only
    the current PostToolUse result, requires a canonical native name already
    causally bound to the serial spawn, and keeps successful completion gated
    on SubagentStop.
    """
    task_id = _active_task_id(root)
    response = _post_tool_response(payload)
    if task_id is None or not isinstance(response, dict):
        return
    with core._lock(root):
        path = _lifecycle_path(root, task_id)
        if not path.is_file():
            return
        state = _load_lifecycle(path, task_id)
        changed = observed = False
        if tool == "spawn_agent":
            task_name = response.get("task_name")
            if isinstance(task_name, str) and task_name:
                name_hash = _identity_hash(task_name)
                pending = state.get("pending_authorized_spawn")
                if isinstance(pending, dict) and pending.get("task_name_hash") is None and _spawn_parent_matches(pending, payload):
                    pending["task_name_hash"] = name_hash
                    changed = True
                else:
                    candidates = [
                        child for child in state["children"]
                        if isinstance(child, dict)
                        and child.get("managed") is True
                        and child.get("task_name_hash") is None
                        and child.get("terminal_state", "RUNNING") == "RUNNING"
                        and _spawn_parent_matches(child, payload)
                    ]
                    if len(candidates) == 1:
                        candidates[0]["task_name_hash"] = name_hash
                        changed = True
        elif tool == "interrupt_agent":
            tool_input = _delegation_input(payload)
            target = tool_input.get("target")
            status = _native_terminal_status(response.get("previous_status"))
            if isinstance(target, str) and status is not None:
                child = _child_for_native_name(state["children"], target)
                if child is not None:
                    observed = True
                    metrics = state.setdefault("metrics", {})
                    metrics["reconciliation_attempts"] = int(metrics.get("reconciliation_attempts", 0)) + 1
                    changed = _record_native_terminal(state, child, status)
                    if changed and child.get("terminal_state") == "NATIVE_TERMINAL_RECONCILED":
                        metrics["reconciliation_successes"] = int(metrics.get("reconciliation_successes", 0)) + 1
        elif tool == "list_agents":
            entries = response.get("agents")
            if isinstance(entries, list):
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    name, status = entry.get("agent_name"), _native_terminal_status(entry.get("agent_status"))
                    if not isinstance(name, str) or status is None:
                        continue
                    child = _child_for_native_name(state["children"], name)
                    if child is None:
                        continue
                    observed = True
                    metrics = state.setdefault("metrics", {})
                    metrics["reconciliation_attempts"] = int(metrics.get("reconciliation_attempts", 0)) + 1
                    did_reconcile = _record_native_terminal(state, child, status)
                    changed = changed or did_reconcile
                    if did_reconcile and child.get("terminal_state") == "NATIVE_TERMINAL_RECONCILED":
                        metrics["reconciliation_successes"] = int(metrics.get("reconciliation_successes", 0)) + 1
        if changed or observed:
            _runtime_metadata(state, payload)
            _write_capture(path, state)


def _subagent_start_output(root: Path, payload: dict[str, Any]) -> str:
    # SubagentStart is lifecycle-only. The native spawn message is the sole
    # task-specific semantic input; returning additionalContext here would
    # create a second router and duplicate the Controller's handoff.
    _record_subagent_start(root, payload)
    return ""


def _bounded_append(state: dict[str, Any], key: str, value: str | None) -> None:
    if not value:
        return
    values = state.setdefault(key, [])
    if isinstance(values, list) and value not in values and len(values) < 16:
        values.append(value)


def child_identity_corroboration(root: Path) -> str:
    """Return YES only for an in-record SubagentStart/PreTool identity match."""
    expected = managed_hook_spec_hash()
    for path in (root / ".context" / "audit").glob("*/runtime.json"):
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(state, dict) or state.get("managed_hook_spec_hash") != expected:
            continue
        starts = state.get("subagent_start_agent_id_hashes")
        pretools = state.get("pretool_child_agent_id_hashes")
        if isinstance(starts, list) and isinstance(pretools, list):
            start_hashes = {item for item in starts if isinstance(item, str)}
            pretool_hashes = {item for item in pretools if isinstance(item, str)}
            if start_hashes & pretool_hashes:
                return "YES"
    return "UNKNOWN"


def _bash_command(payload: dict[str, Any]) -> str | None:
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    command = tool_input.get("command") or tool_input.get("cmd")
    return command if isinstance(command, str) and command.strip() else None


def qualifying_child_completed(root: Path) -> bool:
    """Require completion proof from the latest authorized managed handoff."""
    task_id = _active_task_id(root)
    if task_id is None:
        return False
    path = _lifecycle_path(root, task_id)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    managed = [
        child for child in value.get("children", [])
        if isinstance(child, dict) and child.get("managed") is True
    ] if isinstance(value, dict) else []
    latest = max((child for child in managed if child.get("depth") == 1 and child.get("parent_role") == "controller"), key=lambda child: int(child.get("started", -1)), default=None)
    return (
        isinstance(value, dict)
        and value.get("version") == LIFECYCLE_STATE_VERSION
        and value.get("task_id_hash") == _task_key(task_id)
        and value.get("managed_hook_spec_hash") == managed_hook_spec_hash()
        and value.get("adapter_protocol_version") == CODEX_ADAPTER_PROTOCOL_VERSION
        and value.get("pending_authorized_spawn") is None
        and not _managed_child_active(root)
        and isinstance(latest, dict)
        and latest.get("handoff_bound") is True
        and isinstance(latest.get("handoff_id"), str)
        and isinstance(latest.get("payload_hash"), str)
        and latest.get("terminal_state") == "STOP_ATTESTED"
        and latest.get("native_terminal_status") == "completed"
        and isinstance(latest.get("started"), int)
        and isinstance(latest.get("stopped"), int)
    )


def _managed_child_active(root: Path) -> bool:
    task_id = _active_task_id(root)
    if task_id is None:
        return False
    try:
        value = json.loads(_lifecycle_path(root, task_id).read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    return isinstance(value, dict) and value.get("version") == LIFECYCLE_STATE_VERSION and value.get("managed_hook_spec_hash") == managed_hook_spec_hash() and value.get("adapter_protocol_version") == CODEX_ADAPTER_PROTOCOL_VERSION and any(isinstance(child, dict) and child.get("managed") is True and child.get("terminal_state", "RUNNING") in {"RUNNING", "ORPHANED"} for child in value.get("children", []))


def managed_dependency_pending(root: Path, parent_payload: dict[str, Any] | None = None) -> bool:
    """Report whether a managed reservation or live child can be waited on."""
    task_id = _active_task_id(root)
    if task_id is None:
        return False
    try:
        value = json.loads(_lifecycle_path(root, task_id).read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    def selected(record: object) -> bool:
        if not isinstance(record, dict):
            return False
        if parent_payload is None:
            return True
        return (
            record.get("depth") == 2
            and record.get("parent_agent_id_hash") == _identity_hash(parent_payload.get("agent_id"))
            and record.get("parent_turn_id_hash") == _turn_id_hash(parent_payload)
            and record.get("parent_role") == _managed_spawn_role({"tool_input": parent_payload})
            and record.get("session_id_hash") == _session_id_hash(parent_payload)
        )
    return (
        isinstance(value, dict)
        and value.get("version") == LIFECYCLE_STATE_VERSION
        and value.get("managed_hook_spec_hash") == managed_hook_spec_hash()
        and value.get("adapter_protocol_version") == CODEX_ADAPTER_PROTOCOL_VERSION
        and (
            selected(value.get("pending_authorized_spawn"))
            or any(
                selected(child)
                and child.get("managed") is True
                and child.get("terminal_state", "RUNNING") in {"RUNNING", "ORPHANED"}
                for child in value.get("children", [])
            )
        )
    )


def _post_tool_response(payload: dict[str, Any]) -> object:
    """Read the native PostToolUse result across 0.146 payload variants."""
    for key in ("tool_response", "tool_result", "result", "output"):
        if key in payload:
            return payload[key]
    return None


def _record_execution_observation(root: Path, payload: dict[str, Any]) -> None:
    """Keep a privacy-preserving native payload-shape sample for doctor/probes."""
    tool = payload.get("tool_name") or payload.get("tool")
    response_field = next((key for key in ("tool_response", "tool_result", "result", "output") if key in payload), None)
    response = payload.get(response_field) if response_field is not None else None
    item: dict[str, Any] = {
        "tool": _tool_basename(tool) if isinstance(tool, str) else "UNKNOWN",
        "response_field": response_field,
        "response_type": type(response).__name__,
        "outcome": _codex_bash_outcome(response) if isinstance(tool, str) and _tool_basename(tool) == "Bash" else _execution_outcome(response),
    }
    if isinstance(response, dict):
        item["response_keys"] = sorted(str(key) for key in response)[:16]
        nested = response.get("result")
        if isinstance(nested, dict):
            item["nested_result_keys"] = sorted(str(key) for key in nested)[:16]
    with core._lock(root):
        path = _session_dir(root, payload) / "runtime.json"
        state = _load_runtime(path)
        _runtime_metadata(state, payload)
        observed = state.setdefault("execution_observations", [])
        if isinstance(observed, list) and len(observed) < 8:
            observed.append(item)
        _write_capture(path, state)


def _post_tool_succeeded(response: object) -> bool:
    """Treat a completed PostToolUse spawn as success unless it says failure."""
    if isinstance(response, dict):
        if any(response.get(key) is True or response.get(key) not in (None, False, "") for key in ("isError", "failed", "error")):
            return False
        status = response.get("status")
        if isinstance(status, str) and status.strip().lower() in {"error", "failed", "failure", "rejected"}:
            return False
        nested = response.get("result")
        if isinstance(nested, dict):
            return _post_tool_succeeded(nested)
        return True
    if isinstance(response, str) and response.strip().lower() in {"error", "failed", "rejected"}:
        return False
    return True


def _execution_outcome(response: object) -> str:
    """Parse an explicit terminal-result contract for a future supported runtime.

    Codex stable 0.153.4 does not publish this contract for Bash.  Callers on
    that surface must use _codex_bash_outcome(), which intentionally remains
    UNKNOWN even when a synthetic payload happens to contain these fields.
    """
    if not isinstance(response, dict):
        return "UNKNOWN"
    if any(response.get(key) is True or response.get(key) not in (None, False, "") for key in ("isError", "failed", "error")):
        return "FAILED"
    for key in ("exit_code", "exitCode", "returncode", "return_code"):
        value = response.get(key)
        if type(value) is int:
            return "PASSED" if value == 0 else "FAILED"
    nested = response.get("result")
    return _execution_outcome(nested) if isinstance(nested, dict) else "UNKNOWN"


def _codex_bash_outcome(response: object) -> str:
    """Current Codex stable has no version-pinned Bash terminal-status fact."""
    del response
    return "UNKNOWN"


def _context_call(payload: dict[str, Any]) -> tuple[str | None, list[str]]:
    """Recognize a direct context call and its explicit bounded retrieval targets."""
    command = _bash_command(payload)
    if command is None:
        return None, []
    separator_check = command.lstrip()
    if separator_check.startswith("&") and len(separator_check) > 1 and separator_check[1].isspace():
        separator_check = separator_check[1:].lstrip()
    if _COMMAND_SEPARATOR.search(separator_check):
        return None, []
    arguments = _context_arguments(command)
    if arguments is None:
        return None, []
    try:
        tokens = shlex.split(arguments, posix=False)
    except ValueError:
        return None, []
    index = 0
    while index < len(tokens):
        token = tokens[index].strip("\"'")
        if token == "--pretty":
            index += 1
            continue
        if token == "--root" and index + 1 < len(tokens):
            index += 2
            continue
        if token not in _CONTEXT_OPERATIONS:
            return None, []
        operands = [value.strip("\"'")[:256] for value in tokens[index + 1:] if value and not value.startswith("--")]
        if token == "document-get":
            return token, operands[:8]
        if token in {"task-get", "artifact-get", "catalog", "recover-pending-spawn"}:
            return token, operands[:1]
        return token, []
    return None, []


def _context_operation(payload: dict[str, Any]) -> str | None:
    return _context_call(payload)[0]


def _visible_durable_paths(payload: dict[str, Any]) -> list[str]:
    """Best-effort observation of obvious durable paths, not a security boundary."""
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict) or _obvious_write_attempt(payload):
        return []
    materials: list[str] = []
    command = _bash_command(payload)
    if isinstance(command, str):
        materials.append(command)
    serialized = json.dumps(tool_input, ensure_ascii=False, sort_keys=True)
    if serialized not in materials:
        materials.append(serialized)
    targets: list[str] = []
    for material in materials:
        for match in _DURABLE_PATH_TARGET.finditer(material):
            target = match.group(1).replace("\\", "/").rstrip(".,:)]}")[:256]
            if target not in targets:
                targets.append(target)
            if len(targets) == 8:
                return targets
    return targets


def _control_state_target(payload: dict[str, Any]) -> str | None:
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    material = json.dumps(tool_input, ensure_ascii=False, sort_keys=True)
    match = _CONTROL_STATE_TARGET.search(material)
    return match.group(0).replace("\\", "/") if match is not None else None


def _obvious_write_attempt(payload: dict[str, Any]) -> bool:
    tool = payload.get("tool_name") or payload.get("tool")
    if not isinstance(tool, str):
        return False
    if _tool_basename(tool) in _CONTROLLER_MUTATION_TOOL_NAMES:
        return True
    command = _bash_command(payload)
    return isinstance(command, str) and _OBVIOUS_WRITE.search(command) is not None


def _obvious_mutation_tool(tool: str) -> bool:
    return bool(_CHILD_CONTROL_MUTATION_ACTIONS.intersection(re.split(r"[^A-Za-z0-9]+", _tool_basename(tool).casefold())))


def _updated_command_output(payload: dict[str, Any], argument: str) -> str:
    original = payload.get("tool_input")
    if not isinstance(original, dict):
        return _permission_deny("MANAGED_CURRENT_SESSION_NOT_ATTESTED")
    key = next((name for name in ("cmd", "command") if isinstance(original.get(name), str)), None)
    if key is None:
        return _permission_deny("MANAGED_CURRENT_SESSION_NOT_ATTESTED")
    updated = dict(original)
    updated[key] = f"{original[key]} {argument}"
    return json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "allow",
        "updatedInput": updated,
    }}, ensure_ascii=False, separators=(",", ":"))


def _child_pre_tool_output(root: Path, payload: dict[str, Any]) -> str:
    """Allow reads with telemetry; block only mechanical protocol mutations."""
    _best_effort_record(_record_child_runtime_event, root, payload, "PreToolUse")
    if managed_task_state(root)[0] == "ACTIVE" and not _bound_managed_child(root, payload):
        return _permission_deny(
            "THALIRIS_BOUND_ROLE_SESSION_REQUIRED: ACTIVE child execution requires a currently authorized, handoff-bound exact Thaliris role session."
        )
    tool = payload.get("tool_name") or payload.get("tool")
    if not isinstance(tool, str):
        return ""
    normalized = _tool_basename(tool)
    native_agent_type = _native_spawn_agent_type({"tool_input": payload})
    role = _native_agent_roles().get(native_agent_type, "unknown")
    binding = roles.get_codex_binding(role)
    role_names = _native_role_names()
    if normalized in _DELEGATION_TOOL_NAMES:
        if normalized == "send_message" and managed_task_state(root)[0] == "ACTIVE" and _bound_child_parent_message(root, payload):
            return ""
        if normalized != "spawn_agent" or binding is None or not binding.allowed_delegation_targets:
            return _permission_deny(f"THALIRIS_ROLE_SESSION_DELEGATION: a managed {role_names} session may only use its explicit allowed fresh delegation targets.")
        if managed_task_state(root)[0] == "ACTIVE":
            return _reserve_managed_spawn(root, payload)
        target = _managed_spawn_role(payload)
        if target not in binding.allowed_delegation_targets:
            return _permission_deny("THALIRIS_ROLE_SESSION_DELEGATION: only Investigator delegation is permitted.")
    operation, context_targets = _context_call(payload)
    if operation in _CHILD_CONTEXT_MUTATIONS and binding is not None and not binding.controller_control_state_modification_allowed:
        target = f"thaliris {operation}"
        _best_effort_record(_record_protocol_deviation, root, payload, operation=operation, target=target, blocked=True)
        return _permission_deny(f"THALIRIS_ROLE_SESSION_CONTROL_STATE_MUTATION: a {role_names} session may not modify Controller-owned control state.")
    if operation in _CHILD_CONTEXT_READS:
        for target in context_targets or [f"thaliris {operation}"]:
            _best_effort_record(
                _record_protocol_deviation,
                root,
                payload,
                operation=operation,
                target=target,
                blocked=False,
                notify_controller=role in roles.notice_roles(),
            )
        if operation == "task-status":
            return _updated_command_output(payload, "--suppress-protocol-notice")
        return ""
    target = _control_state_target(payload)
    if target is not None:
        mutation = _obvious_write_attempt(payload) or _obvious_mutation_tool(normalized)
        _best_effort_record(
            _record_protocol_deviation,
            root,
            payload,
            operation="control-state-write" if mutation else "control-state-read",
            target=target,
            blocked=mutation,
            notify_controller=mutation or role in roles.notice_roles(),
        )
        if mutation:
            return _permission_deny(f"THALIRIS_ROLE_SESSION_CONTROL_STATE_MUTATION: a {role_names} session may not modify Controller-owned control state.")
    for durable_target in _visible_durable_paths(payload):
        _best_effort_record(
            _record_protocol_deviation,
            root,
            payload,
            operation="durable-path-read",
            target=durable_target,
            blocked=False,
            notify_controller=role in roles.notice_roles(),
        )
    if binding is not None and not binding.repo_write_allowed and _obvious_write_attempt(payload):
        _best_effort_record(
            _record_protocol_deviation,
            root,
            payload,
            operation=f"{role}-write-attempt",
            target=normalized,
            blocked=True,
        )
        code = binding.write_denial_code or "THALIRIS_ROLE_SESSION_WRITE_BLOCKED"
        reason = binding.write_denial_reason or "this role may not write repository files."
        return _permission_deny(f"{code}: {reason}")
    return ""


def _load_runtime(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"version": 4}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("version") != 4:
        raise ValueError("unsupported audit runtime state")
    return value


def _identity_hash(value: object) -> str | None:
    return hashlib.sha256(value.encode("utf-8")).hexdigest() if isinstance(value, str) and value else None


def managed_task_state(root: Path) -> tuple[str, str | None]:
    """Distinguish absent/inactive state from an unreadable mechanical ledger."""
    path = root / ".context" / "state.json"
    if not path.is_file():
        return "NO_TASK", None
    try:
        value = core._load_state(root)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return "INVALID_STATE", None
    if value.get("status") != "ACTIVE":
        return "NO_TASK", None
    task_id = value.get("task_id")
    return ("ACTIVE", task_id) if isinstance(task_id, str) else ("INVALID_STATE", None)


def _active_task_id(root: Path) -> str | None:
    status, task_id = managed_task_state(root)
    return task_id if status == "ACTIVE" else None


def _task_key(task_id: str | None) -> str:
    return hashlib.sha256((task_id or "unknown-task").encode("utf-8")).hexdigest()[:24]


def _start_attestation_path(root: Path, session_hash: str) -> Path:
    return root / ".context" / "audit" / "task-start-attestations" / f"{session_hash}.json"


def _direct_init_call(root: Path, payload: dict[str, Any]) -> bool:
    """Recognize only a direct init of this worktree in the Host's Bash input."""
    command = _bash_command(payload)
    if command is None:
        return False
    separator_check = command.lstrip()
    if separator_check.startswith("&") and len(separator_check) > 1 and separator_check[1].isspace():
        separator_check = separator_check[1:].lstrip()
    if _COMMAND_SEPARATOR.search(separator_check):
        return False
    arguments = _context_arguments(command)
    if arguments is None:
        return False
    try:
        tokens = [token.strip("\"'") for token in shlex.split(arguments, posix=False)]
    except ValueError:
        return False
    index = 0
    if index < len(tokens) and tokens[index] == "--root":
        if index + 1 >= len(tokens) or not tokens[index + 1]:
            return False
        target = Path(tokens[index + 1])
        cwd = payload.get("cwd")
        base = Path(cwd) if isinstance(cwd, str) and cwd else root
        if not target.is_absolute():
            target = base / target
        if target.resolve(strict=False) != root.resolve(strict=False):
            return False
        index += 2
    return tokens[index:] == ["init"]


def _post_init_attestation(root: Path, payload: dict[str, Any], managed_hook_abi: str | None, controller_bridge_sha256: str | None) -> str:
    """Deliver the admission proof in the successful init callback itself."""
    if managed_task_state(root)[0] != "NO_TASK" or not _direct_init_call(root, payload):
        return ""
    response = _post_tool_response(payload)
    if response is None or not _post_tool_succeeded(response) or _execution_outcome(response) == "FAILED":
        return ""
    return _issue_task_start_attestation(root, payload, managed_hook_abi, controller_bridge_sha256, event="PostToolUse")


def _session_role_profile_snapshot(root: Path, session_hash: str) -> tuple[dict[str, str | None], str, dict[str, str | None]] | None:
    try:
        runtime = json.loads((root / ".context" / "audit" / session_hash[:24] / "runtime.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None
    if (
        not isinstance(runtime, dict) or runtime.get("session_id_hash") != session_hash
        or runtime.get("managed_hook_spec_hash") != managed_hook_spec_hash()
        or runtime.get("adapter_protocol_version") != CODEX_ADAPTER_PROTOCOL_VERSION
        or type(runtime.get("session_start_monotonic_ns")) is not int
    ):
        return None
    snapshot = runtime.get(_PROFILE_FILES_PRESENT_AT_SESSION_START)
    if not isinstance(snapshot, dict):
        return None
    project = snapshot.get("project")
    user_host = snapshot.get("user_host")
    if not isinstance(project, dict) or not isinstance(user_host, dict):
        return None
    project_directory = project.get("directory")
    project_files = project.get("files")
    host_directory = user_host.get("directory")
    host_files = user_host.get("files")
    if (
        project_directory != ".codex/agents"
        or not isinstance(project_files, dict)
        or not isinstance(host_directory, str)
        or not host_directory
        or not isinstance(host_files, dict)
    ):
        return None
    allowed_names = set(roles.agent_profiles())
    for files in (project_files, host_files):
        if any(
            not isinstance(name, str)
            or name not in allowed_names
            or (digest is not None and (not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None))
            for name, digest in files.items()
        ):
            return None
    return project_files, host_directory, host_files


def new_role_profile_files(root: Path, session_hash: str) -> list[str] | None:
    """Find known role-profile filenames absent from this session's disk snapshot."""
    snapshot = _session_role_profile_snapshot(root, session_hash)
    if snapshot is None:
        return None
    project_files, host_directory, host_files = snapshot
    current_project_dir = root / ".codex" / "agents"
    current_host_dir = Path(host_directory)
    added = [
        f".codex/agents/{name}" for name in roles.agent_profiles()
        if (current_project_dir / name).is_file() and name not in project_files
    ]
    added.extend(
        str(current_host_dir / name) for name in roles.agent_profiles()
        if (current_host_dir / name).is_file() and name not in host_files
    )
    return sorted(added)


def changed_role_profile_files(root: Path, session_hash: str) -> list[str] | None:
    """Find existing known role-profile filenames whose bytes changed since SessionStart.

    Missing or unreadable hash evidence remains UNKNOWN.  A byte comparison is
    a disk observation and cannot prove what a Host runtime currently uses.
    """
    snapshot = _session_role_profile_snapshot(root, session_hash)
    if snapshot is None:
        return None
    project_files, host_directory, host_files = snapshot
    current_directories = {
        "project": (root / ".codex" / "agents", project_files),
        "user_host": (Path(host_directory), host_files),
    }
    changed: list[str] = []
    unknown = False
    for label, (directory, expected_files) in current_directories.items():
        for name, expected_digest in expected_files.items():
            path = directory / name
            try:
                if not path.is_file():
                    continue
                if expected_digest is None:
                    unknown = True
                    continue
                current_digest = hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError:
                unknown = True
                continue
            if current_digest != expected_digest:
                changed.append(f".codex/agents/{name}" if label == "project" else str(path))
    return sorted(changed) if changed else (None if unknown else [])


def role_catalog_session_status(root: Path, session_hash: str) -> str:
    added = new_role_profile_files(root, session_hash)
    if added is None:
        return HOST_ROLE_CATALOG_UNKNOWN
    if added:
        return NEW_ROLE_CATALOG_IDENTITY_NOT_ACTIVE
    changed = changed_role_profile_files(root, session_hash)
    if changed:
        return PROFILE_BYTES_CHANGED_SINCE_SESSION_START
    # The current hook payload has no authenticated native Host catalog
    # observation.  Unchanged disk bytes and writable audit fields cannot
    # promote the result to a verified Host runtime profile status.
    return HOST_ROLE_CATALOG_UNKNOWN


def _issue_task_start_attestation(root: Path, payload: dict[str, Any], managed_hook_abi: str | None = None, controller_bridge_sha256: str | None = None, *, event: str = "PreToolUse") -> str:
    session_hash = _session_id_hash(payload)
    marker = root / ".codex" / "thaliris.json"
    if (
        event not in {"PreToolUse", "PostToolUse"}
        or session_hash is None or managed_hook_abi != MANAGED_HOOK_ABI
        or not isinstance(controller_bridge_sha256, str)
        or re.fullmatch(r"[0-9a-f]{64}", controller_bridge_sha256) is None
        or marker.is_symlink() or not marker.is_file()
        or marker.read_bytes() != b'{"format":"thaliris-project-activation-v1"}\n'
    ):
        return ""
    with core._lock(root):
        path = _start_attestation_path(root, session_hash)
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            record = None
        now = time.time_ns()
        if not (
            isinstance(record, dict)
            and record.get("version") == 2
            and record.get("session_id_hash") == session_hash
            and record.get("managed_hook_spec_hash") == managed_hook_spec_hash()
            and record.get("adapter_protocol_version") == CODEX_ADAPTER_PROTOCOL_VERSION
            and record.get("managed_hook_abi") == MANAGED_HOOK_ABI
            and record.get("controller_bridge_sha256") == controller_bridge_sha256
            and isinstance(record.get("token"), str)
            and re.fullmatch(rf"v2\.{session_hash}\.[A-Za-z0-9_-]{{16,128}}", record["token"]) is not None
            and type(record.get("created_at_ns")) is int
            and type(record.get("expires_at_ns")) is int
            and record["created_at_ns"] <= now <= record["expires_at_ns"]
        ):
            token = f"v2.{session_hash}.{secrets.token_urlsafe(24)}"
            record = {
                "version": 2,
                "token": token,
                "session_id_hash": session_hash,
                "managed_hook_spec_hash": managed_hook_spec_hash(),
                "adapter_protocol_version": CODEX_ADAPTER_PROTOCOL_VERSION,
                "managed_hook_abi": MANAGED_HOOK_ABI,
                "controller_bridge_sha256": controller_bridge_sha256,
                "created_at_ns": now,
                "expires_at_ns": now + _START_ATTESTATION_TTL_NS,
            }
            _write_capture(path, record)
        token = record["token"]
    return json.dumps({"hookSpecificOutput": {
        "hookEventName": event,
        "additionalContext": f"Current-session Thaliris admission proof: --hook-attestation {token}. Pass it with the Controller bridge SHA-256 returned by init or bootstrap-check when calling task-start.",
    }}, ensure_ascii=False, separators=(",", ":"))


def consume_task_start_attestation(root: Path, token: str | None, controller_bridge_sha256: str | None = None) -> str:
    """Consume one current-hook, current-session bearer attestation."""
    error = ValueError("MANAGED_CURRENT_SESSION_NOT_ATTESTED")
    if not isinstance(token, str):
        raise error
    match = re.fullmatch(r"v2\.([0-9a-f]{64})\.([A-Za-z0-9_-]{16,128})", token)
    if match is None:
        raise error
    path = _start_attestation_path(root, match.group(1))
    with core._lock(root):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            raise error
        valid = (
            isinstance(record, dict)
            and record.get("version") == 2
            and record.get("token") == token
            and record.get("session_id_hash") == match.group(1)
            and record.get("managed_hook_spec_hash") == managed_hook_spec_hash()
            and record.get("adapter_protocol_version") == CODEX_ADAPTER_PROTOCOL_VERSION
            and record.get("managed_hook_abi") == MANAGED_HOOK_ABI
            and record.get("controller_bridge_sha256") == controller_bridge_sha256
            and type(record.get("created_at_ns")) is int
            and type(record.get("expires_at_ns")) is int
            and record["created_at_ns"] <= time.time_ns() <= record["expires_at_ns"]
        )
        if not valid:
            raise error
        try:
            path.unlink()
        except OSError:
            raise error
    return match.group(1)


def _write_capture(path: Path, state: dict[str, Any]) -> None:
    core._atomic_write(path, (json.dumps(state, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8"))


def _normalized_agent_role(tool_input: dict[str, Any], payload: dict[str, Any]) -> str:
    value = next(
        (tool_input.get(key) for key in ("agent_type", "agentType", "role", "agent_role") if tool_input.get(key) is not None),
        next((payload.get(key) for key in ("agent_type", "agentType", "role", "agent_role") if payload.get(key) is not None), None),
    )
    if not isinstance(value, str) or not value.strip():
        return "unknown"
    normalized = "-".join(value.strip().lower().replace("_", "-").split())
    aliases = roles.role_aliases()
    return aliases.get(normalized, normalized[:64])


def _child_identity_hash(tool: str, tool_input: dict[str, Any]) -> str | None:
    if _tool_basename(tool) not in {"followup_task", "send_input", "send_message"}:
        return None
    for key in ("task_id", "child_id", "target", "task_name", "agent_id", "id"):
        value = tool_input.get(key)
        if isinstance(value, (str, int)) and str(value):
            return _identity_hash(f"{key}:{value}")
    return None


def _tool_basename(tool: str) -> str:
    """Normalize dotted and 0.146 V2 flattened collaboration tool names."""
    dotted = tool.rsplit(".", 1)[-1]
    if dotted != tool:
        return dotted
    if tool.startswith("collaboration"):
        return tool[len("collaboration") :]
    return tool


def _delegation_input(payload: dict[str, Any]) -> dict[str, Any]:
    """Read the native tool input without retaining unrelated payload fields.

    V2 uses ``tool_input``.  Older V1 ``send_input`` events can expose only
    an ``input`` object (or, in minimal payloads, the message fields directly).
    The fallback is deliberately narrow and only supplies fields needed for
    text, role normalization, and a hashed child identity.
    """
    value = payload.get("tool_input")
    if isinstance(value, dict) and value:
        return value
    value = payload.get("input")
    if isinstance(value, dict):
        return value
    if isinstance(payload.get("tool_input"), dict):
        return payload["tool_input"]
    return {key: payload[key] for key in ("message", "input", "text", "agent_type", "agentType", "role", "agent_role", "task_id", "child_id", "target", "task_name", "agent_id", "id", "fork_turns", "isolation_reason", "fork_turns_reason", "model", "reasoning_effort", "thinking", "model_reasoning_effort") if key in payload}


def _delegation_text(tool_input: dict[str, Any]) -> object:
    for key in ("message", "input", "text"):
        value = tool_input.get(key)
        if isinstance(value, str):
            return value
    return None


def _isolation_classification(tool: str, tool_input: dict[str, Any], _role: str) -> dict[str, str] | None:
    """Classify every completed native root spawn, independent of agent_type."""
    if _tool_basename(tool) != "spawn_agent":
        return None
    fork = tool_input.get("fork_turns")
    if fork == "none":
        return {"required": "YES", "fork_turns": "NONE", "status": "PASS"}
    if fork is None:
        return {"required": "YES", "fork_turns": "MISSING", "status": "FAIL"}
    if fork == "all":
        return {"required": "YES", "fork_turns": "ALL", "status": "FAIL"}
    if isinstance(fork, str) and fork in {"1", "2"}:
        return {"required": "YES", "fork_turns": "SMALL", "status": "FAIL"}
    return {"required": "YES", "fork_turns": "OTHER", "status": "FAIL"}


def _pre_tool_output(payload: dict[str, Any], root: Path | None = None, managed_hook_abi: str | None = None, controller_bridge_sha256: str | None = None) -> str:
    """Enforce the small ACTIVE Root tool boundary before native dispatch."""
    tool = payload.get("tool_name") or payload.get("tool")
    if not isinstance(tool, str):
        return ""
    root = _hook_repository_root(root or Path.cwd(), payload)
    normalized = _tool_basename(tool)
    state_status, _task_id = managed_task_state(root)
    operation = _context_operation(payload) if state_status != "NO_TASK" and normalized in _CONTROLLER_EXECUTION_TOOL_NAMES else None

    if state_status == "INVALID_STATE":
        # Damaged managed state does not make unrelated native tools unsafe.
        # Deny only direct Controller-owned mutations that are mechanically
        # visible without interpreting an arbitrary command or tool name.
        target = _control_state_target(payload)
        if operation in _CHILD_CONTEXT_MUTATIONS or (
            target is not None and (_obvious_write_attempt(payload) or _obvious_mutation_tool(normalized))
        ):
            _best_effort_record(_record_controller_guard_event, root, payload, "INVALID_STATE", "blocked")
            return _permission_deny("THALIRIS_INVALID_STATE: managed control is unavailable until the task state is diagnosed or repaired.")
        return ""

    if state_status == "NO_TASK" and normalized == "Bash":
        return _issue_task_start_attestation(root, payload, managed_hook_abi, controller_bridge_sha256)

    if state_status == "ACTIVE":
        if normalized in _FRESH_CHILD_REUSE_TOOL_NAMES or normalized == "Agent":
            _best_effort_record(_record_controller_guard_event, root, payload, "CHILD_REUSE", "blocked")
            return _permission_deny("THALIRIS_FRESH_ROLE_SESSION_REQUIRED: continue work with a new named-role spawn_agent(fork_turns=\"none\") handoff.")
        if normalized == "spawn_agent":
            tool_input = _delegation_input(payload)
            if tool_input.get("fork_turns") != "none":
                return _permission_deny(f"THALIRIS_ISOLATION_REQUIRED: spawn a fresh {_native_role_names()} session explicitly with fork_turns=\"none\".")
            return _reserve_managed_spawn(root, payload)
        if normalized in _ROOT_MANAGED_TOOL_NAMES:
            _best_effort_record(_record_controller_guard_event, root, payload, normalized, "allowed")
            return ""
        if operation in _ACTIVE_ROOT_CONTEXT_OPERATIONS:
            _best_effort_record(_record_controller_guard_event, root, payload, f"CONTEXT_{operation}", "allowed")
            return ""
        if operation == "task-show":
            _best_effort_record(_record_controller_guard_event, root, payload, "CONTEXT_task-show", "blocked")
            return _permission_deny("THALIRIS_BOUNDED_RETRIEVAL_REQUIRED: use task-status or task-get for ACTIVE Controller retrieval.")
        _best_effort_record(_record_controller_guard_event, root, payload, "NON_CONTROL_TOOL", "blocked")
        return _permission_deny(_CONTROLLER_BOUNDARY_REASON)

    # NO_TASK is transparent: ordinary Codex workflows are not managed and
    # therefore do not inherit Thaliris spawn isolation requirements.
    return ""


def _permission_deny(reason: str) -> str:
    return json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }, ensure_ascii=False, separators=(",", ":"))


def _dispatch_status(response: object) -> str:
    rejected = {"error", "failed", "failure", "rejected"}
    accepted = {"ok", "success", "completed"}
    if isinstance(response, str):
        return "REJECTED" if response.strip().lower() in rejected else "UNKNOWN"
    if not isinstance(response, dict):
        return "UNKNOWN"
    status = response.get("status")
    normalized = status.strip().lower() if isinstance(status, str) else None
    explicit_failure = any(
        response.get(key) is True or response.get(key) not in (None, False, "")
        for key in ("isError", "failed", "error")
    )
    if explicit_failure or normalized in rejected:
        return "REJECTED"
    nested = response.get("result")
    nested_status = _dispatch_status(nested) if isinstance(nested, (dict, str)) else "UNKNOWN"
    if nested_status != "UNKNOWN":
        return nested_status
    if response.get("isError") is False or response.get("success") is True or normalized in accepted:
        return "ACCEPTED"
    return "UNKNOWN"
