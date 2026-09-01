"""The nine-agent pipeline.

One supervisor and eight workers, each owning a single stage with its own
contract. Stages emit StageEvent objects as they run, which the API forwards
over SSE and the frontend renders as the live pipeline graph.

Structured as an explicit stage list rather than a graph library so the whole
run is inspectable, replayable from the event log, and has no orchestration
dependency to install. Swapping in LangGraph means implementing `run` as a
StateGraph over the same stage functions; the events and contracts do not change.
"""
from __future__ import annotations

import time
import uuid
from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Any

from ..cache import TaskCache
from ..config import Settings
from ..llm.router import Router
from ..pii import mask_payload
from ..policy import load_pack
from ..schemas import (
    AgentSpec,
    Band,
    Blueprint,
    Bridge,
    CostReport,
    Evidence,
    Resolution,
    ScoredTask,
    StageEvent,
    Task,
    TraceRow,
)
from ..scoring import needs_adjudication, score_task
from .architect import build_catalog, build_dependencies, build_gates

STAGES = [
    (0, "Orchestrator"),
    (1, "Ingestion and parsing"),
    (2, "Feature extraction"),
    (3, "Classification and scoring"),
    (4, "Risk and compliance"),
    (5, "Architecture design"),
    (6, "Guardrail configuration"),
    (7, "Explainability"),
    (8, "Traceability and docs"),
]

ADJUDICATE_SYSTEM = (
    "You adjudicate automation scores for business process activities. A deterministic "
    "engine has already scored the activity from 0 to 100 using seven weighted dimensions. "
    "Your job is only to nudge that score within plus or minus 12 points where the "
    "deterministic features are thin, and to explain why in one sentence. "
    "Reply with JSON only: {\"adjustment\": int, \"confidence\": float, \"rationale\": string}."
)

ARCHITECT_SYSTEM = (
    "You name and describe agents in a multi-agent architecture for shared services. "
    "Given an agent's archetype, its process group and a sample of the activities it "
    "covers, write a single-sentence purpose and suggest up to five concrete tool or "
    "connector names. Reply with JSON only: {\"purpose\": string, \"tools\": [string]}."
)


