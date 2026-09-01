"""Anthropic Messages API.

Static context (rubric, taxonomy, policy pack) goes in the system block with a
cache_control breakpoint. It is identical on every call in a run, so paying for
it once instead of 300 times is the largest single prompt saving available.
"""
from __future__ import annotations

import httpx

from .base import LLMResult, estimate_tokens

API_URL = "https://api.anthropic.com/v1/messages"
VERSION = "2023-06-01"


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str, timeout: float = 45.0) -> None:
        self.api_key = api_key
        self.timeout = timeout

    def complete(self, system: str, prompt: str, model: str, max_tokens: int = 700, json_only: bool = True) -> LLMResult:
        if not self.api_key:
            return LLMResult(text="", model=model, provider=self.name, error="ANTHROPIC_API_KEY is not set")

        body = {
            "model": model,
            "max_tokens": max_tokens,
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": prompt}],
        }
        if json_only:
            # Prefilling the opening brace forces JSON without a schema round trip.
            body["messages"].append({"role": "assistant", "content": "{"})

        try:
            with httpx.Client(timeout=self.timeout) as client:
                res = client.post(
                    API_URL,
                    json=body,
                    headers={
                        "x-api-key": self.api_key,
                        "anthropic-version": VERSION,
                        "content-type": "application/json",
                    },
                )
            if res.status_code >= 400:
                return LLMResult(text="", model=model, provider=self.name, error=f"HTTP {res.status_code}: {res.text[:200]}")
            data = res.json()
        except Exception as exc:  # noqa: BLE001 - degraded, never fatal
            return LLMResult(text="", model=model, provider=self.name, error=str(exc)[:200])

        parts = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
        text = "".join(parts)
        if json_only and not text.lstrip().startswith("{"):
            text = "{" + text

        usage = data.get("usage", {})
        return LLMResult(
            text=text,
            input_tokens=usage.get("input_tokens", estimate_tokens(system + prompt)),
            output_tokens=usage.get("output_tokens", estimate_tokens(text)),
            model=model,
            provider=self.name,
            meta={"cache_read": usage.get("cache_read_input_tokens", 0)},
        )
