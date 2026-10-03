"""Deterministic D11 benchmark protocol gates.

The module consumes a compact ledger emitted by a benchmark driver.  It does
not inspect rollout prose, infer success from prompts, or run agents.
"""
from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal
from pathlib import Path
from typing import Any

ROUTING_PROTOCOL_VERSION = "thaliris-routing-v3"
ROUTING_PROTOCOL_MARKER = f"<!-- thaliris-routing-protocol: {ROUTING_PROTOCOL_VERSION} -->"

CLASSIFICATIONS = {"MECHANICAL", "LOCAL_SEMANTIC", "ARCHITECTURAL"}
REQUIRED_ARTIFACT_FIELDS = {
    "id", "producer_role", "task_id", "revision", "path", "content_sha256",
    "source_refs", "affected_surface", "confirmed_facts", "inferences",
    "unknowns", "contradictions", "verification", "produced_before_decision",
    "registered", "selected", "consumed_by", "superseded_by",
}


def _fail(code: str, detail: str) -> dict[str, Any]:
    return {"status": "FAIL", "code": code, "detail": detail}


def validate_evidence(ledger: dict[str, Any]) -> dict[str, Any]:
    required = ledger.get("evidence_required")
    if required == "NOT_REQUIRED":
        if ledger.get("artifacts"):
            return _fail("UNEXPECTED_EVIDENCE_ARTIFACT", "fast path manufactured reusable evidence")
        return {"status": "PASS", "required": "NOT_REQUIRED", "produced": 0, "registered": 0, "consumed": 0}
    if required != "REQUIRED":
        return _fail("INVALID_EVIDENCE_REQUIREMENT", "evidence_required must be REQUIRED or NOT_REQUIRED")
    artifacts = ledger.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        return _fail("EVIDENCE_ARTIFACT_MISSING", "reusable evidence was required but no artifact was produced")
    ids: set[str] = set()
    registered = selected = consumed = 0
    for artifact in artifacts:
        if not isinstance(artifact, dict) or set(artifact) != REQUIRED_ARTIFACT_FIELDS:
            return _fail("EVIDENCE_ARTIFACT_SCHEMA", "artifact record is incomplete or contains unbounded fields")
        artifact_id = artifact["id"]
        if not isinstance(artifact_id, str) or not artifact_id or artifact_id in ids:
            return _fail("EVIDENCE_ARTIFACT_ID", "artifact IDs must be unique and non-empty")
        ids.add(artifact_id)
        if not isinstance(artifact["producer_role"], str) or artifact["producer_role"] not in {"investigator", "curator"}:
            return _fail("EVIDENCE_ARTIFACT_PRODUCER", f"{artifact_id} has no semantic producer role")
        if not isinstance(artifact["task_id"], str) or not isinstance(artifact["revision"], int) or artifact["revision"] < 1:
            return _fail("EVIDENCE_ARTIFACT_IDENTITY", f"{artifact_id} has no task/revision identity")
        path = artifact["path"]
        private_roots = (".git", ".context", ".agent-memory", ".milestones")
        private_path = any(path == root or path.startswith(f"{root}/") for root in private_roots) if isinstance(path, str) else True
        if not isinstance(path, str) or not path or "\\" in path or path in {".", ".."} or path.startswith("/") or ".." in path.split("/") or private_path:
            return _fail("EVIDENCE_ARTIFACT_PATH", f"{artifact_id} is not repo-relative")
        if not isinstance(artifact["content_sha256"], str) or len(artifact["content_sha256"]) != 64:
            return _fail("EVIDENCE_ARTIFACT_IDENTITY", f"{artifact_id} has no content SHA-256")
        if not all(isinstance(artifact[field], list) for field in ("source_refs", "affected_surface", "confirmed_facts", "inferences", "unknowns", "contradictions", "verification", "selected", "consumed_by")):
            return _fail("EVIDENCE_ARTIFACT_BOUNDS", f"{artifact_id} has malformed bounded lists")
        if artifact["superseded_by"] is not None and not isinstance(artifact["superseded_by"], str):
            return _fail("EVIDENCE_SUPERSESSION", f"{artifact_id} has an invalid supersession identity")
        if artifact["produced_before_decision"] is not True:
            return _fail("EVIDENCE_LATE_PRODUCTION", f"{artifact_id} was written after its dependent decision")
        registration = artifact["registered"]
        if not isinstance(registration, dict) or registration.get("by") != "controller" or not isinstance(registration.get("before_decision"), bool):
            return _fail("EVIDENCE_NOT_REGISTERED", f"{artifact_id} lacks Controller registration evidence")
        if registration["before_decision"] is not True:
            return _fail("EVIDENCE_LATE_REGISTRATION", f"{artifact_id} was registered after its dependent decision")
        registered += 1
        if not artifact["selected"]:
            return _fail("EVIDENCE_NOT_SELECTED", f"{artifact_id} was registered but never selected")
        if any(not isinstance(item, dict) or not isinstance(item.get("role"), str) or not isinstance(item.get("facts"), list) or not item["facts"] for item in artifact["selected"]):
            return _fail("EVIDENCE_SELECTION_INVALID", f"{artifact_id} has no bounded selected facts")
        selected += len(artifact["selected"])
        if not artifact["consumed_by"]:
            return _fail("EVIDENCE_ARTIFACT_UNUSED", f"{artifact_id} has no downstream consumer")
        if any(not isinstance(item, dict) or not isinstance(item.get("role"), str) or not isinstance(item.get("purpose"), str) or not item["purpose"] for item in artifact["consumed_by"]):
            return _fail("EVIDENCE_CONSUMPTION_INVALID", f"{artifact_id} has malformed consumer records")
        consumed += len(artifact["consumed_by"])
    superseded_targets = {artifact["superseded_by"] for artifact in artifacts if artifact["superseded_by"] is not None}
    superseded_ids = {artifact["id"] for artifact in artifacts if artifact["superseded_by"] is not None}
    if not superseded_targets <= ids:
        return _fail("EVIDENCE_SUPERSESSION_TARGET", "superseded artifact target is not present in the ledger")
    active = ledger.get("active_artifacts", [item["id"] for item in artifacts if item["id"] not in superseded_ids])
    if not isinstance(active, list) or any(item not in ids or item in superseded_ids for item in active):
        return _fail("EVIDENCE_STALE_ACTIVE", "stale or superseded evidence remains active")
    return {"status": "PASS", "required": "REQUIRED", "produced": len(artifacts), "registered": registered, "selected": selected, "consumed": consumed, "superseded": len(superseded_ids)}


