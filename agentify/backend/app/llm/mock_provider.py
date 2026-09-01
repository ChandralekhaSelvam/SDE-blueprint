"""Deterministic offline provider.

Demo mode routes here. It returns well-formed JSON shaped exactly like a real
adjudication so every downstream code path is exercised, but it makes no
network call and costs nothing. Output is seeded from the prompt so the same
input always produces the same blueprint, which makes demos reproducible.
"""
from __future__ import annotations

import hashlib
import json

from .base import LLMResult, estimate_tokens


class MockProvider:
    name = "mock"

    def complete(self, system: str, prompt: str, model: str, max_tokens: int = 700, json_only: bool = True) -> LLMResult:
        seed = int(hashlib.sha256(prompt.encode()).hexdigest()[:8], 16)

        if "adjudicate" in system.lower():
            nudge = (seed % 13) - 6
            payload = {
                "adjustment": nudge,
                "confidence": round(0.72 + (seed % 20) / 100, 2),
                "rationale": (
                    "Adjacent activities in this process group share the same system of record "
                    "and exception pattern, which supports the deterministic band."
                ),
            }
        elif "architect" in system.lower():
            payload = {
                "name": None,
                "purpose": (
                    "Handles the grouped activities end to end, emitting a structured result "
                    "for the next stage and escalating anything outside its contract."
                ),
                "tools": ["document_store", "erp_connector", "policy_lookup"],
                "pattern": "supervisor-worker",
            }
        else:
            payload = {"ok": True}

        text = json.dumps(payload)
        return LLMResult(
            text=text,
            input_tokens=estimate_tokens(system + prompt),
            output_tokens=estimate_tokens(text),
            model=model,
            provider=self.name,
        )
