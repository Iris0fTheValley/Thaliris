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

from candidate_manifest import MANIFEST_VERSION, build_manifest


TRUSTED_SOURCE_KINDS = frozenset({"thaliris_audit", "codex_rollout", "harness_attestation", "evaluator_result"})


def load_trusted_events(sources: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize only explicitly classified host/harness streams.

    A random JSON path or an unclassified dict is not an event source.  The
    original source, line, native identity, and ingestion order are retained
    for later audit; raw sequence fields are never used as global time.
    """
    records: list[dict[str, Any]] = []
    for source in sources:
        if not isinstance(source, dict) or set(source) != {"kind", "path"} or source.get("kind") not in TRUSTED_SOURCE_KINDS:
            raise ValueError("event source is not an approved host-owned stream")
        path = Path(source["path"]).resolve()
        if not path.is_file():
            raise ValueError(f"trusted event source is missing: {path}")
        source_sha256 = _sha256(path)
        session_identity = None
        role_identity = None
        model_identity = None
        with path.open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, 1):
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(raw, dict):
                    continue
                payload = raw.get("payload") if isinstance(raw.get("payload"), dict) else {}
                if raw.get("type") == "session_meta":
                    session_identity = payload.get("id") or payload.get("session_id")
                    role_identity = payload.get("agent_role")
                    provenance = payload.get("base_instructions", {}).get("provenance", {}) if isinstance(payload.get("base_instructions"), dict) else {}
                    model_identity = provenance.get("model") or payload.get("model")
                native_id = raw.get("native_event_id") or raw.get("event_id") or f"{source['kind']}:{path}:{line_number}"
                records.append({
                    **raw,
                    "_trusted_source": source["kind"],
                    "_source_file": str(path),
                    "_source_sha256": source_sha256,
                    "_source_line": line_number,
                    "_native_event_id": str(native_id),
                    "_ingestion_index": len(records),
                    "_normalized_kind": str(raw.get("event") or raw.get("kind") or raw.get("type") or ""),
                    "_session_identity": str(session_identity) if session_identity else None,
                    "_role_identity": str(role_identity) if role_identity else None,
                    "_model_identity": str(model_identity) if model_identity else None,
                })
    return records


def _require_trusted(events: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    records = list(events)
    if any(not isinstance(event, dict) or event.get("_trusted_source") not in TRUSTED_SOURCE_KINDS for event in records):
        raise ValueError("collector accepts only normalized trusted events")
    return records


def load_jsonl(paths: Iterable[Path]) -> list[dict[str, Any]]:
    return load_trusted_events([{"kind": "codex_rollout", "path": path} for path in paths])


def _kind(event: dict[str, Any]) -> str:
    return str(event.get("_normalized_kind") or "")


def _order(event: dict[str, Any], fallback: int) -> tuple[int, int]:
    return (int(event.get("_ingestion_index", fallback)), 0)


def _provenance(event: dict[str, Any] | None) -> dict[str, Any] | None:
    if event is None:
        return None
    return {
        "source": event.get("_trusted_source"),
        "source_file": event.get("_source_file"),
        "source_sha256": event.get("_source_sha256"),
        "source_line": event.get("_source_line"),
        "native_event_id": event.get("_native_event_id"),
        "order": _order(event, -1)[0],
    }


def _before(left: dict[str, Any], right: dict[str, Any]) -> bool:
    """Compare only one source stream or an explicit causal edge."""
    if left.get("_source_file") == right.get("_source_file"):
        return _order(left, -1) < _order(right, -1)
    caused_by = right.get("caused_by")
    causes = right.get("causes", [])
    if left.get("_native_event_id") == caused_by:
        return True
    return isinstance(causes, list) and left.get("_native_event_id") in causes


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


def _artifact_envelope(data: bytes, *, artifact_id: str, task_id: str, task_revision: int) -> tuple[dict[str, Any] | None, str | None]:
    if len(data) > 32 * 1024:
        return None, "artifact exceeds bounded envelope size"
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, "artifact is not a structured UTF-8 JSON envelope"
    required = {"artifact_id", "task_id", "task_revision", "source_refs", "affected_surface", "confirmed_facts", "inferences", "unknowns", "contradictions", "verification"}
    if not isinstance(value, dict) or set(value) != required:
        return None, "artifact envelope fields are incomplete or unbounded"
    if value["artifact_id"] != artifact_id or value["task_id"] != task_id or value["task_revision"] != task_revision:
        return None, "artifact envelope identity does not match Core pointer"
    if not isinstance(value["artifact_id"], str) or not value["artifact_id"] or not isinstance(value["task_id"], str) or not value["task_id"] or not isinstance(value["task_revision"], int) or value["task_revision"] < 0:
        return None, "artifact envelope provenance is malformed"
    if any(not isinstance(value[key], list) or len(value[key]) > 32 for key in required - {"artifact_id", "task_id", "task_revision"}):
        return None, "artifact envelope lists are not bounded"
    if not all(isinstance(item, str) and item.strip() for item in value["affected_surface"]):
        return None, "artifact affected_surface is malformed"
    source_refs = value["source_refs"]
    if not all(isinstance(item, str) and item for item in source_refs):
        return None, "artifact source_refs are malformed"
    source_set = set(source_refs)
    for field in ("confirmed_facts", "inferences", "unknowns", "contradictions"):
        for item in value[field]:
            if not isinstance(item, dict) or set(item) != {"text", "source_refs"} or not isinstance(item["text"], str) or not item["text"].strip() or not isinstance(item["source_refs"], list) or not set(item["source_refs"]) <= source_set:
                return None, f"artifact {field} contains malformed statements"
            if field == "confirmed_facts" and not item["source_refs"]:
                return None, "confirmed facts require supporting source refs"
    for item in value["verification"]:
        if not isinstance(item, dict) or set(item) != {"description", "source_refs"} or not isinstance(item["description"], str) or not item["description"].strip() or not isinstance(item["source_refs"], list) or not set(item["source_refs"]) <= source_set:
            return None, "artifact verification is malformed"
    return value, None


def collect_evidence(root: Path, events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Derive the reusable-evidence lifecycle from state, bytes, and events."""
    state = _state(root)
    ordered = sorted(_require_trusted(events), key=lambda item: _order(item, -1))
    roles = {str(event.get("role") or event.get("consumer_role")) for event in ordered if event.get("role") or event.get("consumer_role")}
    downstream_roles = {"controller", "reasoning-specialist", "implementer", "reviewer", "terra", "sol"}
    producer_roles = {
        str(ref.get("producer_role"))
        for ref in state.get("artifact_refs", [])
        if isinstance(ref, dict) and ref.get("producer_role")
    }
    # A Core-registered Investigator/Curator artifact is itself evidence that
    # the route crossed a reusable-evidence boundary.  This is derived from
    # the producer role in Core state, not from the presence of a file, so a
    # missing registration cannot silently turn the requirement off.
    evidence_required = bool({"investigator", "curator"} & producer_roles) or bool(
        ({"investigator", "curator"} & roles)
        and (roles & downstream_roles - {"investigator", "curator"})
    )
    artifacts = []
    superseded_ids = {target for ref in state.get("artifact_refs", []) if isinstance(ref, dict) for target in ref.get("supersedes", [])}
    for ref in state.get("artifact_refs", []):
        if not isinstance(ref, dict):
            continue
        path = root.joinpath(*str(ref.get("path", "")).split("/"))
        actual_sha = _sha256(path) if path.is_file() and not path.is_symlink() else None
        artifact_id = ref.get("id")
        produced = next((e for e in ordered if _kind(e) in {"artifact_produced", "artifact_written"} and e.get("artifact_id") == artifact_id), None)
        registered = next((e for e in ordered if _kind(e) == "artifact_registered" and e.get("artifact_id") == artifact_id), None)
        task_id = str(ref.get("task_id", state.get("task_id")))
        task_revision = int(ref.get("revision", state.get("revision", 0)))
        if actual_sha == ref.get("content_sha256") and actual_sha:
            envelope, envelope_error = _artifact_envelope(path.read_bytes(), artifact_id=str(artifact_id), task_id=task_id, task_revision=task_revision)
        elif registered and isinstance(registered.get("artifact_envelope"), dict):
            envelope, envelope_error = _artifact_envelope(json.dumps(registered["artifact_envelope"], separators=(",", ":")).encode("utf-8"), artifact_id=str(artifact_id), task_id=task_id, task_revision=task_revision)
        else:
            envelope, envelope_error = None, "artifact bytes are unavailable and no registration attestation was provided"
        selections = [e for e in ordered if _kind(e) in {"artifact_selected", "handoff", "role_dispatch"} and artifact_id in e.get("artifact_ids", [])]
        consumers = [e for e in selections if e.get("role") not in {None, "controller"} or e.get("consumer_role")]
        valid_item_ids = set()
        if envelope:
            for field in ("confirmed_facts", "inferences", "unknowns", "contradictions"):
                valid_item_ids.update(f"{field}:{index}" for index, _ in enumerate(envelope[field]))
            valid_item_ids.update(f"verification:{index}" for index, _ in enumerate(envelope["verification"]))
        carried = [e for e in selections if (e.get("content_sha256") == ref.get("content_sha256") or any(isinstance(item, dict) and item.get("content_sha256") == ref.get("content_sha256") for item in e.get("artifacts", []))) and set(e.get("evidence_item_ids", [])) <= valid_item_ids]
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
            "produced_provenance": _provenance(produced),
            "registered_provenance": _provenance(registered),
            "dispatch_provenance": [_provenance(item) for item in selections],
            "consumer_roles": sorted({str(item.get("consumer_role") or item.get("role")) for item in consumers}),
            "carried_content_identity": bool(carried),
            "supersedes": list(ref.get("supersedes", [])),
            "active": artifact_id not in superseded_ids,
            "envelope": envelope,
            "envelope_error": envelope_error,
        }
        artifact["bytes_match"] = actual_sha == ref.get("content_sha256")
        artifact["registered_before_dispatch"] = bool(
            registered and (not selections or all(_before(registered, item) for item in selections))
        )
        artifact["produced_before_registration"] = bool(produced and registered and _before(produced, registered))
        artifact["used"] = bool(consumers and carried)
        artifact["registration_attested"] = bool(registered and registered.get("content_sha256") == ref.get("content_sha256"))
        artifact["selected_item_ids_valid"] = bool(carried)
        artifacts.append(artifact)
    return {"evidence_required": "REQUIRED" if evidence_required else "NOT_REQUIRED", "artifacts": artifacts, "routing_roles": sorted(roles)}