def validate_collected_evidence(ledger: dict[str, Any]) -> dict[str, Any]:
    """Validate facts emitted by d11_collector, never report declarations."""
    required = ledger.get("evidence_required")
    artifacts = ledger.get("artifacts")
    if required == "NOT_REQUIRED":
        return {"status": "PASS", "required": "NOT_REQUIRED", "produced": 0}
    if required != "REQUIRED" or not isinstance(artifacts, list) or not artifacts:
        return _fail("EVIDENCE_COLLECTOR_MISSING", "collector did not observe required artifacts")
    for item in artifacts:
        if not isinstance(item, dict):
            return _fail("EVIDENCE_COLLECTOR_SCHEMA", "collector artifact is not an object")
        if item.get("producer_role") not in {"investigator", "curator"} or item.get("registered_by") != "controller":
            return _fail("EVIDENCE_COLLECTOR_PROVENANCE", "artifact producer or registration is not Core-backed")
        if item.get("envelope") is None:
            return _fail("EVIDENCE_ARTIFACT_SCHEMA", str(item.get("envelope_error") or "artifact envelope is absent"))
        if item.get("producer_lifecycle_valid") is not True:
            return _fail("EVIDENCE_PRODUCER_LIFECYCLE", "artifact producer is not bound to an observed native child lifecycle")
        if item.get("active") is True and (item.get("bytes_match") is not True or item.get("current_freshness") != "FRESH"):
            return _fail("EVIDENCE_CONTENT_IDENTITY", "active artifact bytes do not match Core identity")
        if item.get("active") is not True and (item.get("registration_attested") is not True or item.get("historical_validity") != "PASS" or item.get("current_freshness") != "STALE"):
            return _fail("EVIDENCE_HISTORICAL_IDENTITY", "superseded artifact lacks registration-time identity attestation")
        if not item.get("produced_before_registration") or (
            item.get("dispatch_orders") and not item.get("registered_before_dispatch")
        ):
            return _fail("EVIDENCE_ORDERING", "production, registration, and dispatch ordering was not observed")
        if item.get("active") is not True and item.get("used"):
            return _fail("EVIDENCE_SUPERSEDED_CONSUMED", "superseded evidence was selected for a downstream handoff")
        if item.get("active") is True and (not item.get("source_refs_valid") or not item.get("used") or not item.get("consumed") or not item.get("carried_content_identity") and not item.get("pointer_consumers") or not item.get("selected_item_ids_valid") and not item.get("pointer_consumers")):
            return _fail("EVIDENCE_ARTIFACT_UNUSED", "registered evidence has no provenance-backed downstream consumer")
    return {"status": "PASS", "required": "REQUIRED", "produced": len(artifacts), "consumed": sum(len(item.get("consumer_roles", [])) for item in artifacts)}


