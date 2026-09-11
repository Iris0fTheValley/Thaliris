import importlib.util
from pathlib import Path

from thaliris.codex_adapter import ROLE_PACKS
_PROTOCOL = Path(__file__).parents[1] / "benchmarks" / "abcd" / "d11_protocol.py"
_SPEC = importlib.util.spec_from_file_location("d11_protocol", _PROTOCOL)
assert _SPEC and _SPEC.loader
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
calculate_cost = _MODULE.calculate_cost
validate_candidate_chain = _MODULE.validate_candidate_chain
validate_documentation = _MODULE.validate_documentation
validate_evidence = _MODULE.validate_evidence
validate_fast_path = _MODULE.validate_fast_path
validate_review_convergence = _MODULE.validate_review_convergence


def artifact(*, superseded_by=None):
    return {
        "id": "evidence-1",
        "producer_role": "investigator",
        "task_id": "task-1",
        "revision": 2,
        "path": "artifacts/evidence.md",
        "content_sha256": "0" * 64,
        "source_refs": ["src-1"],
        "affected_surface": ["src/a.py"],
        "confirmed_facts": ["fact"],
        "inferences": [],
        "unknowns": [],
        "contradictions": [],
        "verification": ["test-1"],
        "produced_before_decision": True,
        "registered": {"by": "controller", "before_decision": True},
        "selected": [{"role": "reasoning-specialist", "facts": ["fact"]}],
        "consumed_by": [{"role": "reasoning-specialist", "purpose": "choose implementation"}],
        "superseded_by": superseded_by,
    }


def test_evidence_lifecycle_requires_registration_selection_and_consumption():
    result = validate_evidence({"evidence_required": "REQUIRED", "artifacts": [artifact()]})
    assert result["status"] == "PASS" and result["consumed"] == 1
    unused = artifact(); unused["consumed_by"] = []
    assert validate_evidence({"evidence_required": "REQUIRED", "artifacts": [unused]})["code"] == "EVIDENCE_ARTIFACT_UNUSED"


def test_evidence_supersession_and_fast_path():
    old = artifact(superseded_by="evidence-2")
    new = artifact(); new["id"] = "evidence-2"; new["superseded_by"] = None
    assert validate_evidence({"evidence_required": "REQUIRED", "artifacts": [old, new], "active_artifacts": ["evidence-2"]})["status"] == "PASS"
    assert validate_evidence({"evidence_required": "NOT_REQUIRED", "artifacts": []})["status"] == "PASS"


def test_task_local_scratch_artifact_is_repo_relative():
    item = artifact()
    item["path"] = ".scratch/evidence.md"
    assert validate_evidence({"evidence_required": "REQUIRED", "artifacts": [item]})["status"] == "PASS"


def test_review_convergence_requires_fresh_read_only_final_ready():
    ready = {"reviewer_session": "r2", "candidate_identity": "c1", "verdict": "READY", "packet": None, "fresh": True, "sandbox_mode": "read-only"}
    assert validate_review_convergence({"review_rounds": [ready]})["status"] == "PASS"
    assert validate_review_convergence({"review_rounds": [{**ready, "verdict": "EXTERNALLY_INCOMPLETE"}]})["code"] == "REVIEW_PACKET_SCHEMA"
    assert validate_review_convergence({"review_rounds": [ready]}, expected_candidate="other") ["code"] == "REVIEW_CANDIDATE_MISMATCH"


def test_candidate_chain_and_cost_are_fail_closed():
    chain = {key: "c1" for key in ("runtime_candidate", "reviewed_candidate", "verified_candidate", "evaluator_candidate", "sealed_candidate")}
    chain["review_verdict"] = "READY"; chain["source_mutations_after_ready"] = False
    assert validate_candidate_chain(chain)["status"] == "PASS"
    assert validate_candidate_chain({**chain, "sealed_candidate": "c2"})["code"] == "CANDIDATE_IDENTITY_MISMATCH"
    cost = calculate_cost([{"model": "gpt-5.6-terra", "usage": {"input": 2_000_000, "cached_input": 1_000_000, "output": 1_000_000}}])
    assert cost["status"] == "PASS" and cost["usd"] == 14.2


def test_fast_path_and_documentation_gate():
    assert validate_fast_path({"evidence_required": "NOT_REQUIRED", "sessions": ["implementer"], "escalation_reason": None, "quality": "PASS"})["status"] == "PASS"
    root = Path(__file__).parents[1]
    result = validate_documentation(protocol_path=root / "docs" / "thaliris-benchmark-protocol.md", generated_text=ROLE_PACKS, tests_passed=True, runtime_consistency=True)
    assert result["status"] == "PASS"


def test_target_gate_rejects_model_declared_boolean_facts():
    protocol = _MODULE.validate_target({}, preflight=True, smoke=True, freeze_pre=True, freeze_post=True)
    assert protocol["status"] == "NOT_OBSERVED"
    assert protocol["checks"]["preflight"]["code"] == "PREFLIGHT_DECLARATION_REJECTED"


def test_target_gate_rejects_fake_or_empty_provenance_statuses():
    observed = _MODULE._observed_status
    assert observed({"status": "PASS", "fact_source": "made-up"}, name="x")["status"] == "NOT_OBSERVED"
    assert observed({"status": "PASS", "provenance": {}}, name="x")["status"] == "NOT_OBSERVED"
    assert observed({"status": "PASS", "checks": {}}, name="x")["status"] == "NOT_OBSERVED"
    assert observed({"status": "PASS", "manifest": {}}, name="x")["status"] == "NOT_OBSERVED"
