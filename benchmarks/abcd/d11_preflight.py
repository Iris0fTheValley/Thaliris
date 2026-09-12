"""Deterministic formal-run preflight; no task model workflow is started."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import queue
import threading
from typing import Any, Iterable

from candidate_manifest import build_manifest
from d11_sources import verify_source_registry
from trusted_surface import identity as trusted_identity, mutation_probe, verify as verify_trusted
from thaliris.protocol import ROUTING_PROTOCOL_MARKER, ROUTING_PROTOCOL_VERSION


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git(root: Path, *args: str) -> str | None:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def _hash_files(paths: Iterable[Path]) -> str:
    entries = [{"path": str(path.resolve()), "sha256": _sha(path)} for path in sorted(paths, key=str)]
    return hashlib.sha256(json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _fact_identity(value: dict[str, Any]) -> str:
    """Content identity used by host-observed fact envelopes."""
    payload = {key: item for key, item in value.items() if key != "identity"}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _unexpected_status(status: str | None) -> str:
    """Keep only real mutations, ignoring the known context overlay."""
    if not status:
        return ""
    allowed = {".codex/", ".agent-memory/", ".milestones/", ".context/", "AGENTS.md", ".gitignore", "docs/thaliris-role-packs.md"}
    kept: list[str] = []
    for line in status.splitlines():
        # Porcelain status always reserves two columns (XY), but either
        # column may contain a status letter, so do not assume a leading
        # space before the path.
        path = line[2:].lstrip() if len(line) >= 3 else line
        if " -> " in path:
            path = path.rsplit(" -> ", 1)[-1]
        normalized = path.replace("\\", "/")
        if not any(normalized == item or normalized.startswith(item) for item in allowed):
            kept.append(line)
    return "\n".join(kept)


def _setup_overlay_manifest(root: Path, status: str | None) -> dict[str, Any]:
    """Freeze the bounded files setup is allowed to materialize.

    A clean-checkout result alone loses which overlay was present and permits
    a later run to silently replace it.  Record status, current bytes, and a
    deterministic identity so the frozen run can bind setup to this exact
    checkout state.
    """
    root = root.resolve()
    allowed = {".codex/", ".agent-memory/", ".milestones/", ".context/", "AGENTS.md", ".gitignore", "docs/thaliris-role-packs.md"}
    status_by_path: dict[str, str] = {}
    unknown: list[str] = []
    for line in (status or "").splitlines():
        path = line[2:].lstrip() if len(line) >= 3 else line
        if " -> " in path:
            path = path.rsplit(" -> ", 1)[-1]
        normalized = path.replace("\\", "/")
        if not any(normalized == item or normalized.startswith(item) for item in allowed):
            unknown.append(line)
        else:
            status_by_path[normalized] = line[:2]
    # Git does not list ignored setup state.  Enumerate the explicitly
    # allowed surface itself so .context/state/audit (and similar initial
    # artifacts) are frozen by exact bytes even when porcelain is empty.
    paths: set[str] = set(status_by_path)
    for allowed_path in allowed:
        target = root.joinpath(*allowed_path.rstrip("/").split("/"))
        if target.is_file():
            paths.add(allowed_path)
        elif target.is_dir() and not target.is_symlink():
            for child in target.rglob("*"):
                if child.is_file() and not child.is_symlink():
                    paths.add(child.relative_to(root).as_posix())
    entries = []
    for normalized in sorted(paths):
        target = root.joinpath(*normalized.split("/"))
        if not target.is_file() or target.is_symlink():
            # A deleted/status-only path is part of the frozen state too.
            entries.append({"path": normalized, "status": status_by_path.get(normalized), "sha256": None})
            continue
        entries.append({"path": normalized, "status": status_by_path.get(normalized, "  "), "sha256": _sha(target)})
    entries.sort(key=lambda item: item["path"])
    payload = {"root": str(root), "paths": entries, "unknown_status": sorted(unknown), "valid": not unknown}
    identity = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {**payload, "identity": identity}


def _adapter_generated_hashes(adapter_root: Path) -> dict[str, Any] | None:
    """Render expected generated bytes from the adapter checkout itself."""
    script = (
        "import hashlib, json; from thaliris import codex_adapter; "
        "h=lambda b: hashlib.sha256(b).hexdigest(); "
        "print(json.dumps({'role_pack':h(codex_adapter.ROLE_PACKS.encode()),"
        "'profiles':{n:h(codex_adapter._agent_profile(n.removesuffix('.toml'),r,m,e)) "
        "for n,(m,e,r) in codex_adapter._AGENT_PROFILES.items()}}))"
    )
    environment = os.environ.copy()
    source = str((adapter_root / "src").resolve())
    environment["PYTHONPATH"] = source + (os.pathsep + environment["PYTHONPATH"] if environment.get("PYTHONPATH") else "")
    result = subprocess.run([sys.executable, "-c", script], cwd=adapter_root, env=environment, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return None
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def discover_hooks_app_server(codex_executable: Path, project_root: Path, *, timeout_seconds: float = 10.0) -> dict[str, Any]:
    """Ask the native app-server for hook metadata; never infer trust from files."""
    project_root = project_root.resolve()
    request = json.dumps({"id": 1, "method": "initialize", "params": {"clientInfo": {"name": "thaliris-preflight", "version": "1"}}}) + "\n"
    request += json.dumps({"id": 2, "method": "hooks/list", "params": {"cwds": [str(project_root)]}}) + "\n"
    try:
        process = subprocess.Popen([str(codex_executable.resolve()), "app-server", "--stdio"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
        assert process.stdin is not None and process.stdout is not None
        process.stdin.write(request)
        process.stdin.flush()
        lines: queue.Queue[str] = queue.Queue()
        reader = threading.Thread(target=lambda: [lines.put(line) for line in process.stdout], daemon=True)
        reader.start()
        response = None
        deadline = __import__("time").monotonic() + timeout_seconds
        while __import__("time").monotonic() < deadline:
            try:
                line = lines.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict) and value.get("id") == 2:
                response = value.get("result")
                break
        if not isinstance(response, dict):
            return {"status": "NOT_OBSERVED", "code": "HOOK_INTROSPECTION_NOT_OBSERVED"}
        data = response.get("data")
        entry = next((item for item in data if isinstance(item, dict) and Path(item.get("cwd", "")).resolve() == project_root), None) if isinstance(data, list) else None
        hooks = entry.get("hooks", []) if isinstance(entry, dict) else []
        # Match the complete managed hook set by semantic event, matcher,
        # command suffix, and SubagentStart's explicit context limit. Extra
        # user hooks are allowed, but cannot substitute for a missing managed
        # hook.  The app-server response is the runtime fact; the project file
        # is not treated as proof that the hook was loaded.
        from thaliris.intent_audit import POST_TOOL_MATCHER, PRE_TOOL_MATCHER, _hook_command_prefix
        expected_command_prefix = _hook_command_prefix()
        expected_events = {
            "sessionStart": ("SessionStart", None, None),
            "userPromptSubmit": ("UserPromptSubmit", None, None),
            "preToolUse": ("PreToolUse", PRE_TOOL_MATCHER, None),
            "postToolUse": ("PostToolUse", POST_TOOL_MATCHER, None),
            "subagentStart": ("SubagentStart", None, 0),
            "subagentStop": ("SubagentStop", None, None),
            "stop": ("Stop", None, None),
        }
        expected: dict[str, dict[str, Any]] = {}
        for item in hooks:
            if not isinstance(item, dict) or item.get("eventName") not in expected_events:
                continue
            event_name = str(item["eventName"])
            expected[event_name] = item
        exact = True
        missing: list[str] = []
        for event_name, (command_event, _matcher, context_limit) in expected_events.items():
            item = expected.get(event_name)
            if not isinstance(item, dict):
                missing.append(event_name)
                exact = False
                continue
            command = str(item.get("command") or "")
            expected_command = f"{expected_command_prefix} {command_event}".lower()
            if command.strip().lower() != expected_command or item.get("handlerType") != "command" or not isinstance(item.get("currentHash"), str) or not item.get("currentHash"):
                exact = False
            expected_matcher = _matcher
            actual_matcher = item.get("matcher")
            if expected_matcher is None:
                if actual_matcher not in {None, ""}:
                    exact = False
            elif actual_matcher != expected_matcher:
                exact = False
            if context_limit is None:
                if item.get("additionalContextLimit") not in {None, 0}:
                    exact = False
            elif item.get("additionalContextLimit") != context_limit:
                exact = False
            if item.get("enabled") is not True or item.get("trustStatus") not in {"trusted", "managed"}:
                exact = False
        discovered = bool(hooks) and not missing
        enabled = discovered and exact and all(item.get("enabled") is True for item in expected.values())
        trusted = discovered and exact and all(item.get("trustStatus") in {"trusted", "managed"} for item in expected.values())
        definition_path = Path(str(hooks[0].get("sourcePath"))).resolve() if hooks and hooks[0].get("sourcePath") else None
        current_hashes = {
            str(item.get("eventName")): item.get("currentHash")
            for item in hooks if isinstance(item, dict) and item.get("eventName")
        }
        managed_flags = {
            str(item.get("eventName")): item.get("isManaged")
            for item in hooks if isinstance(item, dict) and item.get("eventName")
        }
        return {
            "status": "PASS" if discovered and enabled and trusted else "FAIL",
            "project_identity": str(project_root),
            "project_discovered": entry is not None,
            "hook_discovered": discovered,
            "hook_enabled": enabled,
            "hook_trusted": trusted,
            "exact_managed_hooks": exact and not missing,
            "missing_managed_hooks": missing,
            "hook_definition_path": str(definition_path) if definition_path else None,
            "hook_definition_sha256": _sha(definition_path) if definition_path and definition_path.is_file() else None,
            "trust_statuses": sorted({str(item.get("trustStatus")) for item in hooks if isinstance(item, dict)}),
            "current_hashes": current_hashes,
            "managed_flags": managed_flags,
            "hooks": hooks,
        }
    except (OSError, AssertionError, subprocess.SubprocessError) as exc:
        return {"status": "NOT_OBSERVED", "code": "HOOK_INTROSPECTION_NOT_OBSERVED", "error": str(exc)}
    finally:
        try:
            process.terminate()
            process.wait(timeout=1)
        except (UnboundLocalError, OSError):
            pass


def run_preflight(
    adapter_root: Path,
    candidate_root: Path,
    *,
    expected_adapter_sha: str,
    harness_paths: Iterable[Path],
    evaluator_path: Path,
    trusted_paths: Iterable[Path] = (),
    trusted_mutation_probe_path: Path | None = None,
    candidate_policy: dict[str, Any] | None = None,
    gold_result: dict[str, Any] | None = None,
    base_result: dict[str, Any] | None = None,
    no_edit_identity: str | None = None,
    base_identity: str | None = None,
    smoke_result: dict[str, Any] | None = None,
    source_registry: dict[str, Any] | None = None,
    trusted_runtime_attack_result: str | None = None,
    calibration_attestation: dict[str, Any] | None = None,
    hook_discovery: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a fact ledger suitable for freezing, never a model report."""
    adapter_root = adapter_root.resolve()
    candidate_root = candidate_root.resolve()
    if adapter_root == candidate_root:
        raise ValueError("adapter_root and candidate_root must be different checkouts")
    checks: dict[str, Any] = {}
    actual_adapter = _git(adapter_root, "rev-parse", "HEAD")
    checks["adapter_sha"] = {"expected": expected_adapter_sha, "actual": actual_adapter, "pass": actual_adapter == expected_adapter_sha}
    routing = adapter_root / "docs" / "thaliris-routing-protocol.md"
    protocol_text = routing.read_text(encoding="utf-8") if routing.is_file() else ""
    checks["product_protocol"] = {"path": str(routing), "sha256": _sha(routing) if routing.is_file() else None, "version": ROUTING_PROTOCOL_VERSION if ROUTING_PROTOCOL_MARKER in protocol_text else None, "pass": routing.is_file() and ROUTING_PROTOCOL_MARKER in protocol_text}
    harness = [Path(path) for path in harness_paths]
    checks["benchmark_harness"] = {"paths": [str(path.resolve()) for path in harness], "sha256": _hash_files(harness) if all(path.is_file() for path in harness) else None, "pass": bool(harness) and all(path.is_file() for path in harness)}
    evaluator_path = evaluator_path.resolve()
    checks["evaluator"] = {"path": str(evaluator_path), "sha256": _sha(evaluator_path) if evaluator_path.is_file() else None, "pass": evaluator_path.is_file()}
    trusted = list(trusted_paths)
    frozen_trusted = trusted_identity(trusted) if trusted and all(path.is_file() for path in trusted) else None
    outside_candidate = bool(trusted) and all(
        not path.resolve().is_relative_to(candidate_root) for path in trusted
    )
    checks["trusted_surface"] = {"identity": frozen_trusted, "paths": [str(path.resolve()) for path in trusted], "outside_candidate_root": outside_candidate, "pass": bool(trusted) and outside_candidate and frozen_trusted is not None and verify_trusted(frozen_trusted, trusted)}
    mutation_result = mutation_probe(trusted_mutation_probe_path) if trusted_mutation_probe_path is not None else "NOT_OBSERVED"
    probe_bound = bool(trusted_mutation_probe_path and any(trusted_mutation_probe_path.resolve() == path.resolve() for path in trusted))
    checks["trusted_runtime_immutability"] = {
        "probe_path": str(trusted_mutation_probe_path) if trusted_mutation_probe_path else None,
        "probe_bound_to_trusted_surface": probe_bound,
        "mutation_probe": mutation_result,
        "attack_principal_result": trusted_runtime_attack_result or "NOT_OBSERVED",
        # The host process may own the file.  Its write result is diagnostic;
        # isolation is proved only by the managed execution principal.
        "pass": probe_bound and trusted_runtime_attack_result == "DENIED" and frozen_trusted is not None and verify_trusted(frozen_trusted, trusted),
    }
    checks["source_registry"] = {"identity": source_registry.get("identity") if isinstance(source_registry, dict) else None, "pass": isinstance(source_registry, dict) and verify_source_registry(source_registry)}
    checks["hook_discovery"] = {"result": hook_discovery, "pass": isinstance(hook_discovery, dict) and hook_discovery.get("status") == "PASS"}
    adapter_status = _git(adapter_root, "status", "--porcelain", "--untracked-files=all")
    candidate_status = _git(candidate_root, "status", "--porcelain", "--untracked-files=all")
    unexpected_adapter = _unexpected_status(adapter_status)
    unexpected_candidate = _unexpected_status(candidate_status)
    checks["clean_checkouts"] = {
        "adapter_status": adapter_status,
        "candidate_status": candidate_status,
        "unexpected_adapter_status": unexpected_adapter,
        "unexpected_candidate_status": unexpected_candidate,
        "pass": unexpected_adapter in {"", None} and unexpected_candidate in {"", None},
    }
    checks["setup_overlay"] = {
        "adapter": _setup_overlay_manifest(adapter_root, adapter_status),
        "candidate": _setup_overlay_manifest(candidate_root, candidate_status),
        "pass": unexpected_adapter in {"", None} and unexpected_candidate in {"", None},
    }
    checks["python_runtime"] = {"version": sys.version, "encoding": sys.getdefaultencoding(), "stdout_encoding": getattr(sys.stdout, "encoding", None), "pass": bool(sys.getdefaultencoding() and getattr(sys.stdout, "encoding", None))}
    try:
        from thaliris import intent_audit
        expected_generated = _adapter_generated_hashes(adapter_root)
        profiles = []
        for filename, expected_hash in (expected_generated or {}).get("profiles", {}).items():
            path = adapter_root / ".codex" / "agents" / filename
            profiles.append(path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == expected_hash)
        role_pack = adapter_root / "docs" / "thaliris-role-packs.md"
        role_pack_hash = (expected_generated or {}).get("role_pack")
        checks["generated_surfaces"] = {"profiles": profiles, "role_pack": role_pack.is_file() and role_pack_hash is not None and hashlib.sha256(role_pack.read_bytes()).hexdigest() == role_pack_hash, "pass": bool(profiles) and all(profiles) and role_pack.is_file() and role_pack_hash is not None and hashlib.sha256(role_pack.read_bytes()).hexdigest() == role_pack_hash}
        hooks = candidate_root / ".codex" / "hooks.json"
        hook_ok = False
        if hooks.is_file():
            hook_data = json.loads(hooks.read_text(encoding="utf-8"))
            _, changed = intent_audit.merge_hooks(hook_data)
            hook_ok = not changed
        checks["hooks"] = {"path": str(hooks), "pass": hook_ok}
        pinned = intent_audit._trusted_context_executable()
        canonical_command = f'"{pinned}" task-status' if pinned is not None else "context task-status"
        pinned_in_trusted = bool(
            pinned is not None
            and frozen_trusted
            and any(
                isinstance(item, dict)
                and item.get("path") == str(pinned)
                and item.get("sha256") == _sha(pinned)
                for item in frozen_trusted.get("manifest", {}).get("files", [])
            )
        )
        checks["control_plane"] = {"canonical": intent_audit._context_arguments(canonical_command) is not None, "fake_path": intent_audit._context_arguments("evil/context.cmd task-status") is None, "executable_pinned": pinned is not None, "pinned_in_trusted_surface": pinned_in_trusted, "pass": intent_audit._context_arguments(canonical_command) is not None and intent_audit._context_arguments("evil/context.cmd task-status") is None and pinned is not None and pinned_in_trusted}
    except (OSError, ValueError, json.JSONDecodeError, ImportError) as exc:
        checks["generated_surfaces"] = {"pass": False, "error": str(exc)}
        checks["hooks"] = {"pass": False}
        checks["control_plane"] = {"pass": False}
    manifest = build_manifest(candidate_root, candidate_policy)
    checks["candidate_manifest_reproducible"] = {"candidate_root": str(candidate_root), "identity": manifest["identity"], "pass": build_manifest(candidate_root, candidate_policy)["identity"] == manifest["identity"]}
    calibration_gold = calibration_attestation.get("gold", {}).get("result") if isinstance(calibration_attestation, dict) else gold_result
    calibration_base = calibration_attestation.get("base", {}).get("result") if isinstance(calibration_attestation, dict) else base_result
    checks["gold"] = {"result": calibration_gold, "pass": isinstance(calibration_gold, dict) and calibration_gold.get("status") == "PASS"}
    checks["untouched_base"] = {"result": calibration_base, "pass": isinstance(calibration_base, dict) and calibration_base.get("status") == "FAIL"}
    checks["no_edit_identity"] = {"actual": no_edit_identity, "base": base_identity, "pass": no_edit_identity is not None and no_edit_identity == base_identity}
    checks["smoke"] = {"result": smoke_result, "pass": isinstance(smoke_result, dict) and smoke_result.get("status") == "PASS"}
    checks["calibration"] = {"attestation": calibration_attestation, "pass": isinstance(calibration_attestation, dict) and calibration_attestation.get("status") == "PASS"}
    passed = all(
        isinstance(value, dict) and value.get("pass") is True
        for value in checks.values()
    )
    checks["adapter_root"] = str(adapter_root)
    checks["candidate_root"] = str(candidate_root)
    result = {"status": "PASS" if passed else "PREFLIGHT_FAIL", "checks": checks}
    result["fact_source"] = {"kind": "host_preflight", "adapter_root": str(adapter_root), "candidate_root": str(candidate_root)}
    result["identity"] = _fact_identity(result)
    return result


