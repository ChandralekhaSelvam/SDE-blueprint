""" Generative Engine.

The Generative Engine fronts several vendors behind an OpenAI-compatible
chat/completions surface, so one client covers every model it exposes. Set
GENENGINE_BASE_URL to your tenant endpoint and map the three tiers to whichever
models your account is entitled to.
"""
from __future__ import annotations

import httpx

from .base import LLMResult, estimate_tokens


class GenEngineProvider:
    name = "genengine"

    def __init__(self, base_url: str, api_key: str, timeout: float = 60.0) -> None:
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def complete(self, system: str, prompt: str, model: str, max_tokens: int = 700, json_only: bool = True) -> LLMResult:
        if not self.base_url or not self.api_key:
            return LLMResult(text="", model=model, provider=self.name, error="GENENGINE_BASE_URL or GENENGINE_API_KEY is not set")

        body = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        }
        if json_only:
            body["response_format"] = {"type": "json_object"}

        try:
            with httpx.Client(timeout=self.timeout) as client:
                res = client.post(
                    f"{self.base_url}/chat/completions",
                    json=body,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                )
            if res.status_code >= 400:
                return LLMResult(text="", model=model, provider=self.name, error=f"HTTP {res.status_code}: {res.text[:200]}")
            data = res.json()
        except Exception as exc:  # noqa: BLE001
            return LLMResult(text="", model=model, provider=self.name, error=str(exc)[:200])

        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            return LLMResult(text="", model=model, provider=self.name, error="Unexpected response shape")

        usage = data.get("usage", {})
        return LLMResult(
            text=text,
            input_tokens=usage.get("prompt_tokens", estimate_tokens(system + prompt)),
            output_tokens=usage.get("completion_tokens", estimate_tokens(text)),
            model=model,
            provider=self.name,
        )
