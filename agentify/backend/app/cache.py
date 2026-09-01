"""Task-level result cache.

APQC activities repeat heavily across towers and clients. "Extract key clauses
from NDA" is near-identical whether the account is Unilever or CSL. Caching the
scored result and its rationale is the single largest token saving after the
deterministic path itself.

The similarity function is Jaccard overlap on a normalised token bag rather
than a vector index. That is a deliberate trade: no embedding call means the
cache lookup is itself free, which matters when the whole point is to avoid
spend. Swap in pgvector for production without changing the interface.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
from dataclasses import dataclass
from typing import Any

STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "for", "in", "on", "with", "from",
    "by", "at", "as", "is", "are", "be", "manage", "process",
}

_lock = threading.Lock()


def _tokens(text: str) -> frozenset[str]:
    words = re.findall(r"[a-z]+", text.lower())
    return frozenset(w for w in words if w not in STOPWORDS and len(w) > 2)


@dataclass
class CacheHit:
    payload: dict[str, Any]
    similarity: float
    source_key: str


class TaskCache:
    def __init__(self, path: str, threshold: float = 0.82) -> None:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.path = path
        self.threshold = threshold
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS task_cache ("
            " key TEXT PRIMARY KEY,"
            " tokens TEXT NOT NULL,"
            " payload TEXT NOT NULL,"
            " hits INTEGER DEFAULT 0)"
        )
        self._conn.commit()
        self._index: list[tuple[str, frozenset[str], dict[str, Any]]] = []
        self._load()

    def _load(self) -> None:
        rows = self._conn.execute("SELECT key, tokens, payload FROM task_cache").fetchall()
        self._index = [(k, frozenset(json.loads(t)), json.loads(p)) for k, t, p in rows]

    def lookup(self, text: str) -> CacheHit | None:
        """Cheapest first: exact token-set match, then best overlap above threshold."""
        probe = _tokens(text)
        if not probe:
            return None
        best: CacheHit | None = None
        for key, tokens, payload in self._index:
            if not tokens:
                continue
            if tokens == probe:
                return CacheHit(payload=payload, similarity=1.0, source_key=key)
            union = len(probe | tokens)
            if not union:
                continue
            sim = len(probe & tokens) / union
            if sim >= self.threshold and (best is None or sim > best.similarity):
                best = CacheHit(payload=payload, similarity=round(sim, 3), source_key=key)
        return best

    def put(self, key: str, text: str, payload: dict[str, Any]) -> None:
        tokens = _tokens(text)
        with _lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO task_cache (key, tokens, payload) VALUES (?, ?, ?)",
                (key, json.dumps(sorted(tokens)), json.dumps(payload)),
            )
            self._conn.commit()
            self._index.append((key, tokens, payload))

    def stats(self) -> dict[str, int]:
        return {"entries": len(self._index)}

    def clear(self) -> None:
        with _lock:
            self._conn.execute("DELETE FROM task_cache")
            self._conn.commit()
            self._index = []
