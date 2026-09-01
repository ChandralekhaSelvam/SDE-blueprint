"""Google Cloud Vertex AI.

Uses the REST generateContent surface with an access token, so the only GCP
dependency is google-auth. On Cloud Run or GKE the attached service account is
picked up automatically; locally, `gcloud auth application-default login` is
enough. No SDK pinning, no vendored client.
"""
from __future__ import annotations

import json

import httpx

from .base import LLMResult, estimate_tokens


class VertexProvider:
    name = "vertex"

    def __init__(self, project: str, location: str = "us-central1", timeout: float = 60.0) -> None:
        self.project = project
        self.location = location
        self.timeout = timeout
        self._credentials = None

    def _token(self) -> str | None:
        try:
            import google.auth
            from google.auth.transport.requests import Request

            if self._credentials is None:
                self._credentials, _ = google.auth.default(
                    scopes=["https://www.googleapis.com/auth/cloud-platform"]
                )
            if not self._credentials.valid:
                self._credentials.refresh(Request())
            return self._credentials.token
        except Exception:  # noqa: BLE001 - reported as a provider error, not a crash
            return None

    def complete(self, system: str, prompt: str, model: str, max_tokens: int = 700, json_only: bool = True) -> LLMResult:
        if not self.project:
            return LLMResult(text="", model=model, provider=self.name, error="GCP_PROJECT is not set")

        token = self._token()
        if not token:
            return LLMResult(
                text="", model=model, provider=self.name,
                error="No Google credentials. Run 'gcloud auth application-default login' or attach a service account.",
            )

        url = (
            f"https://{self.location}-aiplatform.googleapis.com/v1/projects/{self.project}"
            f"/locations/{self.location}/publishers/google/models/{model}:generateContent"
        )
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0},
        }
        if json_only:
            body["generationConfig"]["responseMimeType"] = "application/json"

        try:
            with httpx.Client(timeout=self.timeout) as client:
                res = client.post(url, json=body, headers={"Authorization": f"Bearer {token}"})
            if res.status_code >= 400:
                return LLMResult(text="", model=model, provider=self.name, error=f"HTTP {res.status_code}: {res.text[:200]}")
            data = res.json()
        except Exception as exc:  # noqa: BLE001
            return LLMResult(text="", model=model, provider=self.name, error=str(exc)[:200])

        try:
            parts = data["candidates"][0]["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts)
        except (KeyError, IndexError, TypeError):
            return LLMResult(text="", model=model, provider=self.name, error=f"Unexpected response: {json.dumps(data)[:200]}")

        usage = data.get("usageMetadata", {})
        return LLMResult(
            text=text,
            input_tokens=usage.get("promptTokenCount", estimate_tokens(system + prompt)),
            output_tokens=usage.get("candidatesTokenCount", estimate_tokens(text)),
            model=model,
            provider=self.name,
        )
