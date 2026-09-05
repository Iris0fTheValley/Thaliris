"""Benchmark-only candidate screener for the Thaliris T4 phase.

The input is a JSON list of candidate records with nine 1--5 evidence scores.
This module deliberately does not fetch datasets or alter product code.  It
provides a deterministic sanity check and a compact ranking signal for the
human-controlled A-lite/B-lite screening stage.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


SCORE_FIELDS = (
    "investigation_volume",
    "decision_ambiguity",
    "cross_module_reasoning",
    "hidden_invariant_strength",
    "scope_precision_requirement",
    "luna_failure_likelihood",
    "sol_advantage_likelihood",
    "evaluator_reliability",
    "environment_reproduction_cost",
)


def validate_candidate(candidate: dict[str, Any]) -> None:
    """Raise ``ValueError`` when a record is not a comparable candidate."""
    for field in ("task", "source", "status", *SCORE_FIELDS):
        if field not in candidate:
            raise ValueError(f"candidate is missing {field!r}")
    for field in SCORE_FIELDS:
        score = candidate[field]
        if not isinstance(score, int) or not 1 <= score <= 5:
            raise ValueError(f"{candidate['task']}: {field} must be an integer from 1 to 5")


def screening_signal(candidate: dict[str, Any]) -> float:
    """Return a ranking signal; it is not a predicted model-quality metric."""
    validate_candidate(candidate)
    positive = sum(candidate[field] for field in SCORE_FIELDS[:7])
    reliability = candidate["evaluator_reliability"]
    setup_penalty = candidate["environment_reproduction_cost"]
    return round(positive + reliability - setup_penalty, 2)


def load_candidates(path: Path) -> list[dict[str, Any]]:
    candidates = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(candidates, list):
        raise ValueError("candidate file must contain a JSON list")
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise ValueError("each candidate must be a JSON object")
        validate_candidate(candidate)
        candidate["screening_signal"] = screening_signal(candidate)
    return candidates


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print(f"usage: {Path(sys.argv[0]).name} CANDIDATES.json", file=sys.stderr)
        return 2
    try:
        candidates = load_candidates(Path(argv[0]))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print("task\tstatus\tsignal\tsetup_cost\twhy_luna_may_fail")
    for candidate in sorted(candidates, key=lambda item: item["screening_signal"], reverse=True):
        print(
            "\t".join(
                (
                    candidate["task"],
                    candidate["status"],
                    str(candidate["screening_signal"]),
                    str(candidate["environment_reproduction_cost"]),
                    candidate.get("why_luna_may_fail", ""),
                )
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