def validate_review_graph(ledger: dict[str, Any], *, final_candidate: str, required: bool = True) -> dict[str, Any]:
    """Validate fresh native Reviewer sessions against their own candidates."""
    rounds = ledger.get("review_rounds")
    if not isinstance(rounds, list):
        return _fail("REVIEW_COLLECTOR_SCHEMA", "review rounds are malformed")
    if not rounds:
        if required:
            return _fail("REVIEW_MISSING", "selected review has no verdict")
        if ledger.get("correction_edges") or ledger.get("native_reviewer_sessions") or ledger.get("no_progress_cycles"):
            return _fail("REVIEW_SELECTION_INCONSISTENT", "review activity exists without a selected review")
        return {"status": "PASS", "rounds": 0, "sessions": [], "selection": "NOT_SELECTED"}
    seen: set[str] = set()
    edges = ledger.get("correction_edges", [])
    if not isinstance(edges, list):
        return _fail("CORRECTION_EDGE_SCHEMA", "collector correction edges are malformed")
    if ledger.get("no_progress_cycles"):
        return _fail("REVIEW_NO_PROGRESS", "the same candidate/finding/evidence state was reviewed again without new information")
    for item in rounds:
        if not isinstance(item, dict):
            return _fail("REVIEW_COLLECTOR_SCHEMA", "review fact is not an object")
        session = item.get("reviewer_session")
        if not isinstance(session, str) or not session or session in seen:
            return _fail("REVIEW_SESSION_REUSE", "reviewer session identity is missing or reused")
        seen.add(session)
        if item.get("native_session") is not True or item.get("native_completion") is not True:
            return _fail("REVIEW_NATIVE_LIFECYCLE", "native fresh Reviewer completion is absent")
        if item.get("review_transaction_integrity") is not True:
            if item.get("reviewer_start_order_valid") is False:
                return _fail("REVIEW_START_ORDER_VIOLATION", "review-start was not followed by its exact native Reviewer start")
            if item.get("reviewer_mutation_observed"):
                return _fail("REVIEWER_MUTATION_OBSERVED", "Reviewer mutation invalidated the review transaction")
            return _fail("REVIEW_TRANSACTION_INCOMPLETE", "review-start/review-end candidate transaction is incomplete")
        if item.get("start_candidate_identity") != item.get("end_candidate_identity"):
            return _fail("REVIEW_CANDIDATE_CHANGED", "candidate changed during the review transaction")
        if item.get("verdict") == "EXTERNALLY_INCOMPLETE":
            return _fail("REVIEW_EXTERNAL_INCOMPLETE", "external Reviewer interruption cannot pass")
        if item.get("verdict") not in {"READY", "REQUEST_CHANGES"}:
            return _fail("REVIEW_VERDICT", "unknown Reviewer verdict")
        if item.get("verdict") == "REQUEST_CHANGES" and not any(
            isinstance(edge, dict)
            and edge.get("from_candidate") == item.get("input_candidate_identity")
            and edge.get("finding_id") == item.get("finding_id")
            and edge.get("to_candidate") not in {None, item.get("input_candidate_identity")}
            and isinstance(edge.get("implementer_session"), str)
            for edge in edges
        ):
            return _fail("CORRECTION_EDGE_MISSING", "REQUEST_CHANGES has no observed implementer mutation and verification edge")
    if rounds[-1].get("verdict") != "READY" or rounds[-1].get("input_candidate_identity") != final_candidate:
        return _fail("REVIEW_FINAL_CANDIDATE", "final READY is not bound to the final candidate")
    return {"status": "PASS", "rounds": len(rounds), "sessions": sorted(seen)}


def validate_review_convergence(ledger: dict[str, Any], *, expected_candidate: str | None = None) -> dict[str, Any]:
    """Compatibility entry point using review transaction integrity.

    Older report-shaped rounds that only contain ``fresh`` and
    ``sandbox_mode`` are intentionally not accepted: native read-only is a
    capability diagnostic, while the hard invariant is the host-attested
    unchanged-candidate transaction validated by :func:`validate_review_graph`.
    """
    rounds = ledger.get("review_rounds")
    if not isinstance(rounds, list) or not rounds:
        return _fail("REVIEW_MISSING", "no fresh Reviewer round recorded")
    if any(not isinstance(item, dict) or "start_candidate_identity" not in item for item in rounds):
        return _fail("REVIEW_ROUND_SCHEMA", "legacy report round lacks host transaction facts")
    final = expected_candidate or rounds[-1].get("end_candidate_identity")
    return validate_review_graph(
        {"review_rounds": rounds, "correction_edges": ledger.get("correction_edges", []), "no_progress_cycles": ledger.get("no_progress_cycles", [])},
        final_candidate=final,
    )


