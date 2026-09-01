"""The seven-dimension weighted scorer.

This module contains no model calls and never will. That is the point: a
composite score is arithmetic over features, so roughly three quarters of
tasks are resolved for the price of a dictionary lookup. A model is consulted
only when the deterministic path is genuinely uncertain, which the caller
decides from `confidence` and the ambiguous window.
"""
from __future__ import annotations

import math
import re

from .policy import applicable_overrides
from .schemas import (
    Archetype,
    Band,
    DimensionScore,
    Evidence,
    Override,
    Resolution,
    ScoredTask,
    Task,
)

DIMENSIONS = [
    ("frequency", "Task frequency", 0.15),
    ("rule_based", "Rule-based nature", 0.20),
    ("sensitivity", "Data sensitivity", 0.15),
    ("complexity", "Decision complexity", 0.20),
    ("integration", "Integration maturity", 0.10),
    ("roi", "ROI potential", 0.10),
    ("availability", "Data availability", 0.10),
]

JUDGEMENT_WORDS = [
    "negotiat", "advis", "assess", "judgement", "judgment", "strateg", "approve",
    "escalat", "resolve dispute", "interpret", "counsel", "investigat", "design",
    "recommend", "evaluat",
]
ROUTINE_WORDS = [
    "extract", "validat", "match", "post", "reconcil", "generat", "record", "log",
    "route", "classif", "index", "file", "update", "calculate", "check", "monitor",
    "collect", "transmit", "archive", "notify",
]
SENSITIVE_WORDS = [
    "employee", "personal", "salary", "payroll", "candidate", "patient", "subscriber",
    "customer record", "medical", "bank", "identity", "passport",
]


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def _keyword_hits(text: str, words: list[str]) -> int:
    lowered = text.lower()
    return sum(1 for w in words if w in lowered)


def infer_archetype(task: Task) -> Archetype:
    text = f"{task.l3_name} {task.l4_name}".lower()
    if any(w in text for w in ["monitor", "track", "audit", "report", "review compliance", "obligation"]):
        return Archetype.MONITORING
    if any(w in text for w in ["draft", "generat", "prepare", "produce", "author", "compose", "redline"]):
        return Archetype.GENERATION
    if any(w in text for w in ["assess", "classif", "decide", "determin", "analys", "analyz", "evaluat", "match", "reconcil"]):
        return Archetype.REASONING
    if any(w in text for w in ["route", "coordinat", "orchestrat", "schedul", "dispatch"]):
        return Archetype.ORCHESTRATION
    return Archetype.EXTRACTION


def _dimension_scores(task: Task) -> tuple[list[DimensionScore], float]:
    """Return the seven dimensions plus a completeness figure driving confidence."""
    text = f"{task.l3_name} {task.l4_name} {task.notes or ''}"
    known = 0
    total = 7
    dims: list[DimensionScore] = []

    # 1. Frequency. Log-scaled: a task run 20k times a month is not 20x more
    # automatable than one run 1k times, but it is meaningfully more so.
    if task.volume_per_month is not None:
        raw = _clamp(math.log10(max(task.volume_per_month, 1)) / 4.0 * 100)
        basis = f"{task.volume_per_month:,.0f} executions per month"
        known += 1
    else:
        raw = 50.0
        basis = "volume not supplied, assumed median"
    dims.append(DimensionScore(key="frequency", label="Task frequency", weight=0.15, raw=raw, weighted=raw * 0.15, basis=basis))

    # 2. Rule-based nature.
    if task.rule_based is not None:
        raw = _clamp(task.rule_based)
        basis = "supplied by client inventory"
        known += 1
    else:
        routine = _keyword_hits(text, ROUTINE_WORDS)
        judgement = _keyword_hits(text, JUDGEMENT_WORDS)
        raw = _clamp(50 + routine * 14 - judgement * 20)
        basis = f"inferred from task verb, {routine} routine and {judgement} judgement signals"
    dims.append(DimensionScore(key="rule_based", label="Rule-based nature", weight=0.20, raw=raw, weighted=raw * 0.20, basis=basis))

    # 3. Data sensitivity. Higher score means LESS sensitive, so it is safe to
    # automate. The hard PII cap is applied separately by policy.
    if task.pii is not None:
        raw = 25.0 if task.pii else 85.0
        basis = "PII flag from inventory"
        known += 1
    else:
        hits = _keyword_hits(text, SENSITIVE_WORDS)
        raw = _clamp(85 - hits * 30)
        basis = f"{hits} sensitivity signals in task text" if hits else "no sensitivity signals detected"
    dims.append(DimensionScore(key="sensitivity", label="Data sensitivity", weight=0.15, raw=raw, weighted=raw * 0.15, basis=basis))

    # 4. Decision complexity. Exception rate is the best proxy when present.
    if task.exception_rate is not None:
        raw = _clamp(100 - task.exception_rate * 100 * 2.2)
        basis = f"{task.exception_rate * 100:.0f}% exception rate"
        known += 1
    else:
        judgement = _keyword_hits(text, JUDGEMENT_WORDS)
        raw = _clamp(72 - judgement * 22)
        basis = f"{judgement} judgement signals in task text"
    dims.append(DimensionScore(key="complexity", label="Decision complexity", weight=0.20, raw=raw, weighted=raw * 0.20, basis=basis))

    # 5. Integration maturity. Fewer systems and named APIs mean easier reach.
    if task.systems:
        parts = [s for s in re.split(r"[|,;]", task.systems) if s.strip()]
        api_ready = any(k in task.systems.lower() for k in ["api", "odata", "rest", "sap", "servicenow", "salesforce", "workday", "oracle"])
        raw = _clamp(90 - (len(parts) - 1) * 18 + (12 if api_ready else -18))
        basis = f"{len(parts)} system(s), {'API addressable' if api_ready else 'no API signal'}"
        known += 1
    else:
        raw = 45.0
        basis = "systems not supplied, assumed partial integration"
    dims.append(DimensionScore(key="integration", label="Integration maturity", weight=0.10, raw=raw, weighted=raw * 0.10, basis=basis))

    # 6. ROI potential, from annual hours consumed.
    hours = task.annual_hours
    if hours > 0:
        raw = _clamp(math.log10(max(hours, 1)) / 4.3 * 100)
        basis = f"{hours:,.0f} annual hours"
        known += 1
    else:
        raw = 40.0
        basis = "effort data not supplied"
    dims.append(DimensionScore(key="roi", label="ROI potential", weight=0.10, raw=raw, weighted=raw * 0.10, basis=basis))

    # 7. Data availability, a completeness measure of the row itself.
    supplied = sum(
        1 for v in [task.volume_per_month, task.avg_handle_minutes, task.rule_based, task.systems, task.exception_rate]
        if v is not None
    )
    raw = _clamp(supplied / 5.0 * 100)
    dims.append(DimensionScore(key="availability", label="Data availability", weight=0.10, raw=raw, weighted=raw * 0.10, basis=f"{supplied} of 5 optional fields supplied"))
    if supplied >= 3:
        known += 1

    completeness = known / total
    return dims, completeness


