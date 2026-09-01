"""Provider-neutral model interface.

Every provider returns the same LLMResult so the router, the cost report and
the pipeline never branch on vendor. Adding a provider means implementing one
method.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class LLMResult:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    provider: str = ""
    cached: bool = False
    error: str | None = None
    meta: dict = field(default_factory=dict)

    @property
    def tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class Provider(Protocol):
    name: str

    def complete(
        self,
        system: str,
        prompt: str,
        model: str,
        max_tokens: int = 700,
        json_only: bool = True,
    ) -> LLMResult: ...


def estimate_tokens(text: str) -> int:
    """Cheap token estimate for providers that do not report usage."""
    return max(1, len(text) // 4)
