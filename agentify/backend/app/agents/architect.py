"""Agent architecture synthesis.

Turns scored L4 tasks into the four DoD artifacts: a catalog, the dependency
edges between agents, the human gates, and a per-agent automation estimate.

All four are derived deterministically. A model is used only to write the
purpose sentence and suggest tools, and only once per agent, not once per task.
If the model is unavailable the agent is still fully specified from templates,
which is why the app is demonstrable with no credentials at all.
"""
from __future__ import annotations

import re

from ..schemas import (
    AgentDependency,
    AgentSpec,
    Archetype,
    AutomationEstimate,
    Band,
    HumanGate,
    ScoredTask,
)

# Agents run in archetype order. This is the fixed grammar: the vocabulary
# never changes across industries, only which agents get instantiated.
ARCHETYPE_ORDER = [
    Archetype.EXTRACTION,
    Archetype.REASONING,
    Archetype.GENERATION,
    Archetype.MONITORING,
    Archetype.ORCHESTRATION,
]

ARCHETYPE_TEMPLATES: dict[Archetype, dict[str, object]] = {
    Archetype.EXTRACTION: {
        "suffix": "extractor",
        "purpose": "Parses source documents and records for this process group, normalises them against the taxonomy, and emits structured fields for downstream stages.",
        "tools": ["document_store", "ocr", "schema_validator"],
        "tier": "small",
    },
    Archetype.REASONING: {
        "suffix": "classifier",
        "purpose": "Evaluates the extracted fields against client policy and the risk register, assigns a disposition, and escalates anything outside its confidence contract.",
        "tools": ["policy_lookup", "rules_engine", "vector_search"],
        "tier": "medium",
    },
    Archetype.GENERATION: {
        "suffix": "drafter",
        "purpose": "Produces the outbound artifact for this process group from the classified inputs, using approved templates and leaving every substantive change attributable.",
        "tools": ["template_library", "document_writer", "diff_engine"],
        "tier": "medium",
    },
    Archetype.MONITORING: {
        "suffix": "monitor",
        "purpose": "Watches committed obligations and thresholds for this process group and raises an exception when a condition is breached or a deadline approaches.",
        "tools": ["scheduler", "erp_connector", "alerting"],
        "tier": "small",
    },
    Archetype.ORCHESTRATION: {
        "suffix": "router",
        "purpose": "Sequences work across the mesh for this process group, retries transient failures, and holds the run at any gate that requires a human decision.",
        "tools": ["queue", "state_store", "retry_policy"],
        "tier": "small",
    },
}

RESIDUALS = {"full_agent": 0.04, "hitl": 0.15, "human_only": 0.80}


def _titleise(name: str) -> str:
    words = re.sub(r"[^a-zA-Z ]", " ", name).split()
    stop = {"manage", "the", "and", "of", "for", "a", "an", "to", "process"}
    keep = [w for w in words if w.lower() not in stop][:3]
    return " ".join(keep).title() if keep else "Process"


def _grouping_key(task: ScoredTask) -> tuple[str, Archetype]:
    """Agents are formed per L2 process group per archetype.

    L2 is the right granularity: L3 makes too many single-task agents, L1 makes
    agents so broad their guardrail profiles conflict.
    """
    return (task.task.l2_code or task.task.l1_code, task.archetype)


def build_estimate(tasks: list[ScoredTask], residuals: dict[str, float]) -> AutomationEstimate:
    hours_today = sum(t.task.annual_hours for t in tasks)
    hours_after = sum(t.task.annual_hours * residuals[t.band.value] for t in tasks)
    split = {b.value: sum(1 for t in tasks if t.band is b) for b in Band}
    pct = 0.0 if hours_today <= 0 else (1 - hours_after / hours_today) * 100
    return AutomationEstimate(
        source_task_count=len(tasks),
        annual_hours_today=round(hours_today, 1),
        annual_hours_after=round(hours_after, 1),
        hours_removed=round(hours_today - hours_after, 1),
        fte_today=round(hours_today / 1720.0, 2),
        fte_after=round(hours_after / 1720.0, 2),
        automation_pct=round(pct, 1),
        band_split=split,
    )