def score_task(task: Task, pack: dict) -> ScoredTask:
    """Score one task deterministically. No network, no model, no I/O."""
    dims, completeness = _dimension_scores(task)
    raw = sum(d.weighted for d in dims)

    by_key = {d.key: d.raw for d in dims}
    flags = {
        "pii": bool(task.pii),
        "safety_critical": bool(task.safety_critical),
        "executive_judgement": bool(task.executive_judgement),
        # Computed signal: an activity that is neither rule-bound nor simple is
        # human work however often it runs. Without this, high-volume judgement
        # tasks are pulled into the automatable band by frequency and ROI alone.
        "judgement_dominant": by_key["rule_based"] < 30 and by_key["complexity"] < 40,
    }
    # Keyword rules see the activity only, never the process group name above it.
    text = f"{task.l4_name} {task.notes or ''}"

    overrides: list[Override] = []
    score = raw
    for rule in applicable_overrides(flags, text, pack):
        cap = float(rule["cap"])
        if score > cap:
            overrides.append(Override(rule=rule["rule"], cap=cap, reason=rule["reason"], source=rule.get("source", "policy")))
            score = cap

    bands = pack["bands"]
    if score >= bands["full_agent"]:
        band = Band.FULL_AGENT
    elif score >= bands["hitl"]:
        band = Band.HITL
    else:
        band = Band.HUMAN_ONLY

    # Confidence falls when the row is thin or the score sits near a boundary.
    edge = min(abs(score - bands["full_agent"]), abs(score - bands["hitl"]))
    boundary_penalty = max(0.0, (8 - edge) / 8 * 0.25)
    confidence = round(_clamp(0.55 + completeness * 0.45 - boundary_penalty, 0.0, 1.0), 3)

    evidence = [
        Evidence(
            kind="computed",
            label="Weighted composite",
            detail=" + ".join(f"{d.label} {d.raw:.0f}x{d.weight:.2f}" for d in dims),
            source="scoring.py: DIMENSIONS",
        )
    ]
    for ov in overrides:
        evidence.append(Evidence(kind="policy", label=f"Cap at {ov.cap:.0f}", detail=ov.reason, source=ov.source))

    top = sorted(dims, key=lambda d: d.weighted, reverse=True)[:2]
    rationale = (
        f"Scored {raw:.0f} on seven weighted dimensions, led by {top[0].label.lower()} "
        f"({top[0].basis}) and {top[1].label.lower()} ({top[1].basis})."
    )
    if overrides:
        ov = overrides[-1]
        rationale += f" Capped to {score:.0f} by the {ov.rule} rule: {ov.reason}"

    return ScoredTask(
        task=task,
        dimensions=dims,
        raw_score=round(raw, 1),
        score=round(score, 1),
        band=band,
        confidence=confidence,
        resolution=Resolution.DETERMINISTIC,
        overrides=overrides,
        evidence=evidence,
        rationale=rationale,
        archetype=infer_archetype(task),
    )


def needs_adjudication(scored: ScoredTask, low: float, high: float, floor: float) -> bool:
    """A task reaches a model only if it is near a boundary or under-evidenced.

    A capped task never needs adjudication: policy already decided it, and
    spending a model call to second-guess a deterministic rule is waste.
    """
    if scored.overrides:
        return False
    if scored.confidence < floor:
        return True
    return low <= scored.score <= high
