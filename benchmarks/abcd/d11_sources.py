"""Frozen, source-specific input boundary for formal benchmark collection."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable

SOURCE_KINDS = frozenset({"thaliris_audit", "codex_rollout", "harness_attestation", "evaluator_result"})
SOURCE_REGISTRY_VERSION = 1

# These are intentionally event names, not arbitrary JSON keys.  A source
# cannot acquire another producer's authority by adding a ``trusted`` flag.
SOURCE_EVENTS = {
    "thaliris_audit": frozenset({
        "hook_observation", "guard_denial", "controller_boundary", "child_lifecycle",
        "artifact_produced", "artifact_written", "artifact_registered", "artifact_selected",
        "handoff", "role_dispatch", "implementer_dispatch", "source_mutation",
        "source_snapshot_attestation",
        "SubagentStart", "SubagentStop", "native_session_started", "task_start", "task_status",
    }),
    "codex_rollout": frozenset({
        "session_meta", "token_usage_record", "session_usage", "rollout_session", "model_usage",
        "SubagentStart", "SubagentStop", "native_session_started", "reviewer_native_observation",
        "review_verdict", "tool_observation", "native_status", "native_interruption",
    }),
    "harness_attestation": frozenset({
        "candidate_attestation", "invocation_attestation", "verification_attestation",
        "evaluator_attestation", "seal_attestation", "deterministic_verification", "verification",
    }),
    "evaluator_result": frozenset({"evaluator_result", "evaluator_calibration_attestation"}),
}


def validate_event_shape(source_kind: str, event_type: str, value: dict[str, Any]) -> bool:
    """Apply the small source-specific schema needed by the collector."""
    required = {
        "candidate_attestation": {"stage", "candidate_root", "candidate_identity", "manifest_version", "harness_identity"},
        "reviewer_native_observation": {"session_id", "native_session_id", "sandbox_mode"},
        "source_snapshot_attestation": {"observation_id", "path", "content_sha256", "session_id"},
        "evaluator_result": {"evaluator_sha256", "candidate_identity", "exit_code"},
        "evaluator_calibration_attestation": {"attestation_id", "evaluator_sha256", "gold", "base"},
    }.get(event_type, set())
    if required and not required <= set(value):
        return False
    if event_type == "reviewer_native_observation" and value.get("sandbox_mode") not in {"read-only", "workspace-write", "danger-full-access"}:
        return False
    if event_type == "source_snapshot_attestation":
        path = value.get("path")
        if not isinstance(path, str) or not path or "\\" in path or path.startswith("/") or ".." in path.split("/"):
            return False
        if not isinstance(value.get("observation_id"), str) or not value["observation_id"]:
            return False
        if not isinstance(value.get("content_sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", value["content_sha256"]):
            return False
        if not isinstance(value.get("session_id"), str) or not value["session_id"]:
            return False
    if event_type == "candidate_attestation":
        # Candidate stage identity is the only authority this source owns.
        # Native session/sandbox/verdict/usage claims belong to other streams.
        if any(key in value for key in ("sandbox_mode", "verdict", "usage", "token_usage", "native_event_id")):
            return False
        if value.get("stage") not in {"runtime-final", "review-start", "review-end", "verification-start", "evaluator-start", "seal"}:
            return False
        if not isinstance(value.get("candidate_identity"), str) or not re.fullmatch(r"[0-9a-f]{64}", value["candidate_identity"]):
            return False
        if not isinstance(value.get("manifest_version"), int) or value["manifest_version"] < 1:
            return False
    if event_type == "evaluator_result" and any(key in value for key in ("verdict", "sandbox_mode", "session_id", "token_usage")):
        return False
    if source_kind == "evaluator_result" and not isinstance(value.get("exit_code"), int):
        return False
    return True


def chain_payload(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if key not in {"sequence", "previous_hash", "payload_hash", "record_hash"}}


def hash_chain_record(value: dict[str, Any]) -> str:
    payload = chain_payload(value)
    return hashlib.sha256(json.dumps({"run_id": value.get("run_id"), "sequence": value.get("sequence"), "previous_hash": value.get("previous_hash"), "payload_hash": value.get("payload_hash"), "payload": payload}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _identity(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def create_source_registry(sources: Iterable[dict[str, Any]], *, run_id: str, test_only: bool = False) -> dict[str, Any]:
    """Create a registry from actual source files and their current bytes."""
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("source registry requires a run_id")
    entries: list[dict[str, Any]] = []
    for source in sources:
        if not isinstance(source, dict):
            raise ValueError("source registry entry is not an object")
        kind = source.get("source_kind", source.get("kind"))
        path = Path(source.get("canonical_path", source.get("path", ""))).resolve()
        if kind not in SOURCE_KINDS or not path.is_file():
            raise ValueError("source registry entry is invalid")
        allowed = source.get("allowed_event_types", sorted(SOURCE_EVENTS[kind]))
        allowed_base = set().union(*SOURCE_EVENTS.values()) if test_only else SOURCE_EVENTS[kind]
        if not isinstance(allowed, list) or not allowed or not set(allowed) <= allowed_base:
            raise ValueError("source registry allowlist is invalid")
        source_id = source.get("source_id") or f"{kind}:{_sha(path)}"
        if not isinstance(source_id, str) or not source_id:
            raise ValueError("source registry source_id is invalid")
        entries.append({
            "source_id": source_id,
            "source_kind": kind,
            "canonical_path": str(path),
            "producer": source.get("producer", kind),
            "allowed_event_types": sorted(set(allowed)),
            "content_sha256": _sha(path),
            "stream_identity_policy": source.get("stream_identity_policy", "exact_bytes"),
            "initial_size": path.stat().st_size,
            "run_id": run_id,
        })
    payload = {"version": SOURCE_REGISTRY_VERSION, "run_id": run_id, "test_only": bool(test_only), "sources": sorted(entries, key=lambda x: x["source_id"])}
    return {"registry": payload, "identity": _identity(payload)}


def verify_source_registry(registry: dict[str, Any], *, run_id: str | None = None) -> bool:
    try:
        payload = registry["registry"]
        if payload["version"] != SOURCE_REGISTRY_VERSION or (run_id is not None and payload["run_id"] != run_id):
            return False
        sources = payload["sources"]
        if not isinstance(sources, list) or not sources:
            return False
        if registry.get("identity") != _identity(payload):
            return False
        seen: set[str] = set()
        allowed_base = set().union(*SOURCE_EVENTS.values()) if payload.get("test_only") else None
        for item in sources:
            path = Path(item["canonical_path"])
            if item["source_id"] in seen or item["source_kind"] not in SOURCE_KINDS or not path.is_file():
                return False
            policy = item.get("stream_identity_policy", "exact_bytes")
            if policy not in {"exact_bytes", "append_only"} or policy == "exact_bytes" and _sha(path) != item["content_sha256"] or policy == "append_only" and (path.stat().st_size < int(item.get("initial_size", 0)) or _sha_prefix(path, int(item.get("initial_size", 0))) != item["content_sha256"]):
                return False
            if not set(item["allowed_event_types"]) <= (allowed_base if allowed_base is not None else SOURCE_EVENTS[item["source_kind"]]):
                return False
            seen.add(item["source_id"])
        return True
    except (KeyError, OSError, TypeError, ValueError):
        return False


def registry_sources(registry: dict[str, Any]) -> list[dict[str, Any]]:
    if not verify_source_registry(registry):
        raise ValueError("source registry is not a current, byte-verified registry")
    return list(registry["registry"]["sources"])


def _sha_prefix(path: Path, length: int) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        remaining = length
        while remaining:
            chunk = stream.read(min(1024 * 1024, remaining))
            if not chunk:
                break
            digest.update(chunk)
            remaining -= len(chunk)
    return digest.hexdigest()
