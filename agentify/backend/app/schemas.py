"""Data contracts for the blueprint pipeline.

Every object the API returns is defined here. The four DoD clauses map onto
AgentSpec (catalog), AgentDependency, HumanGate and AutomationEstimate.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class Band(str, Enum):
    FULL_AGENT = "full_agent"
    HITL = "hitl"
    HUMAN_ONLY = "human_only"


class Archetype(str, Enum):
    EXTRACTION = "extraction"
    REASONING = "reasoning"
    GENERATION = "generation"
    MONITORING = "monitoring"
    ORCHESTRATION = "orchestration"


class Resolution(str, Enum):
    """How a task's score was reached. Drives the token-optimisation report."""

    DETERMINISTIC = "deterministic"
    CACHE = "cache"
    SMALL_MODEL = "small_model"
    LARGE_MODEL = "large_model"


class Task(BaseModel):
    """One L4 activity from the client's process inventory."""

    id: str
    l1_code: str
    l1_name: str
    l2_code: str
    l2_name: str
    l3_code: str
    l3_name: str
    l4_code: str
    l4_name: str

    volume_per_month: float | None = None
    avg_handle_minutes: float | None = None
    fte: float | None = None
    rule_based: float | None = Field(default=None, description="0-100")
    pii: bool | None = None
    safety_critical: bool | None = None
    executive_judgement: bool | None = None
    systems: str | None = None
    exception_rate: float | None = None
    notes: str | None = None

    @property
    def annual_hours(self) -> float:
        if self.fte is not None:
            return self.fte * 1720.0
        if self.volume_per_month is not None and self.avg_handle_minutes is not None:
            return self.volume_per_month * 12.0 * self.avg_handle_minutes / 60.0
        return 0.0


class DimensionScore(BaseModel):
    key: str
    label: str
    weight: float
    raw: float
    weighted: float
    basis: str


class Override(BaseModel):
    rule: str
    cap: float
    reason: str
    source: str


class Evidence(BaseModel):
    kind: Literal["computed", "retrieved", "policy"]
    label: str
    detail: str
    source: str
    score: float | None = None


class ScoredTask(BaseModel):
    task: Task
    dimensions: list[DimensionScore]
    raw_score: float
    score: float
    band: Band
    confidence: float
    resolution: Resolution
    overrides: list[Override] = []
    evidence: list[Evidence] = []
    rationale: str
    archetype: Archetype
    tokens: int = 0
    cost_usd: float = 0.0
    human_override: dict[str, Any] | None = None


class AutomationEstimate(BaseModel):
    """DoD clause: per-agent automation estimate."""

    source_task_count: int
    annual_hours_today: float
    annual_hours_after: float
    hours_removed: float
    fte_today: float
    fte_after: float
    automation_pct: float
    band_split: dict[str, int]


class AgentSpec(BaseModel):
    """DoD clause: structured agent catalog."""

    id: str
    name: str
    archetype: Archetype
    purpose: str
    model_tier: str
    tools: list[str]
    guardrails: list[str]
    io_contract: dict[str, str]
    source_task_ids: list[str]
    estimate: AutomationEstimate
    risk_tier: str
    generated_by: str


class AgentDependency(BaseModel):
    """DoD clause: dependencies."""

    source: str
    target: str
    payload: str
    schema_ref: str
    carries_pii: bool
    cross_tower: bool


class HumanGate(BaseModel):
    """DoD clause: human-in-the-loop points."""

    id: str
    before_agent: str
    after_agents: list[str]
    reason: str
    triggers: list[str]
    reviewer_role: str
    task_count: int
    est_review_minutes: float


class TraceRow(BaseModel):
    """DoD clause: each traceable to its source task."""

    task_id: str
    l4_code: str
    l4_name: str
    l3_code: str
    l1_code: str
    agent_id: str
    agent_name: str
    band: Band
    score: float
    gate_id: str | None
    resolution: Resolution
    evidence: list[Evidence]
    overrides: list[Override]


class CostReport(BaseModel):
    total_tokens: int
    total_cost_usd: float
    naive_cost_usd: float
    saved_pct: float
    cost_per_1k_tasks: float
    by_resolution: dict[str, int]
    by_stage: list[dict[str, Any]]
    cache_hit_rate: float
    llm_calls: int
    llm_calls_avoided: int


class Bridge(BaseModel):
    """Hours-weighted headcount bridge."""

    fte_today: float
    fte_after: float
    steps: list[dict[str, Any]]
    residuals: dict[str, float]


class Blueprint(BaseModel):
    run_id: str
    industry: str
    function: str
    created_at: str
    provider: str
    mode: str
    task_count: int
    agents: list[AgentSpec]
    dependencies: list[AgentDependency]
    gates: list[HumanGate]
    traceability: list[TraceRow]
    scored_tasks: list[ScoredTask]
    cost: CostReport
    bridge: Bridge
    band_totals: dict[str, int]
    warnings: list[str] = []


class StageEvent(BaseModel):
    run_id: str
    stage_id: int
    stage: str
    status: Literal["queued", "running", "done", "halted", "failed", "retrying"]
    detail: str = ""
    progress: float = 0.0
    tokens: int = 0
    cost_usd: float = 0.0
    model: str = ""
    elapsed_ms: int = 0
    payload_out: str = ""
    retries: int = 0