def collect_candidate(root: Path, *, policy: dict[str, Any] | None = None) -> dict[str, Any]:
    """Collect candidate identity from the actual product surface."""
    return build_manifest(root, policy)


def collect_sessions(events: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Enumerate every observed model invocation, including failed/orphaned ones."""
    ordered = sorted(_require_trusted(events), key=lambda item: _order(item, -1))
    sessions: dict[str, dict[str, Any]] = {}
    for event in ordered:
        if _kind(event) not in {"session_usage", "rollout_session", "model_usage", "token_usage_record"}:
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        session_id = event.get("session_id") or event.get("_session_identity")
        usage = event.get("usage")
        if _kind(event) == "token_usage_record":
            session_id = session_id or payload.get("session_id")
            usage = payload.get("thread_token_usage") or payload.get("usage")
        if isinstance(usage, dict) and "input" not in usage and "input_tokens" in usage:
            usage = {"input": usage.get("input_tokens"), "cached_input": usage.get("cached_input_tokens", 0), "output": usage.get("output_tokens")}
        if not isinstance(session_id, str) or not session_id or not isinstance(usage, dict):
            continue
        item = {
            "session_id": session_id,
            "role": event.get("role") or event.get("_role_identity"),
            "model": event.get("model") or event.get("_model_identity"),
            "input": usage.get("input"),
            "cached_input": usage.get("cached_input"),
            "output": usage.get("output"),
            "status": event.get("status", "UNKNOWN"),
            "source": event.get("_trusted_source"),
            "source_file": event.get("_source_file"),
            "source_line": event.get("_source_line"),
            "native_event_id": event.get("_native_event_id"),
        }
        previous = sessions.get(session_id)
        if previous is not None and previous != item:
            if _kind(event) != "token_usage_record":
                raise ValueError(f"conflicting usage records for session {session_id}")
            # Native rollout records expose a cumulative thread total.  Keep
            # the latest source-ordered total instead of counting each turn
            # as another session.  A plain per-turn record is only additive.
            if isinstance(payload.get("thread_token_usage"), dict):
                sessions[session_id] = item
                continue
            for field in ("input", "cached_input", "output"):
                item[field] = int(previous[field] or 0) + int(item[field] or 0)
        sessions[session_id] = item
    return [sessions[key] for key in sorted(sessions)]


def collect_candidate_chain(root: Path, events: Iterable[dict[str, Any]], *, policy: dict[str, Any] | None = None) -> dict[str, Any]:
    """Bind stage-time host attestations to the manifest computed now."""
    actual = str(build_manifest(root, policy)["identity"])
    ordered = sorted(_require_trusted(events), key=lambda item: _order(item, -1))
    stages = {"runtime-final": "runtime_candidate", "review-start": "reviewed_candidate", "verification-start": "verified_candidate", "evaluator-start": "evaluator_candidate", "seal": "sealed_candidate"}
    values: dict[str, Any] = {}
    attestations = [event for event in ordered if _kind(event) == "candidate_attestation" and event.get("_trusted_source") == "harness_attestation"]
    for stage, field in stages.items():
        matches = [event for event in attestations if event.get("stage") == stage and event.get("candidate_root") == str(root.resolve()) and event.get("manifest_version") == MANIFEST_VERSION and isinstance(event.get("harness_identity"), str) and event.get("harness_identity")]
        values[field] = matches[-1].get("candidate_identity") if matches else None
        values[f"{field}_provenance"] = _provenance(matches[-1]) if matches else None
    ready_orders = [event for event in ordered if _kind(event) == "review_verdict" and event.get("verdict") == "READY" and isinstance(event.get("session_id"), str) and any(att.get("stage") == "review-start" and att.get("session_id") == event.get("session_id") and att.get("candidate_identity") == actual and _before(att, event) for att in attestations)]
    values["review_verdict"] = "READY" if ready_orders else None
    ready_order = ready_orders[-1] if ready_orders else None
    values["source_mutations_after_ready"] = bool(ready_order and any(_before(ready_order, event) and _kind(event) == "source_mutation" for event in ordered))
    values["computed_candidate"] = actual
    return values


def collect_review_graph(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Collect reviewer edges from native session and review events.

    A caller must provide native session identity and sandbox observation.  The
    collector never treats a prose ``fresh`` flag as proof of either property.
    """
    ordered = sorted(_require_trusted(events), key=lambda item: _order(item, -1))
    sessions: set[str] = set()
    graph: list[dict[str, Any]] = []
    for event in ordered:
        if _kind(event) in {"native_session_started", "SubagentStart"} and event.get("role") == "reviewer" and isinstance(event.get("session_id"), str):
            sessions.add(event["session_id"])
        if _kind(event) != "review_verdict":
            continue
        session = event.get("session_id")
        starts = [att for att in ordered if _kind(att) == "candidate_attestation" and att.get("stage") == "review-start" and att.get("session_id") == session and att.get("_trusted_source") == "harness_attestation"]
        if not isinstance(session, str) or not starts:
            continue
        candidate = starts[-1].get("candidate_identity")
        graph.append({
            "reviewer_session": session,
            "input_candidate_identity": candidate,
            "verdict": event.get("verdict"),
            "finding_id": event.get("finding_id"),
            "classification": event.get("classification"),
            "evidence_identity": event.get("evidence_identity"),
            "native_session": session in sessions,
            "sandbox_mode": starts[-1].get("sandbox_mode"),
            "order": _order(event, -1)[0],
            "attestation_provenance": _provenance(starts[-1]),
            "verdict_provenance": _provenance(event),
        })
    corrections: list[dict[str, Any]] = []
    for review in graph:
        if review.get("verdict") != "REQUEST_CHANGES":
            continue
        dispatch = next((e for e in ordered if _kind(e) == "implementer_dispatch" and e.get("candidate_from") == review["input_candidate_identity"] and e.get("finding_id") == review.get("finding_id")), None)
        if dispatch is None:
            continue
        implementer_session = dispatch.get("session_id")
        mutation = next((e for e in ordered if _kind(e) == "source_mutation" and e.get("session_id") == implementer_session and _before(dispatch, e)), None)
        if mutation is None:
            continue
        candidate_to = mutation.get("candidate_identity")
        verification = next((e for e in ordered if _kind(e) in {"deterministic_verification", "verification"} and e.get("candidate_identity") == candidate_to and e.get("outcome") == "PASSED" and _before(mutation, e)), None)
        if verification is None:
            continue
        corrections.append({"from_candidate": review["input_candidate_identity"], "finding_id": review.get("finding_id"), "implementer_session": implementer_session, "to_candidate": candidate_to, "verification_order": _order(verification, -1)[0], "dispatch_provenance": _provenance(dispatch), "mutation_provenance": _provenance(mutation), "verification_provenance": _provenance(verification)})
    seen_states: set[tuple[Any, Any, Any]] = set()
    no_progress: list[dict[str, Any]] = []
    for review in graph:
        state = (
            review.get("input_candidate_identity"),
            review.get("finding_id"),
            review.get("evidence_identity"),
        )
        if state in seen_states:
            no_progress.append({
                "candidate": state[0],
                "finding_id": state[1],
                "evidence_identity": state[2],
                "provenance": review.get("verdict_provenance"),
            })
        seen_states.add(state)
    return {"review_rounds": graph, "correction_edges": corrections, "native_reviewer_sessions": sorted(sessions), "no_progress_cycles": no_progress}