def _risk_tier(tasks: list[ScoredTask]) -> str:
    if any(t.overrides for t in tasks):
        return "high"
    if any(t.band is Band.HITL for t in tasks):
        return "medium"
    return "low"


def _guardrails(tasks: list[ScoredTask], risk: str) -> list[str]:
    rails = ["input_validation", "output_schema", "audit_log"]
    if any(t.task.pii for t in tasks) or any(o.rule == "pii" for t in tasks for o in t.overrides):
        rails.append("pii_masking")
    if risk in {"medium", "high"}:
        rails += ["confidence_threshold", "escalation_policy"]
    if risk == "high":
        rails += ["dual_control", "fairness_check"]
    return rails


def build_catalog(
    scored: list[ScoredTask],
    residuals: dict[str, float],
    describe=None,
) -> list[AgentSpec]:
    """Group tasks into agents. `describe` is an optional model callback."""
    groups: dict[tuple[str, Archetype], list[ScoredTask]] = {}
    for task in scored:
        groups.setdefault(_grouping_key(task), []).append(task)

    # Fold single-task agents into the same L2's nearest archetype so the mesh
    # stays legible. A twelve-node graph explains itself; a sixty-node one does not.
    merged: dict[tuple[str, Archetype], list[ScoredTask]] = {}
    for (l2, arch), tasks in groups.items():
        if len(tasks) == 1:
            fallback = next(
                (k for k in merged if k[0] == l2),
                next((k for k in groups if k[0] == l2 and k != (l2, arch) and len(groups[k]) > 1), None),
            )
            if fallback:
                merged.setdefault(fallback, []).extend(tasks)
                continue
        merged.setdefault((l2, arch), []).extend(tasks)

    specs: list[AgentSpec] = []
    ordered = sorted(merged.items(), key=lambda kv: (ARCHETYPE_ORDER.index(kv[0][1]), kv[0][0]))

    for index, ((l2_code, archetype), tasks) in enumerate(ordered):
        template = ARCHETYPE_TEMPLATES[archetype]
        group_name = _titleise(tasks[0].task.l2_name or tasks[0].task.l1_name or l2_code)
        name = f"{group_name} {template['suffix']}"
        risk = _risk_tier(tasks)
        estimate = build_estimate(tasks, residuals)

        purpose = str(template["purpose"])
        tools = list(template["tools"])
        generated_by = "template"

        if describe is not None:
            hint = describe(name, archetype.value, group_name, [t.task.l4_name for t in tasks[:6]])
            if hint:
                purpose = hint.get("purpose") or purpose
                if isinstance(hint.get("tools"), list) and hint["tools"]:
                    tools = [str(t) for t in hint["tools"]][:6]
                generated_by = "model"

        specs.append(
            AgentSpec(
                id=f"A{index}",
                name=name,
                archetype=archetype,
                purpose=purpose,
                model_tier=str(template["tier"]),
                tools=tools,
                guardrails=_guardrails(tasks, risk),
                io_contract={
                    "in": "task_context" if archetype is Archetype.EXTRACTION else "structured_fields",
                    "out": "structured_fields" if archetype in {Archetype.EXTRACTION, Archetype.REASONING} else "artifact",
                    "schema": f"schemas/{archetype.value}_v1.json",
                },
                source_task_ids=[t.task.id for t in tasks],
                estimate=estimate,
                risk_tier=risk,
                generated_by=generated_by,
            )
        )
    return specs


