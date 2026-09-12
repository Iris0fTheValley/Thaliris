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
import time
import uuid

from candidate_manifest import MANIFEST_VERSION, build_manifest
from d11_sources import AuthorityRegistry, SOURCE_EVENTS, SOURCE_KINDS, _sha_prefix, chain_payload, create_source_registry, hash_chain_record, registry_sources, validate_event_shape


TRUSTED_SOURCE_KINDS = SOURCE_KINDS


def load_trusted_events(registry: dict[str, Any], *, authority_registry: AuthorityRegistry | None = None) -> list[dict[str, Any]]:
    """Normalize only explicitly classified host/harness streams.

    A random JSON path or an unclassified dict is not an event source.  The
    original source, line, native identity, and ingestion order are retained
    for later audit; raw sequence fields are never used as global time.
    """
    records: list[dict[str, Any]] = []
    source_payload = registry_sources(registry, authority_registry=authority_registry)
    registry_identity = registry.get("identity")
    for source in source_payload:
        kind = source["source_kind"]
        path = Path(source["canonical_path"]).resolve()
        source_sha256 = _sha256(path)
        stream_policy = source.get("stream_identity_policy", "exact_bytes")
        if stream_policy == "exact_bytes" and source_sha256 != source["content_sha256"]:
            raise ValueError(f"registered source changed: {path}")
        if stream_policy == "append_only" and (path.stat().st_size < int(source.get("initial_size", 0)) or _sha_prefix(path, int(source.get("initial_size", 0))) != source["content_sha256"]):
            raise ValueError(f"registered source changed: {path}")
        session_identity = None
        role_identity = None
        model_identity = None
        previous_chain_hash = "0" * 64
        expected_sequence = 1
        test_stream = bool(registry.get("registry", {}).get("test_only"))
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
                normalized_kind = str(raw.get("event") or raw.get("kind") or raw.get("type") or "")
                if normalized_kind not in source["allowed_event_types"]:
                    # A known event in the wrong producer stream is a hard
                    # failure; genuinely unknown rollout noise is not a fact.
                    if normalized_kind in set().union(*SOURCE_EVENTS.values()):
                        raise ValueError(f"{normalized_kind} is not allowed in {kind}")
                    continue
                if not test_stream and not validate_event_shape(kind, normalized_kind, raw):
                    raise ValueError(f"{normalized_kind} has an invalid {kind} schema")
                if not test_stream and normalized_kind == "source_snapshot_attestation" and raw.get("run_id") != source["run_id"]:
                    raise ValueError("source snapshot attestation run identity is invalid")
                if kind == "harness_attestation" and not test_stream:
                    if not all(key in raw for key in ("run_id", "sequence", "previous_hash", "payload_hash", "record_hash", "source_registry_identity", "harness_identity")):
                        raise ValueError("formal harness attestation is missing hash-chain fields")
                    if raw.get("run_id") != source["run_id"] or raw.get("source_registry_identity") != registry_identity or raw.get("sequence") != expected_sequence or raw.get("previous_hash") != previous_chain_hash:
                        raise ValueError("formal harness attestation hash-chain ordering is invalid")
                    payload_hash = hashlib.sha256(json.dumps(chain_payload(raw), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
                    if raw.get("payload_hash") != payload_hash or raw.get("record_hash") != hash_chain_record(raw):
                        raise ValueError("formal harness attestation hash-chain identity is invalid")
                    previous_chain_hash = raw["record_hash"]
                    expected_sequence += 1
                native_id = raw.get("native_event_id") or raw.get("event_id") or f"{kind}:{path}:{line_number}"
                records.append({
                    **raw,
                    "_trusted_source": kind,
                    "_source_id": source["source_id"],
                    "_source_run_id": source["run_id"],
                    "_registry_identity": registry_identity,
                    "_source_file": str(path),
                    "_source_sha256": source_sha256,
                    "_source_line": line_number,
                    "_native_event_id": str(native_id),
                    "_ingestion_index": len(records),
                    "_normalized_kind": normalized_kind,
                    "_session_identity": str(session_identity) if session_identity else None,
                    "_role_identity": str(role_identity) if role_identity else None,
                    "_model_identity": str(model_identity) if model_identity else None,
                })
    return records


def _require_trusted(events: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    records = list(events)
    if any(not isinstance(event, dict) or event.get("_trusted_source") not in TRUSTED_SOURCE_KINDS or not event.get("_source_id") or not event.get("_registry_identity") for event in records):
        raise ValueError("collector accepts only normalized trusted events")
    return records


def load_jsonl(paths: Iterable[Path]) -> list[dict[str, Any]]:
    raise ValueError("load_jsonl is TEST_ONLY/UNTRUSTED_COMPATIBILITY; create a frozen source registry")


def load_test_events(sources: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compatibility fixture loader; never use this for a formal run."""
    entries = []
    all_events = sorted(set().union(*SOURCE_EVENTS.values()))
    for source in sources:
        if not isinstance(source, dict) or set(source) != {"kind", "path"}:
            raise ValueError("test source entry is invalid")
        entries.append({"kind": source["kind"], "path": source["path"], "allowed_event_types": all_events, "producer": "TEST_ONLY"})
    return load_trusted_events(create_source_registry(entries, run_id="TEST_ONLY", test_only=True))


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
    # A canonical path alone is not a stream identity.  A registry may (or a
    # malicious caller could) describe the same bytes under two producer
    # entries; treating those entries as one timeline lets unrelated events be
    # joined into a review/evidence transaction.  Same-stream ordering is
    # valid only when both the source id and canonical file agree.
    if (
        left.get("_source_id") == right.get("_source_id")
        and left.get("_source_file") == right.get("_source_file")
    ):
        return _order(left, -1) < _order(right, -1)
    # Cross-source order has no shared clock.  It is admitted only by the
    # single, typed canonical identity of the earlier normalized event.
    # Optional plural ``causes`` are descriptive; they do not authorize a
    # transaction edge and therefore cannot be used as an ordering bypass.
    caused_by = right.get("caused_by")
    return isinstance(caused_by, str) and caused_by == _canonical_event_identity(left)


def _canonical_event_identity(event: dict[str, Any]) -> str | None:
    """Return exactly one typed identity for a normalized trusted event."""
    explicit = (
        ("native", event.get("native_event_id")),
        ("event", event.get("event_id")),
        ("attestation", event.get("attestation_id")),
        ("observation", event.get("observation_id")),
    )
    present = [(kind, value) for kind, value in explicit if isinstance(value, str) and value]
    if len(present) == 1:
        kind, value = present[0]
        return f"{kind}:{value}"
    if present:
        return None
    native = event.get("_native_event_id")
    return f"native:{native}" if isinstance(native, str) and native else None


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


def attest_source_snapshot(output_path: Path, *, run_id: str, candidate_root: Path, path: str, session_id: str, producer_identity: str) -> dict[str, Any]:
    """Write a host-observed repository snapshot, never a model assertion."""
    if not isinstance(run_id, str) or not run_id or not isinstance(session_id, str) or not session_id or not isinstance(producer_identity, str) or not producer_identity:
        raise ValueError("source snapshot provenance is required")
    if not isinstance(path, str) or not path or "\\" in path or path.startswith("/") or ".." in path.split("/"):
        raise ValueError("source snapshot path must be repo-relative")
    candidate_root = candidate_root.resolve()
    target = candidate_root.joinpath(*path.split("/"))
    if target.is_symlink() or not target.is_file():
        raise ValueError("source snapshot target must be a regular file")
    event = {
        "event": "source_snapshot_attestation",
        "observation_id": str(uuid.uuid4()),
        "run_id": run_id,
        "path": path,
        "content_sha256": _sha256(target),
        "session_id": session_id,
        "producer_identity": producer_identity,
        "candidate_root": str(candidate_root),
        "observed_at_ns": time.time_ns(),
    }
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")
    return event


def _ref_key(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _artifact_envelope(data: bytes, *, artifact_id: str, task_id: str, task_revision: int, allow_legacy: bool = False) -> tuple[dict[str, Any] | None, str | None]:
    if len(data) > 32 * 1024:
        return None, "artifact exceeds bounded envelope size"
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, "artifact is not a structured UTF-8 JSON envelope"
    legacy = {"artifact_id", "task_id", "task_revision", "source_refs", "affected_surface", "confirmed_facts", "inferences", "unknowns", "contradictions", "verification"}
    required = {"artifact_id", "task_id", "producer_base_revision", "producer_session", "producer_identity", "source_refs", "affected_surface", "confirmed_facts", "inferences", "unknowns", "contradictions", "verification"}
    if allow_legacy and isinstance(value, dict) and set(value) == legacy:
        legacy_value = dict(value)
        base_revision = legacy_value.pop("task_revision")
        value = {**legacy_value, "producer_base_revision": base_revision, "producer_session": "TEST_ONLY", "producer_identity": "TEST_ONLY"}
        value["source_refs"] = [{"kind": "event", "source_id": "TEST_ONLY", "native_event_id": str(ref)} if isinstance(ref, str) else ref for ref in value["source_refs"]]
        for field in ("confirmed_facts", "inferences", "unknowns", "contradictions", "verification"):
            for item in value[field]:
                key = "source_refs"
                item[key] = [{"kind": "event", "source_id": "TEST_ONLY", "native_event_id": str(ref)} if isinstance(ref, str) else ref for ref in item[key]]
    if not isinstance(value, dict) or set(value) != required:
        return None, "artifact envelope fields are incomplete or unbounded"
    if value["artifact_id"] != artifact_id or value["task_id"] != task_id:
        return None, "artifact envelope identity does not match Core pointer"
    if not isinstance(value["artifact_id"], str) or not value["artifact_id"] or not isinstance(value["task_id"], str) or not value["task_id"] or not isinstance(value["producer_base_revision"], int) or value["producer_base_revision"] < 0 or not isinstance(value["producer_session"], str) or not value["producer_session"] or not isinstance(value["producer_identity"], str) or not value["producer_identity"]:
        return None, "artifact envelope provenance is malformed"
    if any(not isinstance(value[key], list) or len(value[key]) > 32 for key in required - {"artifact_id", "task_id", "producer_base_revision", "producer_session", "producer_identity"}):
        return None, "artifact envelope lists are not bounded"
    if not all(isinstance(item, str) and item.strip() for item in value["affected_surface"]):
        return None, "artifact affected_surface is malformed"
    source_refs = value["source_refs"]
    if not all(isinstance(item, dict) and isinstance(item.get("kind"), str) and item.get("kind") in {"repo", "event", "verification"} for item in source_refs):
        return None, "artifact source_refs are malformed"
    source_set = {_ref_key(item) for item in source_refs}
    for field in ("confirmed_facts", "inferences", "unknowns", "contradictions"):
        for item in value[field]:
            if not isinstance(item, dict) or set(item) != {"text", "source_refs"} or not isinstance(item["text"], str) or not item["text"].strip() or not isinstance(item["source_refs"], list) or not {_ref_key(ref) for ref in item["source_refs"]} <= source_set:
                return None, f"artifact {field} contains malformed statements"
            if field == "confirmed_facts" and not item["source_refs"]:
                return None, "confirmed facts require supporting source refs"
    for item in value["verification"]:
        if not isinstance(item, dict) or set(item) != {"description", "source_refs"} or not isinstance(item["description"], str) or not item["description"].strip() or not isinstance(item["source_refs"], list) or not {_ref_key(ref) for ref in item["source_refs"]} <= source_set:
            return None, "artifact verification is malformed"
    return value, None


def _resolve_source_refs(envelope: dict[str, Any], root: Path, events: list[dict[str, Any]]) -> tuple[bool, str | None]:
    test_stream = any(event.get("_source_run_id") == "TEST_ONLY" for event in events)
    # Diagnostic fixtures remain inspectable.  Formal gates reject their
    # candidate/review chain before a diagnostic ledger can be reported.
    if envelope.get("producer_identity") == "TEST_ONLY" or test_stream:
        return True, None
    event_ids = {(event.get("_source_id"), event.get("_native_event_id")) for event in events}
    verification_ids = {event.get("attestation_id") for event in events if _kind(event) in {"verification_attestation", "deterministic_verification", "verification"}}
    snapshots = {
        event.get("observation_id"): event
        for event in events
        if _kind(event) == "source_snapshot_attestation" and isinstance(event.get("observation_id"), str)
    }
    for ref in envelope["source_refs"]:
        kind = ref.get("kind")
        if kind == "repo":
            path = ref.get("path")
            if not isinstance(path, str) or not path or "\\" in path or path.startswith("/") or ".." in path.split("/"):
                return False, "repository source reference is not repo-relative"
            target = root.joinpath(*path.split("/"))
            observation_id = ref.get("observation_id")
            observed = snapshots.get(observation_id)
            if not isinstance(observation_id, str) or observed is None:
                return False, "repository source reference lacks a trusted observation"
            if (
                observed.get("path") != path
                or observed.get("content_sha256") != ref.get("content_sha256")
                or observed.get("candidate_root") != str(root.resolve())
                or observed.get("run_id") not in {event.get("_source_run_id") for event in events if event.get("_source_run_id")}
            ):
                return False, "repository source reference does not match its trusted observation"
            # Recompute at consumption time.  The source snapshot proves
            # historical observation; it does not make later bytes fresh.
            if target.is_symlink() or not target.is_file() or _sha256(target) != ref.get("content_sha256"):
                return False, "repository source reference target is unavailable"
            if observed.get("_trusted_source") != "thaliris_audit":
                return False, "repository source observation is outside the trusted capture boundary"
            if observed.get("session_id") != envelope.get("producer_session") or observed.get("producer_identity") != envelope.get("producer_identity"):
                return False, "repository source observation is not bound to the artifact producer"
            starts = [event for event in events if event.get("_trusted_source") == "codex_rollout" and _kind(event) in {"SubagentStart", "native_session_started"} and event.get("session_id") == envelope.get("producer_session")]
            if not starts or not any(envelope.get("producer_identity") in {event.get("session_id"), event.get("native_event_id"), event.get("_native_event_id"), event.get("producer_identity"), event.get("session_identity")} for event in starts):
                return False, "repository source observation lacks a trusted producer lifecycle"
        elif kind == "event":
            if (ref.get("source_id"), ref.get("native_event_id")) not in event_ids:
                return False, "native event source reference is not observed"
        elif kind == "verification":
            if ref.get("attestation_id") not in verification_ids:
                return False, "verification source reference is not observed"
    return True, None


def _producer_lifecycle(envelope: dict[str, Any] | None, artifact_id: str, producer_role: str | None, produced: dict[str, Any] | None, events: list[dict[str, Any]]) -> tuple[bool, str | None]:
    """Bind an artifact producer to a real native child lifecycle."""
    if envelope is None:
        return False, "artifact envelope is absent"
    if any(event.get("_source_run_id") == "TEST_ONLY" for event in events) or envelope.get("producer_identity") == "TEST_ONLY":
        return True, None
    session_id = envelope.get("producer_session")
    identity = envelope.get("producer_identity")
    if not isinstance(session_id, str) or not isinstance(identity, str):
        return False, "producer identity is malformed"
    # Native producer lifecycle is owned by the Codex rollout stream.  Audit
    # and harness streams can describe that lifecycle, but cannot create it;
    # accepting their similarly named events would let a producer self-attest.
    starts = [event for event in events if event.get("_trusted_source") == "codex_rollout" and _kind(event) in {"SubagentStart", "native_session_started"} and event.get("session_id") == session_id]
    if not starts:
        return False, "producer native session start is not observed"
    start = starts[-1]
    observed_role = str(start.get("role") or start.get("agent_role") or "").lower()
    if observed_role not in {"investigator", "curator"} or observed_role != str(producer_role or "").lower():
        return False, "producer native role does not match artifact producer role"
    identities = {session_id, str(start.get("native_event_id") or start.get("_native_event_id") or ""), str(start.get("producer_identity") or ""), str(start.get("session_identity") or "")}
    if identity not in identities:
        return False, "producer identity is not bound to native session"
    if produced is None or produced.get("producer_session") != session_id:
        return False, "artifact production is not bound to producer session"
    stops = [event for event in events if event.get("_trusted_source") == "codex_rollout" and _kind(event) in {"SubagentStop", "native_session_stopped"} and event.get("session_id") == session_id]
    if not stops or not _before(start, produced) or not any(_before(produced, stop) for stop in stops):
        return False, "artifact production is outside observed producer lifecycle"
    return True, None


def collect_evidence(root: Path, events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Derive the reusable-evidence lifecycle from state, bytes, and events."""
    state = _state(root)
    ordered = sorted(_require_trusted(events), key=lambda item: _order(item, -1))
    roles = {str(event.get("role") or event.get("consumer_role")) for event in ordered if event.get("role") or event.get("consumer_role")}
    downstream_roles = {"controller", "reasoning-specialist", "implementer", "reviewer", "terra", "sol"}
    producer_roles = {
        str(ref.get("producer_role") or ref.get("producer"))
        for ref in state.get("artifact_refs", [])
        if isinstance(ref, dict) and (ref.get("producer_role") or ref.get("producer"))
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
        allow_legacy = any(event.get("_source_run_id") == "TEST_ONLY" for event in ordered)
        if actual_sha == ref.get("content_sha256") and actual_sha:
            envelope, envelope_error = _artifact_envelope(path.read_bytes(), artifact_id=str(artifact_id), task_id=task_id, task_revision=task_revision, allow_legacy=allow_legacy)
        elif registered and isinstance(registered.get("artifact_envelope"), dict):
            envelope, envelope_error = _artifact_envelope(json.dumps(registered["artifact_envelope"], separators=(",", ":")).encode("utf-8"), artifact_id=str(artifact_id), task_id=task_id, task_revision=task_revision, allow_legacy=allow_legacy)
        else:
            envelope, envelope_error = None, "artifact bytes are unavailable and no registration attestation was provided"
        selections = [e for e in ordered if _kind(e) in {"artifact_selected", "handoff", "role_dispatch"} and artifact_id in e.get("artifact_ids", [])]
        consumers = [e for e in selections if e.get("role") not in {None, "controller"} or e.get("consumer_role")]
        valid_item_ids = set()
        if envelope:
            for field in ("confirmed_facts", "inferences", "unknowns", "contradictions"):
                valid_item_ids.update(f"{field}:{index}" for index, _ in enumerate(envelope[field]))
            valid_item_ids.update(f"verification:{index}" for index, _ in enumerate(envelope["verification"]))
        source_refs_valid, source_ref_error = _resolve_source_refs(envelope, root, ordered) if envelope else (False, None)
        producer_role = ref.get("producer_role") or ref.get("producer")
        producer_lifecycle_valid, producer_lifecycle_error = _producer_lifecycle(envelope, str(artifact_id), producer_role, produced, ordered)
        carried = [e for e in selections if (e.get("content_sha256") == ref.get("content_sha256") or any(isinstance(item, dict) and item.get("content_sha256") == ref.get("content_sha256") for item in e.get("artifacts", []))) and bool(e.get("evidence_item_ids")) and set(e.get("evidence_item_ids", [])) <= valid_item_ids and source_refs_valid]
        pointer_reads = [e for e in ordered if _kind(e) in {"artifact_read", "artifact_open"} and e.get("artifact_id") == artifact_id and e.get("content_sha256") == ref.get("content_sha256") and e.get("session_id")]
        artifact = {
            "id": artifact_id,
            "task_id": state.get("task_id"),
            "revision": ref.get("revision", state.get("revision")),
            "producer_role": producer_role,
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
            "source_refs_valid": source_refs_valid,
            "source_ref_error": source_ref_error,
            "producer_lifecycle_valid": producer_lifecycle_valid,
            "producer_lifecycle_error": producer_lifecycle_error,
            "selected": bool(selections),
            "selected_item_ids": sorted({item for event in carried for item in event.get("evidence_item_ids", [])}),
            "pointer_consumers": [_provenance(item) for item in pointer_reads],
        }
        artifact["bytes_match"] = actual_sha == ref.get("content_sha256")
        artifact["registration_attested"] = bool(registered and registered.get("content_sha256") == ref.get("content_sha256"))
        artifact["historical_validity"] = "PASS" if artifact["bytes_match"] or artifact["registration_attested"] else "FAIL"
        artifact["current_freshness"] = "FRESH" if artifact["active"] and artifact["bytes_match"] else "STALE"
        artifact["registered_before_dispatch"] = bool(
            registered and (not selections or all(_before(registered, item) for item in selections))
        )
        artifact["produced_before_registration"] = bool(produced and registered and _before(produced, registered))
        artifact["used"] = bool(consumers and carried) or bool(pointer_reads and source_refs_valid)
        artifact["selected_item_ids_valid"] = bool(carried)
        artifact["consumed"] = artifact["used"]
        artifacts.append(artifact)
    return {"evidence_required": "REQUIRED" if evidence_required else "NOT_REQUIRED", "artifacts": artifacts, "routing_roles": sorted(roles), "producer_lifecycle_observed": all(item.get("producer_lifecycle_valid") for item in artifacts) if artifacts else not evidence_required, "formal_collection": bool(ordered) and not any(event.get("_source_run_id") == "TEST_ONLY" for event in ordered)}


def collect_candidate(root: Path, *, policy: dict[str, Any] | None = None) -> dict[str, Any]:
    """Collect candidate identity from the actual product surface."""
    return build_manifest(root, policy)


def attest_candidate(output_path: Path, *, run_id: str, stage: str, candidate_root: Path, policy: dict[str, Any], harness_identity: str, session_id: str | None = None, source_registry_identity: str | None = None, caused_by: str | None = None, causes: list[str] | None = None, attestation_id: str | None = None, reviewer_binding: dict[str, Any] | None = None) -> dict[str, Any]:
    """Host-owned stage attestation; identity is computed at the stage boundary."""
    if not isinstance(run_id, str) or not run_id or stage not in {"runtime-final", "review-start", "review-end", "verification-start", "evaluator-start", "seal"}:
        raise ValueError("invalid candidate attestation boundary")
    if not isinstance(harness_identity, str) or not harness_identity:
        raise ValueError("harness identity is required")
    candidate_root = candidate_root.resolve()
    manifest = build_manifest(candidate_root, policy)
    policy_identity = hashlib.sha256(json.dumps(manifest["manifest"]["policy"], sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    event = {
        "event": "candidate_attestation",
        "attestation_id": attestation_id or str(uuid.uuid4()),
        "run_id": run_id,
        "stage": stage,
        "candidate_root": str(candidate_root),
        "candidate_identity": manifest["identity"],
        "manifest_version": MANIFEST_VERSION,
        "manifest_policy_identity": policy_identity,
        "harness_identity": harness_identity,
        "session_id": session_id,
        "order_identity": time.time_ns(),
    }
    if caused_by is not None:
        if not isinstance(caused_by, str) or not caused_by:
            raise ValueError("candidate attestation causal identity is invalid")
        event["caused_by"] = caused_by
    if causes is not None:
        if not isinstance(causes, list) or not causes or any(not isinstance(item, str) or not item for item in causes):
            raise ValueError("candidate attestation causal identities are invalid")
        event["causes"] = list(causes)
    if reviewer_binding is not None:
        if stage != "review-start" or not isinstance(reviewer_binding, dict):
            raise ValueError("reviewer binding is only valid at review start")
        event["reviewer_binding"] = dict(reviewer_binding)
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if source_registry_identity is not None:
        previous = "0" * 64
        sequence = 1
        if output_path.is_file() and output_path.stat().st_size:
            lines = output_path.read_text(encoding="utf-8").splitlines()
            last = json.loads(lines[-1])
            previous = str(last["record_hash"])
            sequence = int(last["sequence"]) + 1
        event["source_registry_identity"] = source_registry_identity
        event["sequence"] = sequence
        event["previous_hash"] = previous
        event["payload_hash"] = hashlib.sha256(json.dumps(chain_payload(event), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        event["record_hash"] = hash_chain_record(event)
    with output_path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")
    return event


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
    stages = {"runtime-final": "runtime_candidate", "review-start": "reviewed_candidate", "review-end": "review_end_candidate", "verification-start": "verified_candidate", "evaluator-start": "evaluator_candidate", "seal": "sealed_candidate"}
    values: dict[str, Any] = {}
    formal = bool(ordered) and not any(event.get("_source_run_id") == "TEST_ONLY" for event in ordered)
    attestations = [event for event in ordered if _kind(event) == "candidate_attestation" and event.get("_trusted_source") == "harness_attestation" and event.get("source_registry_identity") == event.get("_registry_identity")]
    expected_policy_identity = hashlib.sha256(json.dumps(build_manifest(root, policy)["manifest"]["policy"], sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    stage_counts: dict[str, int] = {}
    stage_events: list[dict[str, Any]] = []
    for stage, field in stages.items():
        matches = [event for event in attestations if event.get("stage") == stage and event.get("candidate_root") == str(root.resolve()) and event.get("manifest_version") == MANIFEST_VERSION and event.get("manifest_policy_identity", expected_policy_identity) == expected_policy_identity and isinstance(event.get("harness_identity"), str) and event.get("harness_identity")]
        stage_counts[stage] = len(matches)
        if matches:
            stage_events.append(matches[-1])
        values[field] = matches[-1].get("candidate_identity") if matches else None
        values[f"{field}_provenance"] = _provenance(matches[-1]) if matches else None
    ready_orders = [event for event in ordered if _kind(event) == "review_verdict" and event.get("verdict") == "READY" and isinstance(event.get("session_id"), str) and any(att.get("stage") == "review-start" and att.get("session_id") == event.get("session_id") and att.get("candidate_identity") == actual and _before(att, event) for att in attestations)]
    values["review_verdict"] = "READY" if ready_orders else None
    ready_order = ready_orders[-1] if ready_orders else None
    values["source_mutations_after_ready"] = bool(ready_order and any(_before(ready_order, event) and _kind(event) == "source_mutation" for event in ordered))
    values["computed_candidate"] = actual
    values["stage_counts"] = stage_counts
    # Stream indexes are local only. Each stage transition must be same-source
    # ordered or have the exact typed caused_by identity of its predecessor.
    values["stage_order_valid"] = len(stage_events) == len(stages) and all(
        _before(left, right) for left, right in zip(stage_events, stage_events[1:])
    )
    values["formal_collection"] = formal
    values["stage_provenance_complete"] = all(values.get(f"{field}_provenance") for field in stages.values())
    values["review_verdict_provenance"] = _provenance(ready_order)
    values["review_verdict_collector_backed"] = bool(ready_order and ready_order.get("_trusted_source") == "codex_rollout")
    return values


def collect_review_graph(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Collect reviewer edges from native lifecycle and review transactions.

    Native sandbox mode is retained as a capability diagnostic only.  The hard
    correctness fact is a fresh native session with matching stop and
    host-attested start/end candidate identities.
    """
    ordered = sorted(_require_trusted(events), key=lambda item: _order(item, -1))
    sessions: set[str] = set()
    stops: dict[str, list[dict[str, Any]]] = {}
    graph: list[dict[str, Any]] = []
    test_stream = any(event.get("_source_run_id") == "TEST_ONLY" for event in ordered)
    for event in ordered:
        if (test_stream or event.get("_trusted_source") == "codex_rollout") and _kind(event) in {"native_session_started", "SubagentStart"} and event.get("role") == "reviewer" and isinstance(event.get("session_id"), str):
            sessions.add(event["session_id"])
        if (test_stream or event.get("_trusted_source") == "codex_rollout") and _kind(event) in {"native_session_stopped", "SubagentStop"} and isinstance(event.get("session_id"), str):
            stops.setdefault(event["session_id"], []).append(event)
    for event in ordered:
        if _kind(event) != "review_verdict":
            continue
        session = event.get("session_id")
        starts = [att for att in ordered if _kind(att) == "candidate_attestation" and att.get("stage") == "review-start" and att.get("session_id") == session and att.get("_trusted_source") == "harness_attestation"]
        if not isinstance(session, str) or not starts:
            continue
        candidate = starts[-1].get("candidate_identity")
        review_start = starts[-1]
        binding = review_start.get("reviewer_binding")
        ends = [att for att in ordered if _kind(att) == "candidate_attestation" and att.get("stage") == "review-end" and att.get("session_id") == session and att.get("_trusted_source") == "harness_attestation"]
        observations = [obs for obs in ordered if _kind(obs) == "reviewer_native_observation" and obs.get("session_id") == session and obs.get("native_session_id")]
        mutations = [mutation for mutation in ordered if _kind(mutation) == "source_mutation" and mutation.get("session_id") == session]
        stop = stops.get(session, [])
        end = ends[-1] if ends else None
        native_starts = [item for item in ordered if (test_stream or item.get("_trusted_source") == "codex_rollout") and _kind(item) in {"native_session_started", "SubagentStart"} and item.get("role") == "reviewer" and item.get("session_id") == session]
        native_start = native_starts[-1] if native_starts else None
        verdict_after_start = bool(native_start and _before(native_start, event))
        completion_after_start = bool(native_start and stop and any(_before(native_start, item) for item in stop))
        completion_before_end = bool(stop and end and any(_before(item, end) for item in stop))
        verdict_before_end = bool(stop and end and any(_before(event, item) and _before(item, end) for item in stop))
        review_start_before_native = bool(native_start and _before(review_start, native_start))
        integrity = bool(
            session in sessions
            and stop
            and end
            and review_start_before_native
            and verdict_after_start
            and completion_after_start
            and completion_before_end
            and verdict_before_end
            and candidate
            and end.get("candidate_identity") == candidate
            and not mutations
        )
        start_order_valid = review_start_before_native
        if not test_stream:
            # The review-start attestation authorizes one, and only one,
            # *subsequent* native Reviewer start.  A lifecycle record before
            # it or a copied reservation/projection is not a review session.
            expected = ("task_id", "task_revision", "controller_session_id", "reservation_id", "projection_id", "parent_session_id")
            native_starts = [item for item in ordered if item.get("_trusted_source") == "codex_rollout" and _kind(item) in {"native_session_started", "SubagentStart"} and item.get("role") == "reviewer"]
            after = [item for item in native_starts if _before(review_start, item)]
            first = after[0] if after else None
            start_order_valid = bool(
                isinstance(binding, dict) and first is not None
                and first.get("session_id") == session and first.get("role") == "reviewer"
                and all(first.get(key) == binding.get(key) for key in expected)
                and first.get("native_sequence") == binding.get("native_sequence")
                and not any(item.get("session_id") == session and not _before(review_start, item) for item in native_starts)
                and len([item for item in after if item.get("session_id") == session]) == 1
            )
            if not start_order_valid:
                integrity = False
        # Every formal review transaction must stay within one frozen run and
        # registry.  Cross-stream ordering is otherwise admitted only through
        # explicit causal edges in ``_before``.
        if not test_stream:
            transaction_events = [starts[-1], event, end, *(stop or [])]
            identities = {(item.get("_source_run_id"), item.get("_registry_identity")) for item in transaction_events if item is not None}
            if len(identities) != 1:
                integrity = False
        graph.append({
            "reviewer_session": session,
            "input_candidate_identity": candidate,
            "verdict": event.get("verdict"),
            "finding_id": event.get("finding_id"),
            "classification": event.get("classification"),
            "evidence_identity": event.get("evidence_identity"),
            "native_session": session in sessions,
            "native_completion": bool(stop),
            "review_end_observed": bool(end),
            "completion_before_review_end": completion_before_end,
            "verdict_after_review_start": verdict_after_start,
            "verdict_before_review_end": verdict_before_end,
            "start_candidate_identity": candidate,
            "end_candidate_identity": end.get("candidate_identity") if end else None,
            "review_transaction_integrity": integrity,
            "reviewer_start_order_valid": start_order_valid,
            "reviewer_mutation_observed": bool(mutations),
            "sandbox_mode": observations[-1].get("sandbox_mode") if observations else None,
            "native_observation_provenance": _provenance(observations[-1]) if observations else None,
            "order": _order(event, -1)[0],
            "attestation_provenance": _provenance(starts[-1]),
            "review_end_provenance": _provenance(end),
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
    return {"review_rounds": graph, "correction_edges": corrections, "native_reviewer_sessions": sorted(sessions), "no_progress_cycles": no_progress, "formal_collection": bool(ordered) and not test_stream}
