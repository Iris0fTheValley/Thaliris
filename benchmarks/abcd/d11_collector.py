"""Fact collector for the benchmark gates.

The collector is intentionally separate from :mod:`d11_protocol`: it reads
Core state, bytes, and native event records and emits a small ledger.  No
model-authored report field is trusted for ordering, freshness, or identity.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from candidate_manifest import build_manifest


def load_jsonl(paths: Iterable[Path]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in paths:
        with path.open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, 1):
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    records.append({"_file": str(path), "_line": line_number, **value})
    return records


def _kind(event: dict[str, Any]) -> str:
    return str(event.get("event") or event.get("kind") or event.get("type") or "")


def _order(event: dict[str, Any], fallback: int) -> tuple[int, int]:
    for key in ("sequence", "seq", "order"):
        if isinstance(event.get(key), int):
            return (event[key], fallback)
    return (fallback, fallback)


def _state(root: Path) -> dict[str, Any]:
    value = json.loads((root / ".context" / "state.json").read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Core state is not an object")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect_evidence(root: Path, events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Derive the reusable-evidence lifecycle from state, bytes, and events."""
    state = _state(root)
    ordered = sorted(list(events), key=lambda item: _order(item, item.get("_line", 0)))
    artifacts = []
    for ref in state.get("artifact_refs", []):
        if not isinstance(ref, dict):
            continue
        path = root.joinpath(*str(ref.get("path", "")).split("/"))
        actual_sha = _sha256(path) if path.is_file() and not path.is_symlink() else None
        artifact_id = ref.get("id")
        produced = next((e for e in ordered if _kind(e) in {"artifact_produced", "artifact_written"} and e.get("artifact_id") == artifact_id), None)
        registered = next((e for e in ordered if _kind(e) == "artifact_registered" and e.get("artifact_id") == artifact_id), None)
        selections = [e for e in ordered if _kind(e) in {"artifact_selected", "handoff", "role_dispatch"} and artifact_id in e.get("artifact_ids", [])]
        consumers = [e for e in selections if e.get("role") not in {None, "controller"} or e.get("consumer_role")]
        carried = [e for e in selections if e.get("content_sha256") == ref.get("content_sha256") or any(isinstance(item, dict) and item.get("content_sha256") == ref.get("content_sha256") for item in e.get("artifacts", []))]
        artifact = {
            "id": artifact_id,
            "task_id": state.get("task_id"),
            "revision": ref.get("revision", state.get("revision")),
            "producer_role": ref.get("producer_role"),
            "path": ref.get("path"),
            "registered_by": ref.get("registered_by"),
            "declared_sha256": ref.get("content_sha256"),
            "actual_sha256": actual_sha,
            "produced_order": _order(produced, -1)[0] if produced else None,
            "registered_order": _order(registered, -1)[0] if registered else None,
            "dispatch_orders": [_order(item, -1)[0] for item in selections],
            "consumer_roles": sorted({str(item.get("consumer_role") or item.get("role")) for item in consumers}),
            "carried_content_identity": bool(carried),
            "supersedes": list(ref.get("supersedes", [])),
        }
        artifact["bytes_match"] = actual_sha == ref.get("content_sha256")
        artifact["registered_before_dispatch"] = bool(registered and selections and _order(registered, -1) < min(_order(item, -1) for item in selections))
        artifact["produced_before_registration"] = bool(produced and registered and _order(produced, -1) < _order(registered, -1))
        artifact["used"] = bool(consumers and carried)
        artifacts.append(artifact)
    return {"evidence_required": "REQUIRED" if artifacts else "NOT_REQUIRED", "artifacts": artifacts}


def collect_candidate(root: Path) -> dict[str, Any]:
    """Collect candidate identity from the actual product surface."""
    return build_manifest(root)


def collect_review_graph(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Collect reviewer edges from native session and review events.

    A caller must provide native session identity and sandbox observation.  The
    collector never treats a prose ``fresh`` flag as proof of either property.
    """
    ordered = sorted(list(events), key=lambda item: _order(item, item.get("_line", 0)))
    sessions: set[str] = set()
    graph: list[dict[str, Any]] = []
    for event in ordered:
        if _kind(event) in {"native_session_started", "SubagentStart"} and event.get("role") == "reviewer" and isinstance(event.get("session_id"), str):
            sessions.add(event["session_id"])
        if _kind(event) != "review_verdict":
            continue
        session = event.get("session_id")
        candidate = event.get("candidate_identity")
        if not isinstance(session, str) or not isinstance(candidate, str):
            continue
        graph.append({
            "reviewer_session": session,
            "input_candidate_identity": candidate,
            "verdict": event.get("verdict"),
            "finding_id": event.get("finding_id"),
            "classification": event.get("classification"),
            "native_session": session in sessions,
            "sandbox_mode": event.get("native_sandbox_mode"),
            "order": _order(event, -1)[0],
        })
    return {"review_rounds": graph, "native_reviewer_sessions": sorted(sessions)}
