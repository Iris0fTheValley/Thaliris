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
                  ("review ready", "selected candidate", "final product acceptance")):
        assert all(term in text for term in terms)
    def prohibits_recommendation(value):
        return any("maximum" in clause and "recommended" in clause and "duration" in clause and "not" in clause
                   for clause in re.split(r"[.!?;]", value))
    assert prohibits_recommendation(text)
    assert not prohibits_recommendation(text.replace("not a recommended duration", "a recommended duration"))
