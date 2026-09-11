import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import pytest

from thaliris import core
from thaliris.protocol import ROUTING_PROTOCOL_MARKER


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "benchmarks" / "abcd"))
for name in ("candidate_manifest", "d11_sources", "d11_collector", "d11_protocol", "trusted_surface", "d11_preflight"):
    spec = importlib.util.spec_from_file_location(name, ROOT / "benchmarks" / "abcd" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    globals()[name] = module


def repo(path: Path) -> Path:
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    return path


def trusted_events(tmp_path: Path, events: list[dict]) -> list[dict]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    stream = tmp_path / "trusted-events.jsonl"
    stream.write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")
    return d11_collector.load_test_events([{"kind": "harness_attestation", "path": stream}])


def evidence_envelope(task_id: str, revision: int, artifact_id: str) -> str:
    return json.dumps({
        "artifact_id": artifact_id,
        "task_id": task_id,
        "task_revision": revision,
        "source_refs": ["src-1"],
        "affected_surface": ["src/product.py"],
        "confirmed_facts": [{"text": "the current source has a stable entrypoint", "source_refs": ["src-1"]}],
        "inferences": [],
        "unknowns": [],
        "contradictions": [],
        "verification": [{"description": "targeted inspection", "source_refs": ["src-1"]}],
    }, separators=(",", ":"))


def test_collector_derives_artifact_identity_order_and_consumer(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.init(root)
    evidence = root / "evidence.md"
    started = core.task_start(root, "collector", None, None)
    task_id = core.task_show(root)["state"]["task_id"]
    evidence.write_text(evidence_envelope(task_id, started["revision"] + 1, "evidence-1"), encoding="utf-8")
    registered = core.task_artifact(root, started["revision"], "evidence-1", "evidence.md", "bounded fact", producer_role="investigator")
    sha = registered["revision"]  # revision is deliberately not a content identity
    actual = __import__("hashlib").sha256(evidence.read_bytes()).hexdigest()
    facts = d11_collector.collect_evidence(root, trusted_events(tmp_path, [
        {"event": "artifact_produced", "sequence": 1, "artifact_id": "evidence-1"},
        {"event": "artifact_registered", "sequence": 2, "artifact_id": "evidence-1"},
        {"event": "role_dispatch", "sequence": 3, "role": "reasoning-specialist", "artifact_ids": ["evidence-1"], "content_sha256": actual, "evidence_item_ids": ["confirmed_facts:0"]},
    ]))
    assert facts["artifacts"][0]["declared_sha256"] == actual
    assert facts["artifacts"][0]["bytes_match"] is True
    assert d11_protocol.validate_collected_evidence(facts)["status"] == "PASS"
    assert sha != actual


def test_collector_does_not_accept_report_booleans_or_unproven_consumption(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.init(root)
    started = core.task_start(root, "collector", None, None)
    task_id = core.task_show(root)["state"]["task_id"]
    (root / "evidence.md").write_text(evidence_envelope(task_id, started["revision"] + 1, "evidence-1"), encoding="utf-8")
    core.task_artifact(root, started["revision"], "evidence-1", "evidence.md", "bounded fact", producer_role="investigator")
    facts = d11_collector.collect_evidence(root, trusted_events(tmp_path, [{"event": "artifact_produced", "sequence": 1, "artifact_id": "evidence-1"}]))
    facts["produced_before_decision"] = True
    assert d11_protocol.validate_collected_evidence(facts)["code"] == "EVIDENCE_ORDERING"


def test_untrusted_dict_cannot_enter_collector_and_missing_artifact_stays_required(tmp_path: Path) -> None:
    root = repo(tmp_path / "missing")
    core.init(root)
    core.task_start(root, "missing artifact", None, None)
    with pytest.raises(ValueError, match="normalized trusted events"):
        d11_collector.collect_evidence(root, [{"event": "role_dispatch", "role": "investigator"}])
    facts = d11_collector.collect_evidence(root, trusted_events(tmp_path / "events", [
        {"event": "role_dispatch", "role": "investigator"},
        {"event": "role_dispatch", "role": "reasoning-specialist"},
    ]))
    assert facts["evidence_required"] == "REQUIRED"
    assert d11_protocol.validate_collected_evidence(facts)["code"] == "EVIDENCE_COLLECTOR_MISSING"


def test_session_collector_counts_completed_failed_and_orphaned_once(tmp_path: Path) -> None:
    sessions = d11_collector.collect_sessions(trusted_events(tmp_path, [
        {"event": "session_usage", "session_id": "root", "role": "controller", "model": "gpt-5.6-luna", "usage": {"input": 10, "cached_input": 2, "output": 3}, "status": "COMPLETED"},
        {"event": "session_usage", "session_id": "failed", "role": "implementer", "model": "gpt-5.6-terra", "usage": {"input": 20, "cached_input": 0, "output": 4}, "status": "FAILED"},
        {"event": "session_usage", "session_id": "orphan", "role": "reviewer", "model": "gpt-5.6-terra", "usage": {"input": 30, "cached_input": 5, "output": 6}, "status": "ORPHANED"},
    ]))
    assert [item["session_id"] for item in sessions] == ["failed", "orphan", "root"]
    cost = d11_protocol.calculate_cost(sessions)
    assert cost["status"] == "PASS" and cost["by_model"]["gpt-5.6-terra"]["input"] == 50


def test_session_collector_uses_native_rollout_session_identity_and_cumulative_usage(tmp_path: Path) -> None:
    sessions = d11_collector.collect_sessions(trusted_events(tmp_path, [
        {"type": "session_meta", "payload": {"id": "native-1", "agent_role": "implementer", "base_instructions": {"provenance": {"model": "gpt-5.6-terra"}}}},
        {"type": "token_usage_record", "payload": {"thread_token_usage": {"input_tokens": 10, "cached_input_tokens": 2, "output_tokens": 3}}},
        {"type": "token_usage_record", "payload": {"thread_token_usage": {"input_tokens": 25, "cached_input_tokens": 5, "output_tokens": 7}}},
    ]))
    assert len(sessions) == 1
    assert sessions[0]["session_id"] == "native-1"
    assert sessions[0]["role"] == "implementer"
    assert sessions[0]["model"] == "gpt-5.6-terra"
    assert sessions[0]["input"] == 25 and sessions[0]["cached_input"] == 5 and sessions[0]["output"] == 7


def test_malformed_artifact_bytes_fail_even_when_registered(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.init(root)
    started = core.task_start(root, "malformed artifact", None, None)
    (root / "evidence.md").write_text("confirmed fact", encoding="utf-8")
    core.task_artifact(root, started["revision"], "evidence-1", "evidence.md", "bad", producer_role="investigator")
    facts = d11_collector.collect_evidence(root, trusted_events(tmp_path / "events", [
        {"event": "artifact_produced", "artifact_id": "evidence-1"},
        {"event": "artifact_registered", "artifact_id": "evidence-1"},
    ]))
    assert d11_protocol.validate_collected_evidence(facts)["code"] == "EVIDENCE_ARTIFACT_SCHEMA"


def test_superseded_same_path_uses_registration_attestation_and_is_not_reused(tmp_path: Path) -> None:
    root = repo(tmp_path)
    core.init(root)
    started = core.task_start(root, "replace evidence", None, None)
    task_id = core.task_show(root)["state"]["task_id"]
    path = root / "evidence.md"
    old_envelope = json.loads(evidence_envelope(task_id, started["revision"] + 1, "evidence-1"))
    path.write_text(json.dumps(old_envelope, separators=(",", ":")), encoding="utf-8")
    old = core.task_artifact(root, started["revision"], "evidence-1", "evidence.md", "old", producer_role="investigator")
    new_envelope = json.loads(evidence_envelope(task_id, old["revision"] + 1, "evidence-2"))
    path.write_text(json.dumps(new_envelope, separators=(",", ":")), encoding="utf-8")
    new = core.task_artifact(root, old["revision"], "evidence-2", "evidence.md", "new", producer_role="investigator", supersedes=["evidence-1"])
    actual_new = __import__("hashlib").sha256(path.read_bytes()).hexdigest()
    facts = d11_collector.collect_evidence(root, trusted_events(tmp_path / "events", [
        {"event": "artifact_produced", "artifact_id": "evidence-1"},
        {"event": "artifact_registered", "artifact_id": "evidence-1", "content_sha256": old_envelope and __import__("hashlib").sha256(json.dumps(old_envelope, separators=(",", ":")).encode()).hexdigest(), "artifact_envelope": old_envelope},
        {"event": "artifact_produced", "artifact_id": "evidence-2"},
        {"event": "artifact_registered", "artifact_id": "evidence-2", "content_sha256": actual_new},
        {"event": "role_dispatch", "role": "reasoning-specialist", "artifact_ids": ["evidence-2"], "content_sha256": actual_new, "evidence_item_ids": ["confirmed_facts:0"]},
    ]))
    old_fact, new_fact = facts["artifacts"]
    assert old_fact["active"] is False and old_fact["bytes_match"] is False and old_fact["registration_attested"] is True
    assert new_fact["active"] is True and new_fact["bytes_match"] is True
    assert d11_protocol.validate_collected_evidence(facts)["status"] == "PASS"
    assert new["revision"] == old["revision"] + 1


def test_review_graph_binds_each_round_to_its_own_candidate_and_native_session(tmp_path: Path) -> None:
    facts = d11_collector.collect_review_graph(trusted_events(tmp_path, [
        {"event": "SubagentStart", "sequence": 1, "role": "reviewer", "session_id": "review-a"},
        {"event": "candidate_attestation", "stage": "review-start", "session_id": "review-a", "candidate_root": "unused", "candidate_identity": "candidate-a", "manifest_version": 2, "harness_identity": "h", "sandbox_mode": "read-only"},
        {"event": "review_verdict", "sequence": 2, "session_id": "review-a", "candidate_identity": "ignored", "verdict": "REQUEST_CHANGES", "finding_id": "F-1", "classification": "LOCAL_SEMANTIC"},
        {"event": "implementer_dispatch", "sequence": 3, "session_id": "implementer-a", "candidate_from": "candidate-a", "finding_id": "F-1"},
        {"event": "source_mutation", "sequence": 4, "session_id": "implementer-a", "candidate_identity": "candidate-b"},
        {"event": "deterministic_verification", "sequence": 5, "candidate_identity": "candidate-b", "outcome": "PASSED"},
        {"event": "SubagentStart", "sequence": 6, "role": "reviewer", "session_id": "review-b"},
        {"event": "candidate_attestation", "stage": "review-start", "session_id": "review-b", "candidate_root": "unused", "candidate_identity": "candidate-b", "manifest_version": 2, "harness_identity": "h", "sandbox_mode": "read-only"},
        {"event": "review_verdict", "sequence": 7, "session_id": "review-b", "candidate_identity": "ignored", "verdict": "READY"},
    ]))
    assert d11_protocol.validate_review_graph(facts, final_candidate="candidate-b")["status"] == "PASS"
    facts["review_rounds"][0]["reviewer_session"] = "review-b"
    assert d11_protocol.validate_review_graph(facts, final_candidate="candidate-b")["code"] == "REVIEW_SESSION_REUSE"


def test_review_graph_rejects_unchanged_cognitive_cycle(tmp_path: Path) -> None:
    events = [
        {"event": "SubagentStart", "role": "reviewer", "session_id": "review-a"},
        {"event": "candidate_attestation", "stage": "review-start", "session_id": "review-a", "candidate_root": "unused", "candidate_identity": "candidate-a", "manifest_version": 2, "harness_identity": "h", "sandbox_mode": "read-only"},
        {"event": "review_verdict", "session_id": "review-a", "verdict": "REQUEST_CHANGES", "finding_id": "F-1", "classification": "LOCAL_SEMANTIC"},
        {"event": "SubagentStart", "role": "reviewer", "session_id": "review-b"},
        {"event": "candidate_attestation", "stage": "review-start", "session_id": "review-b", "candidate_root": "unused", "candidate_identity": "candidate-a", "manifest_version": 2, "harness_identity": "h", "sandbox_mode": "read-only"},
        {"event": "review_verdict", "session_id": "review-b", "verdict": "REQUEST_CHANGES", "finding_id": "F-1", "classification": "LOCAL_SEMANTIC"},
    ]
    facts = d11_collector.collect_review_graph(trusted_events(tmp_path, events))
    assert d11_protocol.validate_review_graph(facts, final_candidate="candidate-a")["code"] == "REVIEW_NO_PROGRESS"


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


def test_manifest_excludes_only_explicit_runtime_and_benchmark_surfaces(tmp_path: Path) -> None:
    root = repo(tmp_path)
    (root / ".codex").mkdir()
    (root / ".codex" / "observable.txt").write_text("product", encoding="utf-8")
    (root / "benchmarks").mkdir()
    (root / "benchmarks" / "observable.txt").write_text("product", encoding="utf-8")
    default = candidate_manifest.build_manifest(root)["manifest"]["files"]
    assert ".codex/observable.txt" in {item["path"] for item in default}
    assert "benchmarks/observable.txt" in {item["path"] for item in default}
    policy = {"task_state_surface": [".git", ".context", ".agent-memory", ".milestones"], "trusted_runtime_surface": [".codex"], "benchmark_infrastructure_surface": ["benchmarks"]}
    explicit = candidate_manifest.build_manifest(root, policy)["manifest"]["files"]
    assert ".codex/observable.txt" not in {item["path"] for item in explicit}
    assert "benchmarks/observable.txt" not in {item["path"] for item in explicit}


def test_trusted_infrastructure_identity_detects_post_freeze_mutation(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime.cmd"
    runtime.write_bytes(b"trusted-v1")
    frozen = trusted_surface.identity([runtime])
    assert trusted_surface.verify(frozen, [runtime]) is True
    runtime.write_bytes(b"candidate-overwrite")
    assert trusted_surface.verify(frozen, [runtime]) is False
    assert trusted_surface.mutation_probe(runtime) == "ALLOWED"


def test_candidate_chain_is_bound_to_computed_manifest(tmp_path: Path) -> None:
    root = repo(tmp_path)
    source = root / "product.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    identity = candidate_manifest.candidate_identity(root)
    events = [
        {"event": "candidate_attestation", "stage": "runtime-final", "candidate_root": str(root.resolve()), "candidate_identity": identity, "manifest_version": 2, "harness_identity": "h"},
        {"event": "candidate_attestation", "stage": "review-start", "session_id": "review", "candidate_root": str(root.resolve()), "candidate_identity": identity, "manifest_version": 2, "harness_identity": "h", "sandbox_mode": "read-only"},
        {"event": "review_verdict", "session_id": "review", "verdict": "READY", "candidate_identity": "ignored"},
        {"event": "candidate_attestation", "stage": "verification-start", "candidate_root": str(root.resolve()), "candidate_identity": identity, "manifest_version": 2, "harness_identity": "h"},
        {"event": "candidate_attestation", "stage": "evaluator-start", "candidate_root": str(root.resolve()), "candidate_identity": identity, "manifest_version": 2, "harness_identity": "h"},
        {"event": "candidate_attestation", "stage": "seal", "candidate_root": str(root.resolve()), "candidate_identity": identity, "manifest_version": 2, "harness_identity": "h"},
    ]
    chain = d11_collector.collect_candidate_chain(root, trusted_events(tmp_path.parent / "candidate-events", events))
    assert d11_protocol.validate_candidate_chain(chain)["status"] == "PASS"
    source.write_text("VALUE = 2\n", encoding="utf-8")
    assert d11_protocol.validate_candidate_chain(d11_collector.collect_candidate_chain(root, trusted_events(tmp_path.parent / "candidate-events-changed", events)))["code"] == "CANDIDATE_IDENTITY_MISMATCH"


def test_preflight_is_fail_closed_without_clean_fixture_and_calibration(tmp_path: Path) -> None:
    root = repo(tmp_path)
    (root / "dirty.py").write_text("dirty", encoding="utf-8")
    candidate = repo(tmp_path / "candidate")
    result = d11_preflight.run_preflight(
        root,
        candidate,
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
        d11_preflight.freeze_run_manifest(
            {"status": "PREFLIGHT_FAIL"},
            task_spec_path=Path("missing-task-spec"),
            base_candidate_root=Path("missing-base"),
            gold_candidate_root=Path("missing-gold"),
            base_candidate={},
            gold_candidate={},
            calibration={},
            pricing_snapshot={},
        )
    except ValueError as exc:
        assert "failed preflight" in str(exc)
    else:
        raise AssertionError("failed preflight was frozen")


def test_source_registry_rejects_arbitrary_paths_and_wrong_source_events(tmp_path: Path) -> None:
    stream = tmp_path / "stream.jsonl"
    stream.write_text(json.dumps({"event": "SubagentStart", "session_id": "x"}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        d11_collector.load_trusted_events([{"kind": "harness_attestation", "path": stream}])
    registry = d11_sources.create_source_registry([{"kind": "harness_attestation", "path": stream}], run_id="run-1")
    with pytest.raises(ValueError, match="not allowed"):
        d11_collector.load_trusted_events(registry)


def test_source_registry_append_only_stream_keeps_identity_and_tracks_provenance(tmp_path: Path) -> None:
    stream = tmp_path / "attest.jsonl"
    attestation = {"event": "candidate_attestation", "stage": "seal", "candidate_root": ".", "candidate_identity": "a" * 64, "manifest_version": 2, "harness_identity": "h"}
    stream.write_text(json.dumps(attestation) + "\n", encoding="utf-8")
    registry = d11_sources.create_source_registry([{"kind": "harness_attestation", "path": stream, "stream_identity_policy": "append_only"}], run_id="run-2")
    stream.write_text(stream.read_text(encoding="utf-8") + json.dumps(attestation) + "\n", encoding="utf-8")
    events = d11_collector.load_trusted_events(registry)
    assert len(events) == 2 and events[0]["_source_id"] == registry["registry"]["sources"][0]["source_id"]


def test_host_candidate_attestation_computes_identity_without_caller_identity(tmp_path: Path) -> None:
    root = repo(tmp_path / "candidate")
    (root / "product.py").write_text("VALUE = 1\n", encoding="utf-8")
    stream = tmp_path / "attest.jsonl"
    policy = candidate_manifest.build_manifest(root)["manifest"]["policy"]
    event = d11_collector.attest_candidate(stream, run_id="run-3", stage="runtime-final", candidate_root=root, policy=policy, harness_identity="harness-sha")
    assert event["candidate_identity"] == candidate_manifest.candidate_identity(root, policy)
    assert "sandbox_mode" not in event
    registry = d11_sources.create_source_registry([{"kind": "harness_attestation", "path": stream}], run_id="run-3")
    assert d11_collector.load_trusted_events(registry)[0]["_registry_identity"] == registry["identity"]


def test_manifest_includes_ignored_observable_file_and_closes_symlink_identity(tmp_path: Path) -> None:
    root = repo(tmp_path / "candidate")
    (root / ".gitignore").write_text("ignored.cfg\n", encoding="utf-8")
    ignored = root / "ignored.cfg"
    ignored.write_text("A", encoding="utf-8")
    first = candidate_manifest.build_manifest(root)
    assert "ignored.cfg" in {item["path"] for item in first["manifest"]["files"]}
    ignored.write_text("B", encoding="utf-8")
    assert candidate_manifest.candidate_identity(root) != first["identity"]
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    link = root / "external-link"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    with pytest.raises(ValueError, match="EXTERNAL_SYMLINK_SURFACE"):
        candidate_manifest.build_manifest(root)


def test_evaluator_calibration_is_host_invoked_and_freezes_real_identities(tmp_path: Path) -> None:
    base = repo(tmp_path / "base")
    gold = repo(tmp_path / "gold")
    (base / "marker.txt").write_text("base", encoding="utf-8")
    (gold / "marker.txt").write_text("gold", encoding="utf-8")
    evaluator = tmp_path / "evaluator.py"
    evaluator.write_text("import json, pathlib, sys; print(json.dumps({'status': 'PASS' if pathlib.Path(sys.argv[1], 'marker.txt').read_text() == 'gold' else 'FAIL'}))\n", encoding="utf-8")
    calibration = d11_preflight.run_frozen_evaluator_calibration(
        evaluator,
        base_candidate_root=base,
        gold_candidate_root=gold,
        candidate_policy=candidate_manifest.build_manifest(base)["manifest"]["policy"],
    )
    assert calibration["status"] == "PASS"
    assert calibration["gold"]["exit_code"] == 0 and calibration["base"]["exit_code"] == 0
    assert d11_preflight.verify_calibration_attestation(
        calibration,
        evaluator_path=evaluator,
        base_identity=candidate_manifest.candidate_identity(base),
        gold_identity=candidate_manifest.candidate_identity(gold),
    ) is True


def test_structured_evidence_source_ref_is_resolved_against_actual_bytes(tmp_path: Path) -> None:
    root = repo(tmp_path / "candidate")
    core.init(root)
    (root / "src").mkdir()
    source = root / "src" / "product.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    started = core.task_start(root, "source-backed evidence", None, None)
    task_id = core.task_show(root)["state"]["task_id"]
    source_sha = __import__("hashlib").sha256(source.read_bytes()).hexdigest()
    ref = {"kind": "repo", "path": "src/product.py", "content_sha256": source_sha}
    envelope = {
        "artifact_id": "evidence-1", "task_id": task_id, "producer_base_revision": started["revision"],
        "producer_session": "investigator-1", "producer_identity": "session-attestation-1",
        "source_refs": [ref], "affected_surface": ["src/product.py"],
        "confirmed_facts": [{"text": "entrypoint is present", "source_refs": [ref]}],
        "inferences": [], "unknowns": [], "contradictions": [],
        "verification": [{"description": "read source", "source_refs": [ref]}],
    }
    artifact_path = root / "evidence.json"
    artifact_path.write_text(json.dumps(envelope, separators=(",", ":")), encoding="utf-8")
    registered = core.task_artifact(root, started["revision"], "evidence-1", "evidence.json", "bounded fact", producer_role="investigator")
    sha = __import__("hashlib").sha256(artifact_path.read_bytes()).hexdigest()
    facts = d11_collector.collect_evidence(root, trusted_events(tmp_path / "events", [
        {"event": "artifact_produced", "artifact_id": "evidence-1"},
        {"event": "artifact_registered", "artifact_id": "evidence-1", "content_sha256": sha},
        {"event": "role_dispatch", "role": "reasoning-specialist", "artifact_ids": ["evidence-1"], "content_sha256": sha, "evidence_item_ids": ["confirmed_facts:0"]},
    ]))
    assert facts["artifacts"][0]["source_refs_valid"] is True
    assert d11_protocol.validate_collected_evidence(facts)["status"] == "PASS"
    assert registered["revision"] > started["revision"]