def validate_candidate_chain(chain: dict[str, Any]) -> dict[str, Any]:
    if chain.get("formal_collection") is not True:
        return _fail("CANDIDATE_CHAIN_NONFORMAL", "TEST_ONLY or unregistered candidate provenance is diagnostic only")
    review_selected = chain.get("review_selected", True)
    if not isinstance(review_selected, bool):
        return _fail("REVIEW_SELECTION_INVALID", "review selection must be observed")
    fields = ("runtime_candidate", "reviewed_candidate", "verified_candidate", "evaluator_candidate", "sealed_candidate") if review_selected else ("runtime_candidate", "verified_candidate", "evaluator_candidate", "sealed_candidate")
    values = [chain.get(field) for field in fields]
    if any(not isinstance(value, str) or not value for value in values):
        return _fail("CANDIDATE_IDENTITY_MISSING", "candidate identity is missing from the provenance chain")
    computed = chain.get("computed_candidate")
    if computed is not None and (not isinstance(computed, str) or computed != values[0] or any(value != computed for value in values)):
        return _fail("CANDIDATE_IDENTITY_MISMATCH", "a recorded stage differs from the manifest computed from the candidate surface")
    if len(set(values)) != 1:
        return _fail("CANDIDATE_IDENTITY_MISMATCH", "runtime, review, verification, evaluator, and seal identities differ")
    counts = chain.get("stage_counts")
    if isinstance(counts, dict):
        expected_stages = {"runtime-final", "verification-start", "evaluator-start", "seal"}
        review_stages = {"review-start", "review-end"}
        if set(counts) != expected_stages | review_stages or any(counts.get(stage) != 1 for stage in expected_stages) or any(counts.get(stage) != (1 if review_selected else 0) for stage in review_stages):
            return _fail("CANDIDATE_STAGE_DUPLICATE", "candidate provenance stages must each have one host attestation")
    if chain.get("stage_order_valid") is False:
        return _fail("CANDIDATE_STAGE_ORDER", "candidate provenance stages are not causally ordered")
    if chain.get("stage_provenance_complete") is not True:
        return _fail("CANDIDATE_STAGE_PROVENANCE", "every candidate stage requires collector-backed attestation provenance")
    if review_selected and (chain.get("review_verdict_collector_backed") is not True or not isinstance(chain.get("review_verdict_provenance"), dict)):
        return _fail("FINAL_REVIEW_PROVENANCE", "final Reviewer READY lacks collector-backed native provenance")
    if review_selected and chain.get("review_verdict") != "READY":
        return _fail("FINAL_REVIEW_NOT_READY", "the exact sealed candidate lacks final Reviewer READY")
    if chain.get("source_mutations_after_ready"):
        return _fail("FINAL_REVIEW_INVALIDATED", "source mutation occurred after READY")
    return {"status": "PASS", "candidate_identity": values[0], "review_selected": review_selected}


# Historical gpt-5.6 comparison rates only; these never price current gpt-6
# invocations. Current rates require independent provenance before use.
PRICES = {
    "gpt-5.6-luna": (0.20, 0.02, 1.20),
    "gpt-5.6-terra": (2.00, 0.20, 12.00),
    "gpt-5.6-sol": (4.00, 0.40, 20.00),
}

GPT6_STANDARD_SNAPSHOT = json.loads(Path(__file__).with_name("pricing_gpt6_standard_20260930.json").read_text(encoding="utf-8"))


def _tokens(value: Any) -> int | None:
    return value if type(value) is int and value >= 0 else None


def _request_provenance(value: Any) -> bool:
    return (isinstance(value, dict) and value.get("kind") == "codex_rollout"
            and isinstance(value.get("source_file"), str) and bool(value["source_file"])
            and type(value.get("source_line")) is int and value["source_line"] > 0
            and isinstance(value.get("native_event_id"), str) and bool(value["native_event_id"])
            and isinstance(value.get("source_sha256"), str) and re.fullmatch(r"[0-9a-f]{64}", value["source_sha256"]) is not None)


def _gpt6_price(request: dict[str, Any], model: str, pricing_snapshot: dict[str, Any] | None) -> tuple[str, Decimal | None]:
    """Price only complete, source-bound request facts under a matching tier."""
    usage = request.get("usage")
    if not isinstance(usage, dict):
        return "NOT_OBSERVED", None
    fields = ("input", "cached_input", "output")
    if any(field not in usage or usage[field] is None for field in fields):
        return "NOT_OBSERVED", None
    counts = [_tokens(usage[field]) for field in fields]
    if any(value is None for value in counts):
        return "FAIL", None
    input_tokens, cached_tokens, output_tokens = counts
    if cached_tokens > input_tokens:
        return "FAIL", None
    if pricing_snapshot != GPT6_STANDARD_SNAPSHOT:
        return "NOT_OBSERVED", None
    rates = pricing_snapshot["models"].get(model)
    if not isinstance(rates, dict):
        return "NOT_OBSERVED", None
    if (request.get("model") != model or request.get("tier") != "Standard"
        or not isinstance(request.get("request_id"), str) or not request["request_id"]
        or not _request_provenance(request.get("provenance"))):
        return "NOT_OBSERVED", None
    if request.get("cache_write_applies") is True:
        write_tokens = _tokens(usage.get("cache_write"))
        if write_tokens is None or write_tokens > input_tokens - cached_tokens:
            return "FAIL" if usage.get("cache_write") is not None else "NOT_OBSERVED", None
    elif request.get("cache_write_applies") is False:
        write_tokens = 0
        if "cache_write" in usage and usage["cache_write"] != 0:
            return "FAIL", None
    else:
        return "NOT_OBSERVED", None
    prompt_tokens = _tokens(request.get("prompt_tokens"))
    long_context = request.get("long_context")
    if "prompt_tokens" in request and prompt_tokens is None:
        return "FAIL", None
    if prompt_tokens is None or type(long_context) is not bool:
        return "NOT_OBSERVED", None
    if prompt_tokens < input_tokens or long_context != (prompt_tokens > 272000):
        return "FAIL", None
    input_multiplier = 2 if long_context else 1
    output_multiplier = 1.5 if long_context else 1
    usd = (((input_tokens - cached_tokens - write_tokens) * Decimal(str(rates["uncached_input"]))
            + cached_tokens * Decimal(str(rates["cached_input"]))
            + write_tokens * Decimal(str(rates["cache_write"])))
           * input_multiplier + output_tokens * Decimal(str(rates["output"])) * Decimal(str(output_multiplier))) / 1_000_000
    return "PASS", usd


