"""Model router and spend meter.

Two jobs. Pick the cheapest tier that can do the work, and stop the run from
overspending. Every call is recorded so the cost report is an aggregation of
real events rather than an estimate written after the fact.

The router degrades rather than fails: over budget, out of calls, provider
error, missing credentials all resolve to "keep the deterministic answer".
That is what lets the app run end to end on a low-tier model, or on none.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from ..config import Settings
from .base import LLMResult
from .mock_provider import MockProvider


@dataclass
class CallRecord:
    stage: str
    tier: str
    model: str
    tokens: int
    cost_usd: float
    ok: bool
    error: str | None = None


@dataclass
class Router:
    settings: Settings
    calls: list[CallRecord] = field(default_factory=list)
    degraded_reason: str | None = None

    def __post_init__(self) -> None:
        self._provider = self._build_provider()

    def _build_provider(self):
        if not self.settings.live:
            return MockProvider()
        provider = self.settings.provider
        if provider == "anthropic":
            from .anthropic_provider import AnthropicProvider

            return AnthropicProvider(self.settings.anthropic_key)
        if provider == "vertex":
            from .vertex_provider import VertexProvider

            return VertexProvider(self.settings.gcp_project, self.settings.gcp_location)
        if provider == "genengine":
            from .genengine_provider import GenEngineProvider

            return GenEngineProvider(self.settings.genengine_base, self.settings.genengine_key)
        return MockProvider()

    @property
    def provider_name(self) -> str:
        return getattr(self._provider, "name", "mock")

    @property
    def spent(self) -> float:
        return round(sum(c.cost_usd for c in self.calls), 6)

    @property
    def tokens(self) -> int:
        return sum(c.tokens for c in self.calls)

    def _price(self, tier: str) -> float:
        tiers = self.settings.tiers
        return {"small": tiers.price_small, "medium": tiers.price_medium, "large": tiers.price_large}[tier]

    def _model(self, tier: str) -> str:
        tiers = self.settings.tiers
        return {"small": tiers.small, "medium": tiers.medium, "large": tiers.large}[tier]

    def budget_left(self) -> bool:
        if len(self.calls) >= self.settings.max_llm_calls:
            self.degraded_reason = f"Call ceiling reached ({self.settings.max_llm_calls}). Remaining tasks kept their deterministic score."
            return False
        if self.spent >= self.settings.budget_usd:
            self.degraded_reason = f"Budget of ${self.settings.budget_usd:.2f} reached. Remaining tasks kept their deterministic score."
            return False
        return True

    def call_json(self, stage: str, tier: str, system: str, prompt: str, max_tokens: int = 500) -> dict | None:
        """Return parsed JSON, or None if the call did not happen or did not parse.

        None is a normal outcome, not an error. Callers must already hold a
        usable deterministic answer before asking the router for an opinion.
        """
        if not self.budget_left():
            return None

        model = self._model(tier)
        result: LLMResult = self._provider.complete(system, prompt, model, max_tokens=max_tokens, json_only=True)
        cost = result.tokens / 1_000_000 * self._price(tier)

        if result.error:
            self.calls.append(CallRecord(stage, tier, model, 0, 0.0, ok=False, error=result.error))
            self.degraded_reason = f"{self.provider_name} unavailable: {result.error}. Falling back to deterministic scoring."
            return None

        self.calls.append(CallRecord(stage, tier, model, result.tokens, round(cost, 6), ok=True))

        text = result.text.strip()
        if text.startswith("```"):
            text = text.strip("`")
            text = text.split("\n", 1)[-1] if "\n" in text else text
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start, end = text.find("{"), text.rfind("}")
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    return None
            return None

    def by_stage(self) -> list[dict]:
        agg: dict[tuple[str, str], dict] = {}
        for call in self.calls:
            key = (call.stage, call.model)
            row = agg.setdefault(key, {"stage": call.stage, "model": call.model, "tier": call.tier, "tokens": 0, "cost_usd": 0.0, "calls": 0, "errors": 0})
            row["tokens"] += call.tokens
            row["cost_usd"] = round(row["cost_usd"] + call.cost_usd, 6)
            row["calls"] += 1
            row["errors"] += 0 if call.ok else 1
        return list(agg.values())
