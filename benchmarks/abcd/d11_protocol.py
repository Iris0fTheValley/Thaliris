"""Deterministic D11 benchmark protocol gates.

The module consumes a compact ledger emitted by a benchmark driver.  It does
not inspect rollout prose, infer success from prompts, or run agents.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


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
        if item.get("bytes_match") is not True:
            return _fail("EVIDENCE_CONTENT_IDENTITY", "registered artifact bytes do not match Core identity")
        if not item.get("produced_before_registration") or not item.get("registered_before_dispatch"):
            return _fail("EVIDENCE_ORDERING", "production, registration, and dispatch ordering was not observed")
        if not item.get("used") or not item.get("carried_content_identity"):
            return _fail("EVIDENCE_ARTIFACT_UNUSED", "registered evidence has no provenance-backed downstream consumer")
    return {"status": "PASS", "required": "REQUIRED", "produced": len(artifacts), "consumed": sum(len(item.get("consumer_roles", [])) for item in artifacts)}


def validate_review_graph(ledger: dict[str, Any], *, final_candidate: str) -> dict[str, Any]:
    """Validate fresh native Reviewer sessions against their own candidates."""
    rounds = ledger.get("review_rounds")
    if not isinstance(rounds, list) or not rounds:
        return _fail("REVIEW_MISSING", "collector observed no review verdict")
    seen: set[str] = set()
    edges = ledger.get("correction_edges", [])
    if not isinstance(edges, list):
        return _fail("CORRECTION_EDGE_SCHEMA", "collector correction edges are malformed")
    for item in rounds:
        if not isinstance(item, dict):
            return _fail("REVIEW_COLLECTOR_SCHEMA", "review fact is not an object")
        session = item.get("reviewer_session")
        if not isinstance(session, str) or not session or session in seen:
            return _fail("REVIEW_SESSION_REUSE", "reviewer session identity is missing or reused")
        seen.add(session)
        if item.get("native_session") is not True or item.get("sandbox_mode") != "read-only":
            return _fail("REVIEW_NOT_NATIVE_READ_ONLY", "native fresh read-only evidence is absent")
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
    rounds = ledger.get("review_rounds")
    if not isinstance(rounds, list) or not rounds:
        return _fail("REVIEW_MISSING", "no fresh Reviewer round recorded")
    corrections = 0
    for item in rounds:
        if not isinstance(item, dict) or set(item) != {"reviewer_session", "candidate_identity", "verdict", "packet", "fresh", "sandbox_mode"}:
            return _fail("REVIEW_ROUND_SCHEMA", "review round is incomplete")
        if item["fresh"] is not True or item["sandbox_mode"] != "read-only":
            return _fail("REVIEW_NOT_FRESH_READ_ONLY", "Reviewer round was not fresh and native read-only")
        if not isinstance(item["reviewer_session"], str) or not item["reviewer_session"]:
            return _fail("REVIEW_IDENTITY", "Reviewer session identity missing")
        if expected_candidate is not None and item["candidate_identity"] != expected_candidate:
            return _fail("REVIEW_CANDIDATE_MISMATCH", "a Reviewer round inspected a different candidate")
        if item["verdict"] == "READY":
            if item["packet"] is not None:
                return _fail("REVIEW_READY_PACKET", "READY must not carry a correction packet")
            continue
        packet = item["packet"]
        if item["verdict"] != "REQUEST_CHANGES" or not isinstance(packet, dict) or set(packet) != {"finding_id", "classification", "affected_surface", "violated_invariant", "verification_requirement"}:
            return _fail("REVIEW_PACKET_SCHEMA", "non-READY review lacks a bounded Review Packet")
        if packet["classification"] not in CLASSIFICATIONS:
            return _fail("REVIEW_CLASSIFICATION", "unknown review finding classification")
        if packet["classification"] in {"MECHANICAL", "LOCAL_SEMANTIC"}:
            corrections += 1
    if rounds[-1]["verdict"] != "READY":
        return _fail("REVIEW_NOT_READY", "final fresh Reviewer did not return READY")
    return {"status": "PASS", "rounds": len(rounds), "corrections": corrections}


def validate_candidate_chain(chain: dict[str, Any]) -> dict[str, Any]:
    fields = ("runtime_candidate", "reviewed_candidate", "verified_candidate", "evaluator_candidate", "sealed_candidate")
    values = [chain.get(field) for field in fields]
    if any(not isinstance(value, str) or not value for value in values):
        return _fail("CANDIDATE_IDENTITY_MISSING", "candidate identity is missing from the provenance chain")
    computed = chain.get("computed_candidate")
    if computed is not None and (not isinstance(computed, str) or computed != values[0] or any(value != computed for value in values)):
        return _fail("CANDIDATE_IDENTITY_MISMATCH", "a recorded stage differs from the manifest computed from the candidate surface")
    if len(set(values)) != 1:
        return _fail("CANDIDATE_IDENTITY_MISMATCH", "runtime, review, verification, evaluator, and seal identities differ")
    if chain.get("review_verdict") != "READY":
        return _fail("FINAL_REVIEW_NOT_READY", "the exact sealed candidate lacks final Reviewer READY")
    if chain.get("source_mutations_after_ready"):
        return _fail("FINAL_REVIEW_INVALIDATED", "source mutation occurred after READY")
    return {"status": "PASS", "candidate_identity": values[0]}


PRICES = {
    "gpt-5.6-luna": (0.20, 0.02, 1.20),
    "gpt-5.6-terra": (2.00, 0.20, 12.00),
    "gpt-5.6-sol": (4.00, 0.40, 20.00),
}


def calculate_cost(sessions: list[dict[str, Any]]) -> dict[str, Any]:
    total = 0.0
    by_model: dict[str, dict[str, float]] = {}
    for session in sessions:
        model = session.get("model")
        usage = session.get("usage")
        if model not in PRICES or not isinstance(usage, dict):
            return _fail("COST_TELEMETRY_INVALID", "model or usage is absent")
        try:
            input_tokens = int(usage["input"])
            cached_tokens = int(usage["cached_input"])
            output_tokens = int(usage["output"])
        except (KeyError, TypeError, ValueError):
            return _fail("COST_TELEMETRY_INVALID", "input/cached_input/output are required")
        if not 0 <= cached_tokens <= input_tokens:
            return _fail("COST_TELEMETRY_INVALID", "cached input exceeds input")
        uncached = input_tokens - cached_tokens
        uncached_price, cached_price, output_price = PRICES[model]
        cost = uncached / 1_000_000 * uncached_price + cached_tokens / 1_000_000 * cached_price + output_tokens / 1_000_000 * output_price
        item = by_model.setdefault(model, {"input": 0, "cached_input": 0, "output": 0, "usd": 0.0})
        item["input"] += input_tokens
        item["cached_input"] += cached_tokens
        item["output"] += output_tokens
        item["usd"] += cost
        total += cost
    return {"status": "PASS", "usd": round(total, 6), "by_model": by_model}


def validate_cost_gate(cost: dict[str, Any], *, d6b_ceiling: float = 5.49, d10c_reference: float = 8.79) -> dict[str, Any]:
    if cost.get("status") != "PASS":
        return _fail("COST_TELEMETRY_INVALID", "cost telemetry did not validate")
    usd = cost.get("usd")
    if not isinstance(usd, (int, float)):
        return _fail("COST_NOT_OBSERVED", "observed cost is absent")
    if usd > d6b_ceiling:
        return _fail("COST_D6B_THRESHOLD", f"formal cost {usd} exceeds D6b ceiling {d6b_ceiling}")
    if usd >= d10c_reference:
        return _fail("COST_D10C_NOT_BEATEN", f"formal cost {usd} does not beat D10c reference {d10c_reference}")
    return {"status": "PASS", "usd": usd, "d6b_ceiling": d6b_ceiling, "d10c_reference": d10c_reference}


def validate_fast_path(report: dict[str, Any]) -> dict[str, Any]:
    if report.get("evidence_required") != "NOT_REQUIRED":
        return _fail("FAST_PATH_EVIDENCE", "simple task did not declare evidence not required")
    if report.get("sessions") != ["implementer"]:
        return _fail("FAST_PATH_ROUTING", "simple task used roles beyond one Implementer")
    if report.get("escalation_reason") is not None:
        return _fail("FAST_PATH_ESCALATED", "simple task escalated without a recorded reason")
    if report.get("quality") != "PASS":
        return _fail("FAST_PATH_QUALITY", "simple task quality did not pass")
    return {"status": "PASS", "sessions": report["sessions"], "evidence_required": "NOT_REQUIRED"}


def validate_documentation(*, protocol_path: Path, generated_text: str, tests_passed: bool, runtime_consistency: bool) -> dict[str, Any]:
    if not protocol_path.is_file():
        return _fail("DOCUMENTATION_MISSING", str(protocol_path))
    routing = protocol_path.parent / "thaliris-routing-protocol.md"
    if not routing.is_file() or "docs/thaliris-routing-protocol.md" not in generated_text:
        return _fail("DOCUMENTATION_DEAD_TEXT", "generated role-pack does not reference authoritative product protocol")
    if "docs/thaliris-routing-protocol.md" not in protocol_path.read_text(encoding="utf-8"):
        return _fail("DOCUMENTATION_RUNTIME_DRIFT", "benchmark protocol does not reference product protocol")
    digest = hashlib.sha256(protocol_path.read_bytes()).hexdigest()
    return {"status": "PASS", "protocol_sha256": digest}


def validate_report(report: dict[str, Any], *, protocol_path: Path, generated_text: str) -> dict[str, Any]:
    # Only a collector-produced ledger is admissible here.  The historical
    # declaration-shaped report is intentionally rejected closed.
    collected = report.get("collector")
    if not isinstance(collected, dict):
        return {"status": "FAIL", "checks": {"collector": _fail("COLLECTOR_REQUIRED", "validator accepts only collector-produced facts")}}
    checks = {
        "evidence_protocol": validate_collected_evidence(collected.get("evidence", {})),
        "candidate_provenance": validate_candidate_chain(collected.get("candidate_chain", {})),
        "cost": validate_cost_gate(calculate_cost(collected.get("sessions", []))),
        "documentation": validate_documentation(
            protocol_path=protocol_path,
            generated_text=generated_text,
            tests_passed=None,
            runtime_consistency=None,
        ),
    }
    expected_candidate = checks["candidate_provenance"].get("candidate_identity")
    checks["review_convergence"] = validate_review_graph(collected.get("reviews", {}), final_candidate=expected_candidate) if isinstance(expected_candidate, str) else _fail("REVIEW_FINAL_CANDIDATE", "candidate identity is not collector-backed")
    status = "PASS" if all(item.get("status") == "PASS" for item in checks.values()) else "FAIL"
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