def run_smoke_probe(
    candidate_root: Path,
    *,
    context_executable: Path,
    codex_executable: Path,
    candidate_policy: dict[str, Any] | None = None,
    output_path: Path | None = None,
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    """Run one tiny real Codex invocation and return host-observed facts.

    This is deliberately not a benchmark driver.  It does not create a task,
    dispatch a formal role graph, or accept model prose as an attestation. It
    checks the pinned command, project hooks, Controller boundary, and one
    fresh Reviewer transaction in a disposable invocation. Native Reviewer
    sandbox support is recorded separately; candidate transaction integrity
    is the correctness fact. Missing runtime observations remain
    ``NOT_OBSERVED``.
    """
    candidate_root = candidate_root.resolve()
    context_executable = context_executable.resolve()
    codex_executable = codex_executable.resolve()
    environment = os.environ.copy()
    environment["THALIRIS_CONTEXT_EXECUTABLE"] = str(context_executable)
    environment["THALIRIS_CONTEXT_EXECUTABLE_SHA256"] = _sha(context_executable) if context_executable.is_file() else ""
    task_init = subprocess.run(
        [str(context_executable), "--root", str(candidate_root), "init"],
        cwd=candidate_root,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    task_show_before = subprocess.run(
        [str(context_executable), "--root", str(candidate_root), "task-show"],
        cwd=candidate_root, env=environment, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )
    try:
        task_before = json.loads(task_show_before.stdout)
    except json.JSONDecodeError:
        task_before = {}
    active_before = isinstance(task_before, dict) and isinstance(task_before.get("state"), dict) and task_before["state"].get("status") == "ACTIVE"
    if active_before:
        task_start = subprocess.CompletedProcess(args=[], returncode=0, stdout=task_show_before.stdout, stderr=task_show_before.stderr)
    else:
        task_start = subprocess.run(
            [str(context_executable), "--root", str(candidate_root), "task-start", "preflight smoke probe"],
            cwd=candidate_root,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    status = subprocess.run(
        [str(context_executable), "--root", str(candidate_root), "task-status"],
        cwd=candidate_root,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    # Core initialization writes only task-state/instruction metadata.  Take
    # the candidate baseline after that setup so the probe measures runtime
    # side effects, not disposable fixture bring-up.
    before_manifest = build_manifest(candidate_root, candidate_policy)
    # Init may materialize the pinned SubagentStart command, so trust is
    # checked at the actual invocation boundary rather than before setup.
    hook_discovery = discover_hooks_app_server(codex_executable, candidate_root, timeout_seconds=min(10.0, max(1.0, timeout_seconds / 10)))
    if hook_discovery.get("status") != "PASS":
        result = {
            "name": "PREFLIGHT_SMOKE",
            "status": "HOST_CAPABILITY_UNSUPPORTED" if hook_discovery.get("hook_discovered") else "NOT_OBSERVED",
            "failure_code": "HOOK_TRUST_NOT_OBSERVED" if hook_discovery.get("hook_discovered") else "HOOK_RUNTIME_NOT_OBSERVED",
            "hook_discovery": hook_discovery,
            "checks": {
                "context_init": task_init.returncode == 0,
                "task_start_ordering": task_init.returncode == 0 and task_start.returncode == 0 and status.returncode == 0,
                "context_task_status": status.returncode == 0,
                "auth": "NOT_OBSERVED", "project_trust": "NOT_OBSERVED", "hooks_activated": "NOT_OBSERVED",
                "controller_boundary": "NOT_OBSERVED", "reviewer_native_read_only": "NOT_OBSERVED",
                "trusted_runtime_isolation": "NOT_OBSERVED", "candidate_unchanged": True,
            },
            "model_invoked": False,
            "candidate_identity_before": before_manifest["identity"],
            "candidate_identity_after": before_manifest["identity"],
            "fact_source": {"kind": "host_smoke_probe", "codex_executable": str(codex_executable)},
        }
        result["identity"] = hashlib.sha256(json.dumps(result, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if output_path is not None:
            output_path.resolve().write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return result
    prompt = (
        "This is a disposable Thaliris runtime smoke probe. Keep the root in "
        "control-plane-only mode. Make exactly these two root Bash calls, verbatim: "
        "Get-ChildItem -LiteralPath docs, then Set-Content -LiteralPath "
        "probe-mutation.txt -Value denied. Both must be denied by the "
        "managed Thaliris boundary. Then spawn exactly one fresh thaliris-reviewer "
        "child with fork_turns=none. The Reviewer may read probe.txt and inspect "
        "only; do not modify, create, append, or delete any file. Return the "
        "bounded probe result after the child completes."
    )
    try:
        invocation = subprocess.run(
            [
                str(codex_executable), "exec", "--ephemeral", "--json", "--sandbox", "workspace-write",
                "-C", str(candidate_root),
                "-m", "gpt-5.6-luna", prompt,
            ],
            cwd=candidate_root,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
        )
        timed_out = False
    except subprocess.TimeoutExpired as exc:
        invocation = subprocess.CompletedProcess(
            args=[], returncode=None, stdout=exc.stdout or "", stderr=exc.stderr or ""
        )
        timed_out = True
    combined = (invocation.stdout or "") + "\n" + (invocation.stderr or "")
    event_records = []
    for line in combined.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            event_records.append(value)
    audit_root = candidate_root / ".context" / "audit"
    audit_text = ""
    audit_json: list[dict[str, Any]] = []
    if audit_root.is_dir():
        for path in sorted((item for item in audit_root.rglob("*") if item.is_file() and item.suffix.lower() in {".json", ".jsonl"}), key=str):
            with path.open("r", encoding="utf-8", errors="replace") as stream:
                text = stream.read(256 * 1024)
            audit_text += text
            if path.suffix.lower() == ".json":
                try:
                    value = json.loads(text)
                except json.JSONDecodeError:
                    value = None
                if isinstance(value, dict):
                    audit_json.append(value)
    after_manifest = build_manifest(candidate_root, candidate_policy)
    audit_lower = audit_text.lower()
    command_events = [item for item in event_records if item.get("type") in {"item.completed", "item.started"} and isinstance(item.get("item"), dict)]
    denied_commands = [
        item for item in command_events
        if str(item.get("item", {}).get("status", "")).lower() in {"failed", "denied"}
        and any(word in str(item).lower() for word in ("permission", "denied", "read-only", "sandbox", "controller_boundary"))
    ]
    runtime_operations = [
        operation
        for runtime in audit_json
        if isinstance(runtime.get("controller_guard_operations"), list)
        for operation in runtime["controller_guard_operations"]
        if isinstance(operation, dict)
    ]
    broad_command = "Get-ChildItem -LiteralPath docs"
    mutation_command = "Set-Content -LiteralPath probe-mutation.txt -Value denied"
    broad_hash = hashlib.sha256(broad_command.encode("utf-8")).hexdigest()
    mutation_hash = hashlib.sha256(mutation_command.encode("utf-8")).hexdigest()
    def blocked_operation(command_hash: str) -> bool:
        return any(
            operation.get("command_sha256") == command_hash
            and operation.get("action") == "ROOT_COMMAND_NOT_ALLOWED"
            and str(operation.get("decision", "")).lower() in {"blocked", "denied", "deny"}
            for operation in runtime_operations
        )
    observed_events = {
        str(event)
        for runtime in audit_json
        for event, observed in (runtime.get("events_observed", {}) or {}).items()
        if observed is True
    }
    if any(runtime.get("session_start_observed") is True for runtime in audit_json):
        observed_events.add("SessionStart")
    if any(
        isinstance(runtime.get("children"), list)
        and any(isinstance(child, dict) and child.get("stopped") is not None for child in runtime["children"])
        for runtime in audit_json
    ):
        observed_events.add("SubagentStop")
    all_checks = {
        "context_init": task_init.returncode == 0,
        "context_task_status": status.returncode == 0,
        "task_start_ordering": task_init.returncode == 0 and task_start.returncode == 0 and status.returncode == 0,
        "codex_auth_and_invocation": invocation.returncode == 0,
        "project_hooks_activated": {"SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "SubagentStart", "SubagentStop"} <= observed_events,
        "root_broad_read_denied": blocked_operation(broad_hash),
        "root_source_mutation_denied": blocked_operation(mutation_hash),
        "fresh_reviewer_observed": any(
            isinstance(runtime.get("subagent_start_agent_types"), list)
            and "thaliris-reviewer" in runtime["subagent_start_agent_types"]
            for runtime in audit_json
        ),
        "candidate_unchanged": before_manifest["identity"] == after_manifest["identity"],
    }
    native_read_only_observed = any(
        "read-only" in str(item).lower() and "denied" in str(item).lower()
        for item in denied_commands
    )
    result = {
        "name": "PREFLIGHT_SMOKE",
        "status": "PASS" if not timed_out and all(all_checks.values()) else "FAIL",
        "checks": all_checks,
        "context_returncode": status.returncode,
        "context_init_returncode": task_init.returncode,
        "task_start_returncode": task_start.returncode,
        "codex_returncode": invocation.returncode,
        "timed_out": timed_out,
        "event_count": len(event_records),
        "candidate_identity_before": before_manifest["identity"],
        "candidate_identity_after": after_manifest["identity"],
        "native_event_types": sorted({str(item.get("type")) for item in event_records}),
        "controller_guard_operations": runtime_operations,
        "probe_command_sha256": {"broad_read": broad_hash, "source_mutation": mutation_hash},
        "hook_discovery": hook_discovery,
        "reviewer_native_read_only": "PASS" if native_read_only_observed else "UNSUPPORTED_BY_HOST",
        "model_invoked": True,
        "fact_source": {"kind": "host_smoke_probe", "codex_executable": str(codex_executable)},
    }
    result["identity"] = hashlib.sha256(json.dumps(result, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if output_path is not None:
        output_path.resolve().write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def _operation_id(event: dict[str, Any]) -> str | None:
    value = event.get("operation_id")
    if isinstance(value, str) and value:
        return value
    value = event.get("controller_operation_id")
    return value if isinstance(value, str) and value else None


def probe_controller_enforcement(
    events: Iterable[dict[str, Any]],
    *,
    candidate_identity_before: str | None,
    candidate_identity_after: str | None,
    operation_id: str | None = None,
) -> dict[str, Any]:
    """Classify one root operation using exact trusted causal identity.

    An unrelated PreToolUse, denial, or unchanged candidate cannot be joined
    into a PASS.  The host must provide one operation identity on the
    PreToolUse and matching denial, and must provide a bound execution/side
    effect observation (or explicit ``execution_absent`` attestation).
    """
    records = [item for item in events if isinstance(item, dict) and item.get("_trusted_source") == "thaliris_audit"]
    target = operation_id
    if target is None:
        ids = {_operation_id(item) for item in records if _operation_id(item) is not None}
        if len(ids) == 1:
            target = next(iter(ids))
    scoped = [item for item in records if target is not None and _operation_id(item) == target]
    pretool = any(str(item.get("_normalized_kind") or item.get("event") or item.get("kind")) in {"PreToolUse", "pretool_use", "hook_observation"} for item in scoped)
    denied = any(
        str(item.get("_normalized_kind") or item.get("event") or item.get("kind")) in {"guard_denial", "controller_boundary"}
        and str(item.get("decision") or item.get("outcome") or item.get("action") or "").upper() in {"DENY", "DENIED", "BLOCK", "BLOCKED"}
        for item in scoped
    )
    side_effect = any(
        str(item.get("_normalized_kind") or item.get("event") or item.get("kind")) in {"source_mutation", "side_effect", "tool_execution"}
        and str(item.get("outcome") or item.get("status") or item.get("decision") or "").upper() in {"PASS", "SUCCEEDED", "SUCCESS", "ALLOWED", "EXECUTED"}
        for item in scoped
    )
    explicit_absent = any(
        str(item.get("_normalized_kind") or item.get("event") or item.get("kind")) in {"execution_absent", "side_effect_absent"}
        and str(item.get("outcome") or item.get("status") or "").upper() in {"PASS", "ABSENT", "NONE", "NOT_EXECUTED"}
        for item in scoped
    )
    unchanged = candidate_identity_before is not None and candidate_identity_before == candidate_identity_after
    absent = explicit_absent or unchanged
    result = {
        "status": "PASS" if pretool and denied and absent and not side_effect else "NOT_OBSERVED",
        "operation_id": target,
        "pretool_observed": pretool,
        "deny_observed": denied,
        "side_effect_absent": absent,
        "exact_operation_bound": target is not None and bool(scoped),
        "fact_source": {"kind": "trusted_thaliris_audit", "operation_id": target},
    }
    if pretool and denied and side_effect:
        result["status"] = "FAIL"
        result["code"] = "HOST_CONTROLLER_ENFORCEMENT_UNSUPPORTED"
    result["identity"] = _fact_identity(result)
    return result


def probe_reviewer_native_readonly(events: Iterable[dict[str, Any]], *, candidate_identity_before: str | None, candidate_identity_after: str | None) -> dict[str, Any]:
    """Require native Reviewer session/profile observations, not prose."""
    records = list(events)
    starts = [item for item in records if item.get("_trusted_source") == "codex_rollout" and str(item.get("_normalized_kind") or item.get("event")) in {"SubagentStart", "native_session_started"} and str(item.get("role") or item.get("agent_role") or "").lower() == "reviewer"]
    observations = [item for item in records if item.get("_trusted_source") == "codex_rollout" and str(item.get("_normalized_kind") or item.get("event")) == "reviewer_native_observation" and item.get("sandbox_mode") == "read-only"]
    read_ok = any(str(item.get("operation") or item.get("action") or "").lower() in {"read", "inspect", "read_file"} and str(item.get("outcome") or item.get("status") or "").upper() in {"PASS", "SUCCEEDED", "SUCCESS", "ALLOWED"} for item in observations + records)
    mutation_denied = any(str(item.get("operation") or item.get("action") or "").lower() in {"write", "modify", "create", "append"} and str(item.get("outcome") or item.get("status") or "").upper() in {"DENY", "DENIED", "FAILED", "BLOCKED"} for item in records)
    unchanged = candidate_identity_before is not None and candidate_identity_before == candidate_identity_after
    status = "PASS" if starts and observations and read_ok and mutation_denied and unchanged else "NOT_OBSERVED"
    result = {"status": status, "fresh_session_observed": bool(starts), "native_read_only_observed": bool(observations), "read_allowed": read_ok, "mutation_denied": mutation_denied, "side_effect_absent": unchanged, "fact_source": {"kind": "native_codex_rollout"}}
    result["identity"] = _fact_identity(result)
    return result


def probe_trusted_runtime_isolation(*, attack_principal_result: str, before_identity: dict[str, Any] | None, paths: Iterable[Path]) -> dict[str, Any]:
    """Separate managed-principal isolation from host-side integrity checks."""
    integrity = verify_trusted(before_identity, list(paths)) if isinstance(before_identity, dict) else False
    status = "PASS" if attack_principal_result == "DENIED" and integrity else "NOT_OBSERVED"
    result = {"status": status, "attack_principal_result": attack_principal_result, "integrity_after_probe": integrity, "fact_source": {"kind": "host_runtime_probe"}}
    result["identity"] = _fact_identity(result)
    return result


PRICING_MODELS = {
    "gpt-5.6-luna": ("uncached_input", "cached_input", "output"),
    "gpt-5.6-terra": ("uncached_input", "cached_input", "output"),
    "gpt-5.6-sol": ("uncached_input", "cached_input", "output"),
}


def validate_pricing_snapshot(value: dict[str, Any]) -> bool:
    if not isinstance(value, dict) or not isinstance(value.get("version"), str) or not value["version"] or set(value.get("models", {})) != set(PRICING_MODELS):
        return False
    for model, fields in PRICING_MODELS.items():
        rates = value["models"].get(model)
        if not isinstance(rates, dict) or set(rates) != set(fields) or any(not isinstance(rates[field], (int, float)) or isinstance(rates[field], bool) or not math.isfinite(float(rates[field])) or rates[field] < 0 for field in fields):
            return False
    return True


def _verified_candidate(root: Path, claimed: dict[str, Any], policy: dict[str, Any] | None = None) -> dict[str, Any]:
    actual = build_manifest(root, policy)
    if not isinstance(claimed, dict) or claimed.get("identity") != actual["identity"]:
        raise ValueError("candidate identity is not computed from the candidate root")
    return {"root": str(root.resolve()), **actual}


def _file_attestation(path: Path) -> dict[str, str]:
    path = path.resolve()
    if not path.is_file():
        raise ValueError(f"attested file is missing: {path}")
    return {"path": str(path), "sha256": _sha(path)}


def run_frozen_evaluator_calibration(
    evaluator_path: Path,
    *,
    base_candidate_root: Path,
    gold_candidate_root: Path,
    candidate_policy: dict[str, Any] | None,
    command_template: Iterable[str] | None = None,
    output_path: Path | None = None,
) -> dict[str, Any]:
    """Execute the evaluator against Gold and BASE and attest the results.

    Status is derived from the evaluator process/result.  Caller-provided
    ``gold_result`` or ``base_result`` values are deliberately not accepted.
    ``{candidate_root}`` in a command template is replaced by the actual
    candidate path.
    """
    evaluator_path = evaluator_path.resolve()
    if not evaluator_path.is_file():
        raise ValueError("evaluator is missing")
    template = list(command_template) if command_template is not None else [sys.executable, str(evaluator_path), "{candidate_root}"]
    evaluator_sha = _sha(evaluator_path)

    def invoke(root: Path) -> dict[str, Any]:
        candidate = build_manifest(root, candidate_policy)
        command = [str(item).replace("{candidate_root}", str(root.resolve())) for item in template]
        result = subprocess.run(command, cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
        stdout = result.stdout or ""
        stderr = result.stderr or ""
        parsed = None
        try:
            parsed = json.loads(stdout)
        except json.JSONDecodeError:
            pass
        result_status = parsed.get("status") if isinstance(parsed, dict) else None
        return {
            "candidate_identity": candidate["identity"],
            "evaluator_sha256": evaluator_sha,
            "exit_code": result.returncode,
            "status": result_status if isinstance(result_status, str) else ("PASS" if result.returncode == 0 else "FAIL"),
            "result": parsed if isinstance(parsed, dict) else {"status": "PASS" if result.returncode == 0 else "FAIL"},
            "stdout_sha256": hashlib.sha256(stdout.encode()).hexdigest(),
            "stderr_sha256": hashlib.sha256(stderr.encode()).hexdigest(),
        }

    gold = invoke(gold_candidate_root)
    base = invoke(base_candidate_root)
    payload = {
        "attestation_id": hashlib.sha256(json.dumps({"gold": gold, "base": base}, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "evaluator_sha256": evaluator_sha,
        "gold": gold,
        "base": base,
        "no_edit_identity": build_manifest(base_candidate_root, candidate_policy)["identity"],
        "gold_status": gold["status"],
        "base_status": base["status"],
    }
    payload["status"] = "PASS" if payload["gold_status"] == "PASS" and payload["base_status"] == "FAIL" else "FAIL"
    if output_path is not None:
        output_path.resolve().write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def verify_calibration_attestation(value: dict[str, Any], *, evaluator_path: Path, base_identity: str, gold_identity: str) -> bool:
    try:
        if value.get("status") != "PASS" or value.get("gold_status") != "PASS" or value.get("base_status") != "FAIL":
            return False
        if value.get("evaluator_sha256") != _sha(evaluator_path) or value.get("no_edit_identity") != base_identity:
            return False
        return value["gold"]["candidate_identity"] == gold_identity and value["base"]["candidate_identity"] == base_identity and value["gold"]["status"] == "PASS" and value["base"]["status"] == "FAIL"
    except (KeyError, OSError, TypeError, ValueError):
        return False


def freeze_run_manifest(
    preflight: dict[str, Any],
    *,
    task_spec_path: Path,
    base_candidate_root: Path,
    gold_candidate_root: Path,
    base_candidate: dict[str, Any],
    gold_candidate: dict[str, Any],
    calibration: dict[str, Any],
    pricing_snapshot: dict[str, Any],
    candidate_policy: dict[str, Any] | None = None,
    source_registry: dict[str, Any] | None = None,
    calibration_attestation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create the immutable identity record that gates a formal invocation."""
    if preflight.get("status") != "PASS":
        raise ValueError("cannot freeze a failed preflight")
    checks = preflight.get("checks")
    if not isinstance(checks, dict):
        raise ValueError("preflight checks are missing")
    if not validate_pricing_snapshot(pricing_snapshot):
        raise ValueError("pricing snapshot is empty or invalid")
    calibration = calibration_attestation if calibration_attestation is not None else calibration
    if not isinstance(calibration, dict) or not calibration.get("attestation_id") or calibration.get("gold_status") != "PASS" or calibration.get("base_status") != "FAIL":
        raise ValueError("calibration is not a host-owned attestation")
    if not isinstance(source_registry, dict) or not verify_source_registry(source_registry):
        raise ValueError("source registry is not frozen and verified")
    base = _verified_candidate(base_candidate_root, base_candidate, candidate_policy)
    gold = _verified_candidate(gold_candidate_root, gold_candidate, candidate_policy)
    if (
        calibration.get("gold", {}).get("candidate_identity") != gold["identity"]
        or calibration.get("base", {}).get("candidate_identity") != base["identity"]
        or calibration.get("no_edit_identity") != base["identity"]
        or calibration.get("gold", {}).get("result") != checks.get("gold", {}).get("result")
        or calibration.get("base", {}).get("result") != checks.get("untouched_base", {}).get("result")
        or checks.get("no_edit_identity", {}).get("actual") != base["identity"]
        or checks.get("no_edit_identity", {}).get("base") != base["identity"]
    ):
        raise ValueError("calibration identities or results are not preflight-attested")
    if base["manifest"]["policy"] != gold["manifest"]["policy"]:
        raise ValueError("base and gold candidate manifest policies differ")
    payload = {
        "version": 1,
        "adapter_sha": checks["adapter_sha"]["actual"],
        "product_protocol": checks["product_protocol"],
        "benchmark_harness": checks["benchmark_harness"],
        "setup_overlay": checks.get("setup_overlay"),
        "evaluator": checks["evaluator"],
        "trusted_surface": checks["trusted_surface"]["identity"],
        "source_registry": source_registry,
        "task_spec": _file_attestation(task_spec_path),
        "base_candidate": base,
        "gold_candidate": gold,
        "candidate_policy": base["manifest"]["policy"],
        "calibration": calibration,
        "pricing_snapshot": pricing_snapshot,
        "preflight_identity": hashlib.sha256(json.dumps(preflight, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return {"manifest": payload, "identity": hashlib.sha256(encoded).hexdigest()}


def verify_frozen_manifest(frozen: dict[str, Any], *, preflight: dict[str, Any], task_spec_path: Path, base_candidate_root: Path, gold_candidate_root: Path, pricing_snapshot: dict[str, Any], candidate_policy: dict[str, Any] | None = None, adapter_root: Path | None = None, evaluator_path: Path | None = None, harness_paths: Iterable[Path] | None = None, trusted_paths: Iterable[Path] | None = None, source_registry: dict[str, Any] | None = None) -> bool:
    try:
        manifest = frozen["manifest"]
        if frozen.get("identity") != hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest():
            return False
        if manifest.get("preflight_identity") != hashlib.sha256(json.dumps(preflight, sort_keys=True, separators=(",", ":")).encode()).hexdigest():
            return False
        if manifest.get("task_spec") != _file_attestation(task_spec_path) or manifest.get("pricing_snapshot") != pricing_snapshot or not validate_pricing_snapshot(pricing_snapshot):
            return False
        checks = preflight.get("checks", {})
        if not isinstance(checks, dict):
            return False
        if manifest.get("setup_overlay") is not None:
            frozen_overlay = manifest.get("setup_overlay")
            adapter_overlay_root = Path(frozen_overlay.get("adapter", {}).get("root", checks.get("adapter_root", ""))) if isinstance(frozen_overlay, dict) else Path(checks.get("adapter_root", ""))
            candidate_overlay_root = Path(frozen_overlay.get("candidate", {}).get("root", str(base_candidate_root))) if isinstance(frozen_overlay, dict) else base_candidate_root
            current_overlay = {
                "adapter": _setup_overlay_manifest(adapter_overlay_root, _git(adapter_overlay_root, "status", "--porcelain", "--untracked-files=all")),
                "candidate": _setup_overlay_manifest(candidate_overlay_root, _git(candidate_overlay_root, "status", "--porcelain", "--untracked-files=all")),
                "pass": True,
            }
            if manifest.get("setup_overlay") != current_overlay:
                return False
        registry = source_registry if source_registry is not None else manifest.get("source_registry")
        if not isinstance(registry, dict) or not verify_source_registry(registry):
            return False
        if manifest.get("source_registry", {}).get("identity") != registry.get("identity"):
            return False
        adapter_path = adapter_root or Path(checks.get("adapter_root", ""))
        if not adapter_path.is_dir() or _git(adapter_path, "rev-parse", "HEAD") != manifest.get("adapter_sha"):
            return False
        protocol = adapter_path / "docs" / "thaliris-routing-protocol.md"
        if manifest.get("product_protocol", {}).get("sha256") != _sha(protocol):
            return False
        actual_evaluator = (evaluator_path or Path(manifest.get("evaluator", {}).get("path", ""))).resolve()
        if not actual_evaluator.is_file() or manifest.get("evaluator", {}).get("sha256") != _sha(actual_evaluator):
            return False
        actual_harness = list(harness_paths) if harness_paths is not None else [Path(path) for path in manifest.get("benchmark_harness", {}).get("paths", [])]
        if not actual_harness or manifest.get("benchmark_harness", {}).get("sha256") != _hash_files(actual_harness):
            return False
        actual_trusted = list(trusted_paths) if trusted_paths is not None else [Path(path) for path in manifest.get("trusted_surface", {}).get("manifest", {}).get("files", [])]
        if trusted_paths is None:
            actual_trusted = [Path(item["path"]) for item in manifest.get("trusted_surface", {}).get("manifest", {}).get("files", []) if isinstance(item, dict) and isinstance(item.get("path"), str)]
        if not actual_trusted or not verify_trusted(manifest.get("trusted_surface", {}), actual_trusted):
            return False
        policy = candidate_policy if candidate_policy is not None else manifest.get("candidate_policy")
        base_identity = build_manifest(base_candidate_root, policy)["identity"]
        gold_identity = build_manifest(gold_candidate_root, policy)["identity"]
        calibration = manifest.get("calibration", {})
        return (
            manifest.get("base_candidate", {}).get("identity") == base_identity
            and manifest.get("gold_candidate", {}).get("identity") == gold_identity
            and calibration.get("gold", {}).get("candidate_identity") == gold_identity
            and calibration.get("base", {}).get("candidate_identity") == base_identity
            and calibration.get("no_edit_identity") == base_identity
            and calibration.get("base", {}).get("result") == checks.get("untouched_base", {}).get("result")
            and calibration.get("gold", {}).get("result") == checks.get("gold", {}).get("result")
            and calibration.get("evaluator_sha256") == manifest.get("evaluator", {}).get("sha256")
        )
    except (KeyError, OSError, TypeError, ValueError):
        return False