class Pipeline:
    def __init__(self, settings: Settings, cache: TaskCache | None = None) -> None:
        self.settings = settings
        self.cache = cache
        self.router = Router(settings)

    # ---------------------------------------------------------------- helpers

    def _event(self, stage_id: int, status: str, **kw: Any) -> StageEvent:
        return StageEvent(
            run_id=self.run_id,
            stage_id=stage_id,
            stage=STAGES[stage_id][1],
            status=status,
            tokens=self.router.tokens,
            cost_usd=self.router.spent,
            **kw,
        )

    def _adjudicate(self, scored: ScoredTask) -> ScoredTask:
        """Ask a model to nudge a borderline score. Failure is not an error."""
        text = f"{scored.task.l3_name} / {scored.task.l4_name}"

        if self.cache is not None and self.settings.enable_cache:
            hit = self.cache.lookup(text)
            if hit is not None:
                scored.score = float(hit.payload["score"])
                scored.band = self._band(scored.score)
                scored.resolution = Resolution.CACHE
                scored.evidence.append(
                    Evidence(
                        kind="computed",
                        label=f"Cache hit at {hit.similarity:.2f} similarity",
                        detail=f"Reused the adjudicated result for '{hit.payload.get('label', hit.source_key)}'.",
                        source="cache.py",
                        score=hit.similarity,
                    )
                )
                return scored

        masked, _ = mask_payload({"activity": text, "notes": scored.task.notes})
        prompt = (
            f"Activity: {masked['activity']}\n"
            f"Notes: {masked.get('notes') or 'none'}\n"
            f"Deterministic score: {scored.raw_score:.0f}\n"
            f"Leading dimensions: "
            + "; ".join(f"{d.label} {d.raw:.0f} ({d.basis})" for d in scored.dimensions[:3])
        )
        tier = "medium" if scored.confidence < 0.7 else "small"
        before = len(self.router.calls)
        payload = self.router.call_json("Classification and scoring", tier, ADJUDICATE_SYSTEM, prompt, max_tokens=220)

        if payload is None:
            return scored  # deterministic answer stands

        adjustment = max(-12, min(12, float(payload.get("adjustment", 0))))
        scored.score = round(max(0.0, min(100.0, scored.score + adjustment)), 1)
        scored.band = self._band(scored.score)
        scored.confidence = float(payload.get("confidence", scored.confidence))
        scored.resolution = Resolution.SMALL_MODEL if tier == "small" else Resolution.LARGE_MODEL
        rationale = str(payload.get("rationale", "")).strip()
        if rationale:
            scored.rationale += f" Adjudicated: {rationale}"
        call = self.router.calls[before] if len(self.router.calls) > before else None
        if call:
            scored.tokens = call.tokens
            scored.cost_usd = call.cost_usd
        scored.evidence.append(
            Evidence(
                kind="retrieved",
                label=f"Model adjudication ({self.router.provider_name})",
                detail=rationale or "No rationale returned.",
                source=call.model if call else "unknown",
            )
        )

        if self.cache is not None and self.settings.enable_cache:
            self.cache.put(scored.task.id, text, {"score": scored.score, "label": text})
        return scored

    def _band(self, score: float) -> Band:
        bands = self.pack["bands"]
        if score >= bands["full_agent"]:
            return Band.FULL_AGENT
        if score >= bands["hitl"]:
            return Band.HITL
        return Band.HUMAN_ONLY

    def _describe_agent(self, name: str, archetype: str, group: str, samples: list[str]):
        if not self.router.budget_left():
            return None
        prompt = (
            f"Agent name: {name}\nArchetype: {archetype}\nProcess group: {group}\n"
            f"Sample activities: {'; '.join(samples)}"
        )
        return self.router.call_json("Architecture design", "large", ARCHITECT_SYSTEM, prompt, max_tokens=320)

    # ------------------------------------------------------------------- run

    def run(self, tasks: list[Task], industry: str, function: str, warnings: list[str]) -> Iterator[StageEvent | Blueprint]:
        self.run_id = uuid.uuid4().hex[:12]
        self.pack = load_pack(industry)
        residuals = self.pack.get("residuals", {"full_agent": 0.04, "hitl": 0.15, "human_only": 0.80})
        started = time.time()

        yield self._event(0, "running", detail=f"Sequencing 8 workers over {len(tasks)} activities.")

        # 1. Ingestion --------------------------------------------------------
        t0 = time.time()
        yield self._event(1, "running", detail="Validating schema and normalising the L1 to L4 hierarchy.")
        redactions = 0
        for task in tasks:
            cleaned, hits = mask_payload({"name": task.l4_name, "notes": task.notes})
            task.l4_name = cleaned["name"]
            task.notes = cleaned.get("notes") or None
            redactions += sum(hits.values())
        detail = f"{len(tasks)} activities normalised."
        if redactions:
            detail += f" {redactions} PII span(s) masked before any further processing."
        yield self._event(1, "done", detail=detail, progress=1.0, elapsed_ms=int((time.time() - t0) * 1000),
                          payload_out=f"{len(tasks)} normalised activities", model="none")

        # 2. Feature extraction ----------------------------------------------
        t0 = time.time()
        yield self._event(2, "running", detail="Deriving scoring features from the inventory.")
        complete = sum(1 for t in tasks if t.annual_hours > 0)
        yield self._event(
            2, "done",
            detail=f"{complete} of {len(tasks)} activities carry effort data. The rest are scored on inferred features and flagged as a range.",
            progress=1.0, elapsed_ms=int((time.time() - t0) * 1000),
            payload_out=f"{len(tasks)} feature vectors", model="none",
        )

        # 3. Classification and scoring ---------------------------------------
        t0 = time.time()
        yield self._event(3, "running", detail="Applying the seven weighted dimensions.")
        scored: list[ScoredTask] = []
        adjudicated = 0
        for index, task in enumerate(tasks):
            result = score_task(task, self.pack)
            if needs_adjudication(result, self.settings.ambiguous_low, self.settings.ambiguous_high, self.settings.confidence_floor):
                result = self._adjudicate(result)
                adjudicated += 1
            scored.append(result)
            if index % 25 == 0 and index:
                yield self._event(3, "running", detail=f"{index} of {len(tasks)} scored.", progress=index / len(tasks))

        avoided = len(tasks) - adjudicated
        yield self._event(
            3, "done",
            detail=f"{avoided} of {len(tasks)} activities resolved without a model call. {adjudicated} reached the ambiguous window.",
            progress=1.0, elapsed_ms=int((time.time() - t0) * 1000),
            payload_out=f"{len(scored)} scored activities", model=self.settings.tiers.small,
        )

        # 4. Risk and compliance ----------------------------------------------
        t0 = time.time()
        yield self._event(4, "running", detail="Independently reviewing high-impact classifications.")
        capped = sum(1 for s in scored if s.overrides)
        vetoed = 0
        for item in scored:
            # Second line of defence: a high-scoring task carrying a policy flag
            # is downgraded regardless of what the scorer or a model concluded.
            if item.band is Band.FULL_AGENT and (item.task.pii or item.task.safety_critical):
                item.band = Band.HITL
                item.score = min(item.score, 74.0)
                item.evidence.append(
                    Evidence(kind="policy", label="Risk agent veto",
                             detail="Independently downgraded from autonomous: the activity carries a policy flag.",
                             source="agents/pipeline.py: risk review")
                )
                vetoed += 1
        yield self._event(
            4, "done",
            detail=f"{capped} score(s) capped by policy, {vetoed} autonomous classification(s) vetoed on review.",
            progress=1.0, elapsed_ms=int((time.time() - t0) * 1000),
            payload_out=f"{capped + vetoed} governed decisions", model="none",
        )

        # 5. Architecture design ----------------------------------------------
        t0 = time.time()
        yield self._event(5, "running", detail="Grouping activities into agents and generating specifications.")
        describe = self._describe_agent if self.settings.live else None
        specs: list[AgentSpec] = build_catalog(scored, residuals, describe=describe)
        scored_by_id = {s.task.id: s for s in scored}
        edges = build_dependencies(specs, scored_by_id)
        yield self._event(
            5, "done",
            detail=f"{len(specs)} agents with {len(edges)} dependency edges.",
            progress=1.0, elapsed_ms=int((time.time() - t0) * 1000),
            payload_out=f"{len(specs)} agent specifications", model=self.settings.tiers.large if self.settings.live else "none",
        )

        # 6. Guardrail configuration ------------------------------------------
        t0 = time.time()
        yield self._event(6, "running", detail="Sizing guardrail configs to each agent's risk tier.")
        gates = build_gates(specs, scored_by_id, edges, self.pack.get("reviewer_role", "Process owner"))
        rails = sum(len(s.guardrails) for s in specs)
        yield self._event(
            6, "done",
            detail=f"{rails} guardrails attached across {len(specs)} agents. {len(gates)} human gate(s) placed.",
            progress=1.0, elapsed_ms=int((time.time() - t0) * 1000),
            payload_out=f"{len(gates)} gates", model="none",
        )

        # 7. Explainability ----------------------------------------------------
        t0 = time.time()
        yield self._event(7, "running", detail="Assembling criteria-level rationale and evidence.")
        unsourced = sum(1 for s in scored if not s.evidence)
        yield self._event(
            7, "done",
            detail=f"Every one of {len(scored)} classifications carries a rationale and at least one evidence record."
            if not unsourced else f"{unsourced} classification(s) lack evidence and are flagged for review.",
            progress=1.0, elapsed_ms=int((time.time() - t0) * 1000),
            payload_out=f"{sum(len(s.evidence) for s in scored)} evidence records", model="none",
        )

        # 8. Traceability and docs ---------------------------------------------
        t0 = time.time()
        yield self._event(8, "running", detail="Building the L1 to L4 to agent matrix.")
        gate_by_agent = {g.before_agent: g.id for g in gates}
        agent_by_task: dict[str, AgentSpec] = {}
        for spec in specs:
            for task_id in spec.source_task_ids:
                agent_by_task[task_id] = spec

        trace: list[TraceRow] = []
        for item in scored:
            spec = agent_by_task.get(item.task.id)
            trace.append(
                TraceRow(
                    task_id=item.task.id,
                    l4_code=item.task.l4_code,
                    l4_name=item.task.l4_name,
                    l3_code=item.task.l3_code,
                    l1_code=item.task.l1_code,
                    agent_id=spec.id if spec else "unassigned",
                    agent_name=spec.name if spec else "Unassigned",
                    band=item.band,
                    score=item.score,
                    gate_id=gate_by_agent.get(spec.id) if spec else None,
                    resolution=item.resolution,
                    evidence=item.evidence,
                    overrides=item.overrides,
                )
            )
        yield self._event(
            8, "done",
            detail=f"{len(trace)} rows, every one traceable to its source activity.",
            progress=1.0, elapsed_ms=int((time.time() - t0) * 1000),
            payload_out=f"{len(trace)} trace rows", model="none",
        )

        # Reports ---------------------------------------------------------------
        cost = self._cost_report(scored, len(tasks))
        bridge = self._bridge(scored, residuals)
        band_totals = {b.value: sum(1 for s in scored if s.band is b) for b in Band}

        if self.router.degraded_reason:
            warnings = warnings + [self.router.degraded_reason]

        yield self._event(0, "done", detail=f"Run complete in {time.time() - started:.1f}s.", progress=1.0)

        yield Blueprint(
            run_id=self.run_id,
            industry=industry,
            function=function,
            created_at=datetime.now(timezone.utc).isoformat(),
            provider=self.router.provider_name,
            mode=self.settings.run_mode,
            task_count=len(tasks),
            agents=specs,
            dependencies=edges,
            gates=gates,
            traceability=trace,
            scored_tasks=scored,
            cost=cost,
            bridge=bridge,
            band_totals=band_totals,
            warnings=warnings,
        )

    # --------------------------------------------------------------- reports

    def _cost_report(self, scored: list[ScoredTask], task_count: int) -> CostReport:
        by_resolution = {r.value: sum(1 for s in scored if s.resolution is r) for r in Resolution}
        llm_calls = by_resolution["small_model"] + by_resolution["large_model"]
        avoided = task_count - llm_calls

        # The naive baseline is one medium-tier call per activity plus one large
        # call per agent, which is what a prompt-only implementation would spend.
        naive_tokens = task_count * 1400
        naive = naive_tokens / 1_000_000 * self.settings.tiers.price_medium
        actual = self.router.spent
        saved = 0.0 if naive <= 0 else max(0.0, (1 - actual / naive)) * 100

        cache_hits = by_resolution["cache"]
        denominator = max(1, cache_hits + llm_calls)

        return CostReport(
            total_tokens=self.router.tokens,
            total_cost_usd=round(actual, 4),
            naive_cost_usd=round(naive, 4),
            saved_pct=round(saved, 1),
            cost_per_1k_tasks=round(actual / max(task_count, 1) * 1000, 4),
            by_resolution=by_resolution,
            by_stage=self.router.by_stage(),
            cache_hit_rate=round(cache_hits / denominator * 100, 1),
            llm_calls=llm_calls,
            llm_calls_avoided=avoided,
        )

    def _bridge(self, scored: list[ScoredTask], residuals: dict[str, float]) -> Bridge:
        """Hours-weighted effort bridge.

        Task counts and hour counts diverge sharply, which is why a 31 percent
        autonomous share can still remove most of the effort: a small set of
        high-volume activities carries the majority of the hours.
        """
        hours = {b.value: 0.0 for b in Band}
        for item in scored:
            hours[item.band.value] += item.task.annual_hours
        total = sum(hours.values())
        fte_today = total / 1720.0

        steps = []
        running = fte_today
        for band, label in [
            ("full_agent", "Autonomous execution"),
            ("hitl", "Reviewed, not drafted"),
            ("human_only", "AI-assisted human work"),
        ]:
            band_fte = hours[band] / 1720.0
            removed = band_fte * (1 - residuals[band])
            steps.append(
                {
                    "band": band,
                    "label": label,
                    "fte_in_band": round(band_fte, 1),
                    "share_of_hours": round(hours[band] / total * 100, 1) if total else 0.0,
                    "residual": residuals[band],
                    "fte_removed": round(removed, 1),
                    "from": round(running, 1),
                    "to": round(running - removed, 1),
                }
            )
            running -= removed

        return Bridge(
            fte_today=round(fte_today, 1),
            fte_after=round(running, 1),
            steps=steps,
            residuals=residuals,
        )
