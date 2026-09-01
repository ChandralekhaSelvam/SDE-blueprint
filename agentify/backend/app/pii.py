"""Input-side redaction.

Client SOPs and process inventories routinely carry employee names, case
references and account numbers in free-text columns. Nothing reaches a model
provider or the semantic cache before passing through here.

Deliberately regex-based rather than an ML recogniser: this runs on every row
of every upload, and a deterministic redactor is auditable, instant and free.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]{2,}\b")),
    ("IBAN", re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b")),
    ("CARD", re.compile(r"\b(?:\d[ -]?){13,19}\b")),
    ("PHONE", re.compile(r"\b(?:\+\d{1,3}[ -]?)?(?:\(\d{2,4}\)[ -]?)?\d{3,4}[ -]\d{3,4}\b")),
    ("NATIONAL_ID", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("CASE_REF", re.compile(r"\b(?:CASE|REF|TKT|INC|CTR)[-_ ]?\d{4,}\b", re.I)),
    ("MONEY_ACCOUNT", re.compile(r"\bacct\.?\s*#?\s*\d{6,}\b", re.I)),
]

NAME_HINT = re.compile(r"\b(?:Mr|Mrs|Ms|Dr)\.?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b")


@dataclass
class MaskResult:
    text: str
    hits: dict[str, int]

    @property
    def total(self) -> int:
        return sum(self.hits.values())


def mask(text: str | None) -> MaskResult:
    if not text:
        return MaskResult(text or "", {})
    hits: dict[str, int] = {}
    out = text
    for label, pattern in PATTERNS:
        out, count = pattern.subn(f"[{label}]", out)
        if count:
            hits[label] = hits.get(label, 0) + count
    out, count = NAME_HINT.subn("[NAME]", out)
    if count:
        hits["NAME"] = hits.get("NAME", 0) + count
    return MaskResult(out, hits)


def mask_payload(fields: dict[str, str | None]) -> tuple[dict[str, str], dict[str, int]]:
    """Mask a whole handoff payload and report what was found."""
    cleaned: dict[str, str] = {}
    totals: dict[str, int] = {}
    for key, value in fields.items():
        result = mask(value)
        cleaned[key] = result.text
        for label, count in result.hits.items():
            totals[label] = totals.get(label, 0) + count
    return cleaned, totals
