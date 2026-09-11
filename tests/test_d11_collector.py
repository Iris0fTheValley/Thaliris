import importlib.util
from pathlib import Path
import subprocess
import sys

from thaliris import core


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "benchmarks" / "abcd"))
for name in ("candidate_manifest", "d11_collector", "d11_protocol", "trusted_surface", "d11_preflight"):
    spec = importlib.util.spec_from_file_location(name, ROOT / "benchmarks" / "abcd" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    globals()[name] = module


def repo(path: Path) -> Path:
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    return path


def test_collector_derives_artifact_identity_order_and_consumer(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.init(root)
    evidence = root / "evidence.md"
    evidence.write_text("confirmed fact\n", encoding="utf-8")
    started = core.task_start(root, "collector", None, None)
    registered = core.task_artifact(root, started["revision"], "evidence-1", "evidence.md", "bounded fact", producer_role="investigator")
    sha = registered["revision"]  # revision is deliberately not a content identity
    actual = __import__("hashlib").sha256(evidence.read_bytes()).hexdigest()
    facts = d11_collector.collect_evidence(root, [
        {"event": "artifact_produced", "sequence": 1, "artifact_id": "evidence-1"},
        {"event": "artifact_registered", "sequence": 2, "artifact_id": "evidence-1"},
        {"event": "role_dispatch", "sequence": 3, "role": "reasoning-specialist", "artifact_ids": ["evidence-1"], "content_sha256": actual},
    ])
    assert facts["artifacts"][0]["declared_sha256"] == actual
    assert facts["artifacts"][0]["bytes_match"] is True
    assert d11_protocol.validate_collected_evidence(facts)["status"] == "PASS"
    assert sha != actual


def test_collector_does_not_accept_report_booleans_or_unproven_consumption(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.init(root)
    (root / "evidence.md").write_text("fact", encoding="utf-8")
    started = core.task_start(root, "collector", None, None)
    core.task_artifact(root, started["revision"], "evidence-1", "evidence.md", "bounded fact", producer_role="investigator")
    facts = d11_collector.collect_evidence(root, [{"event": "artifact_produced", "sequence": 1, "artifact_id": "evidence-1"}])
    facts["produced_before_decision"] = True
    assert d11_protocol.validate_collected_evidence(facts)["code"] == "EVIDENCE_ORDERING"


def test_review_graph_binds_each_round_to_its_own_candidate_and_native_session() -> None:
    facts = d11_collector.collect_review_graph([
        {"event": "SubagentStart", "sequence": 1, "role": "reviewer", "session_id": "review-a"},
        {"event": "review_verdict", "sequence": 2, "session_id": "review-a", "candidate_identity": "candidate-a", "verdict": "REQUEST_CHANGES", "finding_id": "F-1", "classification": "LOCAL_SEMANTIC", "native_sandbox_mode": "read-only"},
        {"event": "implementer_dispatch", "sequence": 3, "session_id": "implementer-a", "candidate_from": "candidate-a", "finding_id": "F-1"},
        {"event": "source_mutation", "sequence": 4, "session_id": "implementer-a", "candidate_identity": "candidate-b"},
        {"event": "deterministic_verification", "sequence": 5, "candidate_identity": "candidate-b", "outcome": "PASSED"},
        {"event": "SubagentStart", "sequence": 6, "role": "reviewer", "session_id": "review-b"},
        {"event": "review_verdict", "sequence": 7, "session_id": "review-b", "candidate_identity": "candidate-b", "verdict": "READY", "native_sandbox_mode": "read-only"},
    ])
    assert d11_protocol.validate_review_graph(facts, final_candidate="candidate-b")["status"] == "PASS"
    facts["review_rounds"][0]["reviewer_session"] = "review-b"
    assert d11_protocol.validate_review_graph(facts, final_candidate="candidate-b")["code"] == "REVIEW_SESSION_REUSE"


def test_candidate_manifest_is_reproducible_and_excludes_runtime_state(tmp_path: Path) -> None:
    root = repo(tmp_path)
    (root / "src").mkdir()
    (root / "src" / "product.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / ".context").mkdir()
    (root / ".context" / "state.json").write_text("volatile", encoding="utf-8")
    first = candidate_manifest.build_manifest(root)
    second = candidate_manifest.build_manifest(root)
    assert first["identity"] == second["identity"]
    assert all(not item["path"].startswith(".context/") for item in first["manifest"]["files"])
    (root / "src" / "product.py").write_text("VALUE = 2\n", encoding="utf-8")
    assert candidate_manifest.candidate_identity(root) != first["identity"]


def test_trusted_infrastructure_identity_detects_post_freeze_mutation(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime.cmd"
    runtime.write_bytes(b"trusted-v1")
    frozen = trusted_surface.identity([runtime])
    assert trusted_surface.verify(frozen, [runtime]) is True
    runtime.write_bytes(b"candidate-overwrite")
    assert trusted_surface.verify(frozen, [runtime]) is False


def test_candidate_chain_is_bound_to_computed_manifest(tmp_path: Path) -> None:
    root = repo(tmp_path)
    source = root / "product.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    identity = candidate_manifest.candidate_identity(root)
    events = [
        {"event": "candidate_produced", "sequence": 1, "candidate_identity": identity},
        {"event": "review_verdict", "sequence": 2, "verdict": "READY", "candidate_identity": identity},
        {"event": "deterministic_verification", "sequence": 3, "outcome": "PASSED", "candidate_identity": identity},
        {"event": "evaluator_result", "sequence": 4, "candidate_identity": identity},
        {"event": "candidate_sealed", "sequence": 5, "candidate_identity": identity},
    ]
    chain = d11_collector.collect_candidate_chain(root, events)
    assert d11_protocol.validate_candidate_chain(chain)["status"] == "PASS"
    source.write_text("VALUE = 2\n", encoding="utf-8")
    assert d11_protocol.validate_candidate_chain(d11_collector.collect_candidate_chain(root, events))["code"] == "CANDIDATE_IDENTITY_MISMATCH"


def test_preflight_is_fail_closed_without_clean_fixture_and_calibration(tmp_path: Path) -> None:
    root = repo(tmp_path)
    (root / "dirty.py").write_text("dirty", encoding="utf-8")
    result = d11_preflight.run_preflight(
        root,
        expected_adapter_sha="0" * 40,
        harness_paths=[root / "missing-harness.py"],
        evaluator_path=root / "missing-evaluator.py",
    )
    assert result["status"] == "PREFLIGHT_FAIL"
    assert result["checks"]["adapter_sha"]["pass"] is False
    assert result["checks"]["benchmark_harness"]["pass"] is False
    assert result["checks"]["gold"]["pass"] is False


def test_run_manifest_cannot_be_frozen_from_failed_preflight() -> None:
    try:
        d11_preflight.freeze_run_manifest({"status": "PREFLIGHT_FAIL"}, task_spec_identity="task", base_identity="base", gold_identity="gold", pricing_snapshot={})
    except ValueError as exc:
        assert "failed preflight" in str(exc)
    else:
        raise AssertionError("failed preflight was frozen")
