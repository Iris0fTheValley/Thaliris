"""Focused checks of the shared semantic contract; no Host behavior claims."""
from pathlib import Path


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