def calculate_cost(sessions: list[dict[str, Any]], *, pricing_snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
    if not sessions:
        return {"status": "NOT_OBSERVED", "usd": None, "by_model": {}, "unpriced_models": []}
    exact_total = Decimal(0)
    by_model: dict[str, dict[str, Any]] = {}
    incomplete: set[str] = set()
    seen_requests: set[str] = set()
    all_historical = True
    for session in sessions:
        if not isinstance(session, dict):
            return _fail("COST_TELEMETRY_INVALID", "session is not an object")
        model = session.get("model")
        usage = session.get("usage") if isinstance(session.get("usage"), dict) else session
        if not isinstance(model, str) or not model or not isinstance(usage, dict):
            return {"status": "NOT_OBSERVED", "usd": None, "by_model": by_model, "unpriced_models": [str(model)] if model else []}
        fields = ("input", "cached_input", "output")
        if any(field not in usage or usage[field] is None for field in fields):
            return {"status": "NOT_OBSERVED", "usd": None, "by_model": by_model, "unpriced_models": [model]}
        counts = [_tokens(usage[field]) for field in fields]
        if any(value is None for value in counts):
            return _fail("COST_TELEMETRY_INVALID", "input/cached_input/output must be nonnegative integer counts")
        input_tokens, cached_tokens, output_tokens = counts
        if cached_tokens > input_tokens:
            return _fail("COST_TELEMETRY_INVALID", "cached input exceeds input")
        uncached = input_tokens - cached_tokens
        item = by_model.setdefault(model, {"input": 0, "cached_input": 0, "output": 0, "usd": 0.0 if model in PRICES or model.startswith("gpt-6-") else None})
        item["input"] += input_tokens
        item["cached_input"] += cached_tokens
        item["output"] += output_tokens
        if model in PRICES:
            uncached_price, cached_price, output_price = PRICES[model]
            cost = uncached / 1_000_000 * uncached_price + cached_tokens / 1_000_000 * cached_price + output_tokens / 1_000_000 * output_price
            item["usd"] += cost
            exact_total += Decimal(uncached) * Decimal(str(uncached_price)) / 1_000_000 + Decimal(cached_tokens) * Decimal(str(cached_price)) / 1_000_000 + Decimal(output_tokens) * Decimal(str(output_price)) / 1_000_000
        else:
            all_historical = False
            if not model.startswith("gpt-6-"):
                incomplete.add(model)
                item["usd"] = None
                continue
            requests = session.get("billing_requests")
            if not isinstance(requests, list) or not requests:
                incomplete.add(model)
                item["usd"] = None
                continue
            request_totals = {"input": 0, "cached_input": 0, "output": 0}
            request_cost = Decimal(0)
            for request in requests:
                if not isinstance(request, dict):
                    incomplete.add(model)
                    break
                result, amount = _gpt6_price(request, model, pricing_snapshot)
                if result == "FAIL":
                    return _fail("COST_TELEMETRY_INVALID", "per-request token or context telemetry is malformed")
                if result != "PASS" or request["request_id"] in seen_requests:
                    incomplete.add(model)
                    break
                seen_requests.add(request["request_id"])
                for field in request_totals:
                    request_totals[field] += request["usage"][field]
                request_cost += amount
            if model in incomplete or request_totals != {"input": input_tokens, "cached_input": cached_tokens, "output": output_tokens}:
                incomplete.add(model)
                item["usd"] = None
                continue
            if item["usd"] is not None:
                item["usd"] += float(request_cost)
            exact_total += request_cost
    if incomplete:
        return {"status": "NOT_OBSERVED", "usd": None, "by_model": by_model, "unpriced_models": sorted(incomplete), "basis": "API-equivalent"}
    return {"status": "PASS", "usd": float(exact_total), "usd_exact": format(exact_total.normalize(), "f"), "by_model": by_model, "basis": "historical-gpt-5.6" if all_historical else "API-equivalent", "actual_allowance_cost": "NOT_OBSERVED"}


def validate_cost_gate(cost: dict[str, Any], *, d6b_ceiling: float = 5.49, d10c_reference: float = 8.79) -> dict[str, Any]:
    if cost.get("status") == "NOT_OBSERVED":
        return {"status": "NOT_OBSERVED", "code": "COST_NOT_OBSERVED", "usd": None, "by_model": cost.get("by_model", {}), "unpriced_models": cost.get("unpriced_models", []), "actual_allowance_cost": "NOT_OBSERVED"}
    if cost.get("status") != "PASS":
        return _fail("COST_TELEMETRY_INVALID", "cost telemetry did not validate")
    usd = cost.get("usd")
    if not isinstance(usd, (int, float)):
        return _fail("COST_NOT_OBSERVED", "observed cost is absent")
    if cost.get("basis") not in {"historical-gpt-5.6", "API-equivalent"}:
        return {"status": "NOT_OBSERVED", "code": "COST_BASIS_NOT_OBSERVED", "usd": None, "actual_allowance_cost": "NOT_OBSERVED"}
    if cost.get("basis") == "API-equivalent":
        return {"status": "PASS", "usd": usd, "usd_exact": cost.get("usd_exact"), "basis": "API-equivalent", "comparison": "NO_COMPARABLE_BASELINE", "actual_allowance_cost": "NOT_OBSERVED"}
    if usd > d6b_ceiling:
        return _fail("COST_D6B_THRESHOLD", f"formal cost {usd} exceeds D6b ceiling {d6b_ceiling}")
    if usd >= d10c_reference:
        return _fail("COST_D10C_NOT_BEATEN", f"formal cost {usd} does not beat D10c reference {d10c_reference}")
    return {"status": "PASS", "usd": usd, "usd_exact": cost.get("usd_exact"), "basis": "historical-gpt-5.6", "d6b_ceiling": d6b_ceiling, "d10c_reference": d10c_reference, "actual_allowance_cost": "NOT_OBSERVED"}


def validate_raw_usage(sessions: Any) -> dict[str, Any]:
    if not isinstance(sessions, list) or not sessions:
        return {"status": "NOT_OBSERVED", "code": "USAGE_NOT_OBSERVED"}
    for session in sessions:
        if not isinstance(session, dict):
            return _fail("USAGE_TELEMETRY_INVALID", "session is not an object")
        usage = session.get("usage") if isinstance(session.get("usage"), dict) else session
        fields = ("input", "cached_input", "output")
        if any(field not in usage or usage[field] is None for field in fields):
            return {"status": "NOT_OBSERVED", "code": "USAGE_NOT_OBSERVED"}
        counts = [_tokens(usage[field]) for field in fields]
        if any(value is None for value in counts) or counts[1] > counts[0]:
            return _fail("USAGE_TELEMETRY_INVALID", "session token counts are invalid")
    return {"status": "PASS", "sessions": len(sessions)}


def validate_fast_path(report: dict[str, Any]) -> dict[str, Any]:
    if report.get("evidence_required") != "NOT_REQUIRED":
        return _fail("FAST_PATH_EVIDENCE", "simple task did not declare evidence not required")
    if report.get("sessions") != ["implementer"]:
        return _fail("FAST_PATH_ROUTING", "simple task used roles beyond one Implementer")
    if report.get("quality") != "PASS":
        return _fail("FAST_PATH_QUALITY", "simple task quality did not pass")
    return {"status": "PASS", "sessions": report["sessions"], "evidence_required": "NOT_REQUIRED"}


def validate_documentation(*, protocol_path: Path, generated_text: str, tests_passed: bool, runtime_consistency: bool) -> dict[str, Any]:
    """Validate benchmark documentation without constraining production text."""
    del generated_text, tests_passed, runtime_consistency
    if not protocol_path.is_file():
        return _fail("DOCUMENTATION_MISSING", str(protocol_path))
    if not protocol_path.read_text(encoding="utf-8").strip():
        return _fail("DOCUMENTATION_EMPTY", "benchmark protocol is empty")
    digest = hashlib.sha256(protocol_path.read_bytes()).hexdigest()
    return {"status": "PASS", "protocol_sha256": digest}


def validate_report(report: dict[str, Any], *, protocol_path: Path, generated_text: str) -> dict[str, Any]:
    # Only a collector-produced ledger is admissible here.  The historical
    # declaration-shaped report is intentionally rejected closed.
    collected = report.get("collector")
    if not isinstance(collected, dict):
        return {"status": "FAIL", "checks": {"collector": _fail("COLLECTOR_REQUIRED", "validator accepts only collector-produced facts")}}
    formal_parts = (collected.get("evidence"), collected.get("candidate_chain"), collected.get("reviews"))
    if any(not isinstance(part, dict) or part.get("formal_collection") is not True for part in formal_parts):
        return {"status": "FAIL", "checks": {"collector": _fail("COLLECTOR_NONFORMAL", "formal collection rejects TEST_ONLY or unregistered diagnostic streams")}}
    checks = {
        "evidence_protocol": validate_collected_evidence(collected.get("evidence", {})),
        "candidate_provenance": validate_candidate_chain(collected.get("candidate_chain", {})),
        "usage": validate_raw_usage(collected.get("sessions")),
        "cost": validate_cost_gate(calculate_cost(collected.get("sessions", []), pricing_snapshot=collected.get("pricing_snapshot"))),
        "documentation": validate_documentation(
            protocol_path=protocol_path,
            generated_text=generated_text,
            tests_passed=None,
            runtime_consistency=None,
        ),
    }
    expected_candidate = checks["candidate_provenance"].get("candidate_identity")
    checks["review_convergence"] = validate_review_graph(collected.get("reviews", {}), final_candidate=expected_candidate, required=checks["candidate_provenance"].get("review_selected", True)) if isinstance(expected_candidate, str) else _fail("REVIEW_FINAL_CANDIDATE", "candidate identity is not collector-backed")
    statuses = {item.get("status") for key, item in checks.items() if key not in {"usage", "cost"}}
    status = "PASS" if statuses == {"PASS"} else "NOT_OBSERVED" if "NOT_OBSERVED" in statuses and "FAIL" not in statuses else "FAIL"
    return {"status": status, "checks": checks}


_OBSERVATION_SEAL = object()


class VerifiedObservation:
    """An in-memory, host-issued observation bound to fact and source bytes."""
    __slots__ = ("issuer", "source_digest", "subject_digest", "_seal")

    def __init__(self, issuer: str, source_digest: str, subject_digest: str, seal: object) -> None:
        self.issuer = issuer
        self.source_digest = source_digest
        self.subject_digest = subject_digest
        self._seal = seal


class _TestObservationWriter:
    """Private fixture writer; formal validation has no observation issuer."""
    def __init__(self, issuer: str = "host-collector") -> None:
        self.issuer = issuer

    def observe(self, value: dict[str, Any], *, source_bytes: bytes) -> VerifiedObservation:
        payload = {key: item for key, item in value.items() if key not in {"identity", "observation"}}
        return VerifiedObservation(
            self.issuer,
            hashlib.sha256(source_bytes).hexdigest(),
            hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
            _OBSERVATION_SEAL,
        )


def _valid_observation(value: dict[str, Any]) -> bool:
    observation = value.get("observation")
    if not isinstance(observation, VerifiedObservation) or observation._seal is not _OBSERVATION_SEAL:
        return False
    if not observation.issuer or not observation.source_digest:
        return False
    payload = {key: item for key, item in value.items() if key not in {"identity", "observation"}}
    return observation.subject_digest == hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _observed_status(value: Any, *, name: str) -> dict[str, Any]:
    if isinstance(value, dict) and value.get("status") in {"PASS", "FAIL", "NOT_OBSERVED", "EXTERNALLY_INCOMPLETE"}:
        # A status string is not an attestation.  Only a non-empty structured
        # producer identity, provenance record, or independently computed
        # check/manifest can enter the target gate.  Arbitrary fact_source
        # strings and empty provenance are declarations.
        structured = any(
            isinstance(value.get(key), dict) and bool(value[key])
            for key in ("fact_source", "collector", "provenance", "checks", "manifest")
        )
        # A nested object or arbitrary identity string is still model-owned
        # input.  Accept only known host/collector producer kinds, and when an
        # identity is supplied require it to be the content hash of the fact
        # payload (the host producers in d11_preflight use this convention).
        fact_source = value.get("fact_source")
        allowed_kinds = {
            "host_preflight", "host_smoke_probe", "trusted_thaliris_audit",
            "native_codex_rollout", "host_runtime_probe", "native_capability_diagnostic",
            "collector",
        }
        source_kind = fact_source.get("kind") if isinstance(fact_source, dict) else None
        source_ok = isinstance(source_kind, str) and source_kind in allowed_kinds
        identity_value = value.get("identity")
        identity = isinstance(identity_value, str) and bool(identity_value)
        if identity:
            payload = {key: item for key, item in value.items() if key not in {"identity", "observation"}}
            expected = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            if identity_value != expected:
                return {"status": "NOT_OBSERVED", "code": f"{name.upper()}_IDENTITY_INVALID"}
        if not structured or not source_ok or (identity_value is not None and not identity):
            return {"status": "NOT_OBSERVED", "code": f"{name.upper()}_PROVENANCE_NOT_OBSERVED"}
        # A fact source allowlist and self-hash merely describe caller data.
        # Passing requires an independent, host-owned observation bound to the
        # bytes that yielded this status.  JSON/sidecar copies cannot recreate
        # this in-memory capability.
        if not _valid_observation(value):
            return {"status": "NOT_OBSERVED", "code": f"{name.upper()}_OBSERVATION_NOT_OBSERVED"}
        if source_kind != "native_capability_diagnostic" and not identity:
            return {"status": "NOT_OBSERVED", "code": f"{name.upper()}_IDENTITY_NOT_OBSERVED"}
        return value
    if isinstance(value, bool):
        return {"status": "NOT_OBSERVED", "code": f"{name.upper()}_DECLARATION_REJECTED"}
    return {"status": "NOT_OBSERVED", "code": f"{name.upper()}_NOT_OBSERVED"}


def validate_target(
    collected: dict[str, Any],
    *,
    preflight: dict[str, Any] | None = None,
    smoke: dict[str, Any] | None = None,
    freeze_pre: Any = None,
    freeze_post: Any = None,
    tests: dict[str, Any] | None = None,
    fast_path: dict[str, Any] | None = None,
    protocol_path: Path | None = None,
    generated_text: str | None = None,
) -> dict[str, Any]:
    """Mechanical final gate over collector/harness facts only."""
    if not isinstance(collected, dict):
        return {"status": "NOT_OBSERVED", "code": "COLLECTOR_NOT_OBSERVED"}
    checks: dict[str, dict[str, Any]] = {}
    checks["preflight"] = _observed_status(preflight, name="preflight")
    checks["smoke"] = _observed_status(smoke, name="smoke")
    checks["freeze_pre"] = _observed_status(freeze_pre, name="freeze_pre")
    checks["freeze_post"] = _observed_status(freeze_post, name="freeze_post")
    checks["controller_boundary"] = _observed_status(collected.get("controller_boundary"), name="controller_boundary")
    checks["trusted_runtime"] = _observed_status(collected.get("trusted_runtime"), name="trusted_runtime")
    checks["routing"] = _observed_status(collected.get("routing"), name="routing")
    evidence = collected.get("evidence")
    checks["evidence_protocol"] = validate_collected_evidence(evidence) if isinstance(evidence, dict) else _observed_status(None, name="evidence_protocol")
    checks["evidence_source_provenance"] = _observed_status(collected.get("evidence_source_provenance"), name="evidence_source_provenance")
    checks["evidence_consumption"] = _observed_status(collected.get("evidence_consumption"), name="evidence_consumption")
    checks["supersession"] = _observed_status(collected.get("supersession"), name="supersession")
    chain = collected.get("candidate_chain")
    chain_check = validate_candidate_chain(chain) if isinstance(chain, dict) else _observed_status(None, name="candidate_chain")
    checks["candidate_chain"] = chain_check
    final_candidate = chain_check.get("candidate_identity") if chain_check.get("status") == "PASS" else None
    reviews = collected.get("reviews")
    review_check = validate_review_graph(reviews, final_candidate=final_candidate, required=chain_check.get("review_selected", True)) if isinstance(reviews, dict) and isinstance(final_candidate, str) else _observed_status(None, name="review_graph")
    checks["review_graph"] = review_check
    checks["review_transaction_integrity"] = review_check
    # Native sandbox support is a host capability diagnostic.  The hard
    # correctness gate is the unchanged-candidate review transaction above.
    checks["reviewer_native_readonly"] = _observed_status(collected.get("reviewer_native_readonly"), name="reviewer_native_readonly") if collected.get("reviewer_native_readonly") is not None else {"status": "UNSUPPORTED_BY_HOST", "fact_source": {"kind": "native_capability_diagnostic"}}
    checks["evaluator_calibration"] = _observed_status(collected.get("evaluator_calibration"), name="evaluator_calibration")
    checks["final_evaluator"] = _observed_status(collected.get("final_evaluator"), name="final_evaluator")
    checks["documentation_consistency"] = validate_documentation(protocol_path=protocol_path, generated_text=generated_text or "", tests_passed=None, runtime_consistency=None) if protocol_path is not None else _observed_status(None, name="documentation_consistency")
    checks["tests"] = _observed_status(tests, name="tests")
    checks["usage"] = validate_raw_usage(collected.get("sessions"))
    checks["cost"] = validate_cost_gate(calculate_cost(collected.get("sessions", []), pricing_snapshot=collected.get("pricing_snapshot"))) if isinstance(collected.get("sessions"), list) else _observed_status(None, name="cost")
    if isinstance(fast_path, dict):
        checks["fast_path"] = validate_fast_path(fast_path)
    statuses = {item.get("status") for key, item in checks.items() if key not in {"reviewer_native_readonly", "usage", "cost"}}
    status = "PASS" if statuses == {"PASS"} else ("FAIL" if "FAIL" in statuses else "NOT_OBSERVED")
    return {"status": status, "checks": checks}


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--generated", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    generated = args.generated.read_text(encoding="utf-8")
    result = validate_report(report, protocol_path=args.protocol, generated_text=generated)
    if args.output:
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
