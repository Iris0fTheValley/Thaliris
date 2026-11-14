"""Typed claim blocks: the shared, pure parser for a child's final message.

A child ends its final message with one fenced block whose info string is
``thaliris-claims``. The body is either the literal ``none`` or one JSON object::

    {"claims": [{"requirement": "R1", "polarity": "supports|contradicts|unknown",
                 "text": "...", "evidence": "<check id or path:line>",
                 "basis": "check|read|inference"}]}

The parser only reads shape. It never weighs a claim: there is no confidence
field, and an unreadable polarity or basis degrades to the weakest value
(``unknown`` / ``inference``) so a mistyped adverse claim stays an obligation
instead of being dropped.
"""
from __future__ import annotations

import json
import re

CLAIM_BLOCK_INFO = "thaliris-claims"
CLAIMS_MAX = 5
CLAIM_TEXT_MAX = 300
CLAIM_EVIDENCE_MAX = 300
CLAIM_REQUIREMENT_MAX = 64
CLAIM_POLARITIES = ("supports", "contradicts", "unknown")
CLAIM_BASES = ("check", "read", "inference")
CLAIM_EVIDENCE_UNSPECIFIED = "unspecified"

_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})[ \t]*([^\s`]*)[^`]*$")


def _clean(value: str, limit: int, *, single_line: bool = False) -> tuple[str, bool]:
    """Bounded text without control characters; returns (text, truncated)."""
    text = "".join(char if char in "\n\t" or (ord(char) >= 32 and ord(char) != 0x7F) else " " for char in value)
    if single_line:
        text = " ".join(text.split())
    text = text.strip()
    return text[:limit], len(text) > limit


def _last_block(text: str) -> str | None:
    """Body of the last ``thaliris-claims`` fence; an unclosed final fence runs to the end."""
    found: str | None = None
    opener: tuple[str, int, bool] | None = None  # fence character, length, is a claims block
    body: list[str] = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        match = _FENCE.match(line)
        if opener is None:
            if match:
                opener = (match.group(1)[0], len(match.group(1)), match.group(2) == CLAIM_BLOCK_INFO)
                body = []
            continue
        closes = (match is not None and match.group(1)[0] == opener[0] and len(match.group(1)) >= opener[1]
                  and not line.strip().strip(opener[0]))
        if closes:
            if opener[2]:
                found = "\n".join(body)
            opener = None
        else:
            body.append(line)
    if opener is not None and opener[2]:
        found = "\n".join(body)
    return found


def parse_claim_block(text: object) -> dict[str, object]:
    """Parse the last ``thaliris-claims`` fenced block of ``text``.

    Returns ``{"status", "claims", "total", "truncated", "invalid", "error"}``:

    - ``status``: ``present`` (a readable block, possibly with zero claims),
      ``missing`` (no such block) or ``malformed`` (a block whose body is neither
      ``none`` nor ``{"claims": [...]}``).
    - ``claims``: at most ``CLAIMS_MAX`` normalized claims in block order (over the cap,
      ``contradicts`` and ``unknown`` claims are kept before ``supports``), each
      ``{"requirement", "polarity", "text", "evidence", "basis"}`` plus
      ``text_truncated: true`` when the text exceeded ``CLAIM_TEXT_MAX`` and
      ``normalized: [field, ...]`` naming fields that were unreadable and took
      their weakest value.
    - ``total``: readable claims in the block before the cap; ``truncated`` is
      true when the cap dropped some. ``invalid`` counts list items that are not
      objects or carry no text.
    """
    result: dict[str, object] = {"status": "missing", "claims": [], "total": 0, "truncated": False,
                                 "invalid": 0, "error": None}
    if not isinstance(text, str):
        return result
    body = _last_block(text)
    if body is None:
        return result
    if body.strip().casefold() == "none":
        return {**result, "status": "present"}
    try:
        raw = json.loads(body)
    except (json.JSONDecodeError, RecursionError) as exc:
        return {**result, "status": "malformed", "error": _clean(f"block is not JSON: {exc}", 200, single_line=True)[0]}
    if not isinstance(raw, dict) or not isinstance(raw.get("claims"), list):
        return {**result, "status": "malformed", "error": 'block must be `none` or {"claims": [...]}'}
    claims: list[dict[str, object]] = []
    total = invalid = 0
    for item in raw["claims"]:
        if not isinstance(item, dict) or not isinstance(item.get("text"), str) or not item["text"].strip():
            invalid += 1
            continue
        total += 1
        normalized: list[str] = []
        body_text, text_truncated = _clean(item["text"], CLAIM_TEXT_MAX)
        requirement = item.get("requirement")
        if isinstance(requirement, str) and requirement.strip():
            requirement = _clean(requirement, CLAIM_REQUIREMENT_MAX, single_line=True)[0]
        else:
            requirement = ""
            normalized.append("requirement")
        polarity = item.get("polarity")
        polarity = polarity.strip().casefold() if isinstance(polarity, str) else None
        if polarity not in CLAIM_POLARITIES:
            polarity = "unknown"
            normalized.append("polarity")
        basis = item.get("basis")
        basis = basis.strip().casefold() if isinstance(basis, str) else None
        if basis not in CLAIM_BASES:
            basis = "inference"
            normalized.append("basis")
        evidence = item.get("evidence")
        evidence = _clean(evidence, CLAIM_EVIDENCE_MAX, single_line=True)[0] if isinstance(evidence, str) else ""
        if not evidence:
            evidence = CLAIM_EVIDENCE_UNSPECIFIED
            normalized.append("evidence")
        claim: dict[str, object] = {"requirement": requirement, "polarity": polarity, "text": body_text,
                                    "evidence": evidence, "basis": basis}
        if text_truncated:
            claim["text_truncated"] = True
        if normalized:
            claim["normalized"] = normalized
        claims.append(claim)
    if len(claims) > CLAIMS_MAX:
        # Adverse claims first: contradicts and unknown are kept before supports, block order within each group.
        adverse = [claim for claim in claims if claim["polarity"] != "supports"]
        supports = [claim for claim in claims if claim["polarity"] == "supports"]
        kept = (adverse + supports)[:CLAIMS_MAX]
        claims = [claim for claim in claims if any(claim is other for other in kept)]
    return {"status": "present", "claims": claims, "total": total, "truncated": total > len(claims),
            "invalid": invalid, "error": None}
