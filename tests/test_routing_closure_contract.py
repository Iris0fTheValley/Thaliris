"""Focused checks of the shared semantic contract; no Host behavior claims."""
from pathlib import Path
import re


def shared_contract():
    root = Path(__file__).resolve().parents[1]
    return " ".join((root / "docs/thaliris-routing-protocol.md").read_text(encoding="utf-8").lower().split())


def test_shared_precision_and_operational_authority_contract():
    text = shared_contract()
    for term in ("stable narrative base language", "precision-bearing original terms",
                 "quotations, distinctions and user formulations", "compression and handoff",
                 "output language requirements", "authoritative artifact, source, revision and provenance",
                 "before delegation", "later workstream", "operational acceptance"):
        assert term in text
    for term in ("project/package", "fixtures", "isolated smoke", "packed artifacts",
                 "project-local verification", "effective live host", "separate host authority"):
        assert term in text


def test_shared_compatibility_ambiguity_and_same_closure_rerouting():
    text = shared_contract()
    for term in ("accepted contract uniquely determines", "compatibility authority ambiguity remains semantic",
                 "production behavior and historical fixtures", "representative evidence",
                 "full regression is not mandatory", "same semantic closure", "fresh ordinary session",
                 "explicit inputs and independent acceptance", "accumulated debugging state adds no benefit",
                 "green evidence, provenance, remaining acceptance and blockers, not raw history",
                 "many failures, many files or long regression alone do not require escalation"):
        assert term in text


def test_shared_observation_frequency_and_wait_capacity_contract():
    text = shared_contract()
    for terms in (("normal controller", "directly available", "exceptional recovery", "when needed"),
                  ("complete task context", "retrieval", "delivered quality"),
                  ("one observation owner", "executors", "tests", "processes", "ci", "child result"),
                  ("tool maximum", "capacity", "higher-level limits", "precedence"),
                  ("simultaneous", "active/pending", "not a lifetime quota", "terminal completion"),
                  ("original failure", "local reproduction", "failed boundaries", "inferred deeper root cause"),
                  ("controller owns product acceptance", "reviewer is an optional", "selected review",
                   "native child completed", "task-close done")):
        assert all(term in text for term in terms)
    def prohibits_recommendation(value):
        return any("maximum" in clause and "recommended" in clause and "duration" in clause and "not" in clause
                   for clause in re.split(r"[.!?;]", value))
    assert prohibits_recommendation(text)
    assert not prohibits_recommendation(text.replace("not a recommended duration", "a recommended duration"))


def test_controller_acceptance_and_optional_review_are_shared_across_docs():
    root = Path(__file__).resolve().parents[1]
    protocol = shared_contract()
    roles = " ".join((root / "docs/thaliris-role-packs.md").read_text(encoding="utf-8").lower().split())
    agents = " ".join((root / "AGENTS.md").read_text(encoding="utf-8").lower().split())
    for text in (protocol, roles, agents):
        assert "controller" in text and "product acceptance" in text
        assert "no fixed closing handoff" in text
        assert "native child" in text and "completed" in text and "done" in text
        assert "pass" in text and "ready" in text
    assert "reviewer is an optional" in protocol
    assert "independent" in protocol and "non-writing" in protocol
    assert "a separate explicit closing handoff" not in protocol
    assert "controller integrates that result" not in protocol

    stale_claims_en = ("16 promotion units", "a confirmed promotion must",
                       "only the controller may run `task-promote`",
                       "`progress`/`verification` fields for the current milestone",
                       "memory only appends a new entry")
    for name in ("README.md", "README.en.md"):
        text = " ".join((root / name).read_text(encoding="utf-8").lower().split())
        if name == "README.md":
            stale_claims = ("16 个 promotion units", "confirmed promotion 还必须",
                            "只有 controller 可以运行 `task-promote`",
                            "当前 milestone 的 `progress`/`verification`",
                            "memory 只追加新 entry")
        else:
            stale_claims = stale_claims_en
        assert "completed" in text and "ready" in text and "done" in text
        assert "separate explicit closing handoff" not in text
        assert all(claim not in text for claim in stale_claims)

    # The task-promote input contract lives in DESIGN.md, not in the README narrative.
    design = " ".join((root / "DESIGN.md").read_text(encoding="utf-8").lower().split())
    assert "core does not impose semantic categories" in design
    assert "refuses to overwrite an existing target" in design
    assert "same transaction as the new documents" in design
    assert "including nested namespaces" in design
    assert all(claim not in design for claim in stale_claims_en)


def test_task_commands_select_the_global_task_id_and_design_describes_current_promotion():
    root = Path(__file__).resolve().parents[1]
    command = re.compile(r"thaliris-core[^\n]*\btask-(?:status|show|update|promote|close|artifact)\b")
    for name in ("README.md", "README.en.md"):
        text = (root / name).read_text(encoding="utf-8")
        for line in text.splitlines():
            if command.search(line):
                assert "--task-id" in line, f"missing explicit task selection in {name}: {line}"
    design = " ".join((root / "DESIGN.md").read_text(encoding="utf-8").lower().split())
    assert "supplies the complete content and its `base_sha256`" in design
    assert "`source_refs` may cite only evidence or artifacts already recorded in the selected task id" in design
    assert "promotion uses task-revision cas and does not advance that revision" in design
    agents = (root / "AGENTS.md").read_text(encoding="utf-8")
    assert "thaliris-core --task-id <id> task-status" in agents
    assert "thaliris-core --task-id <id> task-show" in agents