def build_dependencies(specs: list[AgentSpec], scored_by_id: dict[str, ScoredTask]) -> list[AgentDependency]:
    """Edges follow archetype order within a process group, plus cross-group joins."""
    edges: list[AgentDependency] = []
    by_group: dict[str, list[AgentSpec]] = {}
    for spec in specs:
        l2 = scored_by_id[spec.source_task_ids[0]].task.l2_code
        by_group.setdefault(l2, []).append(spec)

    payloads = {
        Archetype.EXTRACTION: "normalised fields",
        Archetype.REASONING: "classified dispositions",
        Archetype.GENERATION: "draft artifact",
        Archetype.MONITORING: "obligation events",
        Archetype.ORCHESTRATION: "routing decision",
    }

    for group in by_group.values():
        chain = sorted(group, key=lambda s: ARCHETYPE_ORDER.index(s.archetype))
        for src, dst in zip(chain, chain[1:]):
            src_tasks = [scored_by_id[i] for i in src.source_task_ids]
            edges.append(
                AgentDependency(
                    source=src.id,
                    target=dst.id,
                    payload=payloads[src.archetype],
                    schema_ref=src.io_contract["schema"],
                    carries_pii=any(t.task.pii for t in src_tasks),
                    cross_tower=False,
                )
            )

    # Cross-group edges: a group's reasoning layer consumes upstream extraction
    # from the group immediately preceding it in taxonomy order. This is what
    # surfaces the honest finding that an agent cannot run unattended because
    # something upstream is human-only.
    groups = sorted(by_group.keys())
    for prev, curr in zip(groups, groups[1:]):
        src = next((s for s in by_group[prev] if s.archetype is Archetype.EXTRACTION), None)
        dst = next((s for s in by_group[curr] if s.archetype is Archetype.REASONING), None)
        if src and dst:
            src_tasks = [scored_by_id[i] for i in src.source_task_ids]
            edges.append(
                AgentDependency(
                    source=src.id,
                    target=dst.id,
                    payload="shared reference data",
                    schema_ref=src.io_contract["schema"],
                    carries_pii=any(t.task.pii for t in src_tasks),
                    cross_tower=True,
                )
            )
    return edges


def build_gates(
    specs: list[AgentSpec],
    scored_by_id: dict[str, ScoredTask],
    edges: list[AgentDependency],
    reviewer_role: str,
) -> list[HumanGate]:
    """A gate sits before any agent whose inputs carry a non-autonomous decision."""
    gates: list[HumanGate] = []
    incoming: dict[str, list[str]] = {}
    for edge in edges:
        incoming.setdefault(edge.target, []).append(edge.source)

    for spec in specs:
        tasks = [scored_by_id[i] for i in spec.source_task_ids]
        gated = [t for t in tasks if t.band is not Band.FULL_AGENT]
        if not gated:
            continue
        if spec.archetype not in {Archetype.GENERATION, Archetype.REASONING}:
            continue

        reasons: list[str] = []
        if any(t.overrides for t in tasks):
            rule = next(o.rule for t in tasks if t.overrides for o in t.overrides)
            reasons.append(f"policy cap ({rule})")
        if any(t.confidence < 0.85 for t in tasks):
            reasons.append("confidence below 0.85")
        if any(t.band is Band.HUMAN_ONLY for t in tasks):
            reasons.append("human-only activities in scope")

        review_minutes = sum(
            (t.task.avg_handle_minutes or 12) * 0.18
            for t in gated
        )

        gates.append(
            HumanGate(
                id=f"G{spec.id}",
                before_agent=spec.id,
                after_agents=incoming.get(spec.id, []),
                reason=(
                    f"{len(gated)} of {len(tasks)} source activities are not cleared for autonomous "
                    f"execution: {', '.join(reasons) or 'score below the autonomous band'}."
                ),
                triggers=[
                    "confidence below 0.85",
                    "policy override fired",
                    "novel pattern not seen in the source inventory",
                    "value above the client approval threshold",
                ],
                reviewer_role=reviewer_role,
                task_count=len(gated),
                est_review_minutes=round(review_minutes, 1),
            )
        )
    return gates
