"""Runtime configuration.

Two axes the operator controls:

  RUN_MODE  = demo | live      whether any network call is made at all
  LLM_PROVIDER = mock | anthropic | vertex | genengine

Demo mode is not a stub. The deterministic scorer produces a complete,
DoD-satisfying blueprint with zero model calls, so the whole app is usable
with no credentials and no spend. Live mode adds model adjudication only
where the deterministic path is genuinely uncertain.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def _flag(key: str, default: bool) -> bool:
    raw = _env(key)
    if not raw:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


@dataclass
class ModelTiers:
    """Three tiers. The router never sends a cheap task to an expensive tier."""

    small: str
    medium: str
    large: str

    # USD per 1M tokens, blended input/output. Used for the cost report.
    price_small: float = 0.80
    price_medium: float = 4.50
    price_large: float = 22.00


PROVIDER_DEFAULTS: dict[str, ModelTiers] = {
    "mock": ModelTiers("mock-small", "mock-medium", "mock-large", 0.80, 4.50, 22.00),
    "anthropic": ModelTiers(
        _env("ANTHROPIC_MODEL_SMALL", "claude-haiku-4-5-20251001"),
        _env("ANTHROPIC_MODEL_MEDIUM", "claude-sonnet-5"),
        _env("ANTHROPIC_MODEL_LARGE", "claude-opus-5"),
        0.80, 4.50, 22.00,
    ),
    "vertex": ModelTiers(
        _env("VERTEX_MODEL_SMALL", "gemini-2.5-flash-lite"),
        _env("VERTEX_MODEL_MEDIUM", "gemini-2.5-flash"),
        _env("VERTEX_MODEL_LARGE", "gemini-2.5-pro"),
        0.20, 0.90, 6.00,
    ),
    "genengine": ModelTiers(
        _env("GENENGINE_MODEL_SMALL", "gpt-4o-mini"),
        _env("GENENGINE_MODEL_MEDIUM", "gpt-4o"),
        _env("GENENGINE_MODEL_LARGE", "claude-sonnet-4"),
        0.60, 5.00, 15.00,
    ),
}


@dataclass
class Settings:
    run_mode: str = field(default_factory=lambda: _env("RUN_MODE", "demo").lower())
    provider: str = field(default_factory=lambda: _env("LLM_PROVIDER", "mock").lower())

    # Adjudication window. Scores outside this range never reach a model.
    ambiguous_low: float = float(_env("AMBIGUOUS_LOW", "55"))
    ambiguous_high: float = float(_env("AMBIGUOUS_HIGH", "80"))
    confidence_floor: float = float(_env("CONFIDENCE_FLOOR", "0.85"))

    # Hard budget. The router downgrades tiers rather than overspend.
    max_llm_calls: int = int(_env("MAX_LLM_CALLS", "60"))
    budget_usd: float = float(_env("BUDGET_USD", "2.00"))

    enable_cache: bool = field(default_factory=lambda: _flag("ENABLE_CACHE", True))
    enable_l3_rollup: bool = field(default_factory=lambda: _flag("ENABLE_L3_ROLLUP", True))

    data_dir: str = field(default_factory=lambda: _env("DATA_DIR", "./data"))
    policy_dir: str = field(default_factory=lambda: _env("POLICY_DIR", "./policy"))
    cors_origins: str = field(default_factory=lambda: _env("CORS_ORIGINS", "*"))

    anthropic_key: str = field(default_factory=lambda: _env("ANTHROPIC_API_KEY"))
    genengine_base: str = field(default_factory=lambda: _env("GENENGINE_BASE_URL"))
    genengine_key: str = field(default_factory=lambda: _env("GENENGINE_API_KEY"))
    gcp_project: str = field(default_factory=lambda: _env("GCP_PROJECT"))
    gcp_location: str = field(default_factory=lambda: _env("GCP_LOCATION", "us-central1"))

    @property
    def tiers(self) -> ModelTiers:
        return PROVIDER_DEFAULTS.get(self.provider, PROVIDER_DEFAULTS["mock"])

    @property
    def live(self) -> bool:
        return self.run_mode == "live" and self.provider != "mock"

    def describe(self) -> dict[str, object]:
        return {
            "run_mode": self.run_mode,
            "provider": self.provider,
            "live": self.live,
            "tiers": {
                "small": self.tiers.small,
                "medium": self.tiers.medium,
                "large": self.tiers.large,
            },
            "ambiguous_window": [self.ambiguous_low, self.ambiguous_high],
            "confidence_floor": self.confidence_floor,
            "budget_usd": self.budget_usd,
            "max_llm_calls": self.max_llm_calls,
            "cache": self.enable_cache,
            "l3_rollup": self.enable_l3_rollup,
        }


settings = Settings()
