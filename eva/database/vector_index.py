"""Reusable semantic vector index backed by SQLite + EmbeddingEngine.

Each instance manages a `{prefix}_semantic_index` table.
Reusable by any domain store (journal, people, knowledge, etc.).
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from config import logger
from eva.database.db import SQLiteHandler
from eva.database.embeddings import EmbeddingEngine

# Recency half-life in days — after this many days, recency boost halves.
_RECENCY_HALF_LIFE_DAYS = 14.0


def _to_blob(vector: list[float]) -> bytes:
    return np.asarray(vector, dtype=np.float32).tobytes()


class VectorIndex:
    """Embed, store and search vectors in SQLite."""

    _MAX_CANDIDATES = 256

    def __init__(self, db: SQLiteHandler, embedder: EmbeddingEngine, prefix: str):
        self._db = db
        self._embedder = embedder
        self._table = f"{prefix}_semantic_index"

    @property
    def enabled(self) -> bool:
        return self._embedder is not None and self._embedder.enabled

    async def ensure_schema(self) -> None:
        await self._db.execute(f"""
            CREATE TABLE IF NOT EXISTS {self._table} (
                entry_id     TEXT PRIMARY KEY,
                provider     TEXT NOT NULL,
                model        TEXT NOT NULL,
                dimensions   INTEGER NOT NULL,
                embedding    BLOB NOT NULL,
                created_at   TIMESTAMP
            )
        """)

    async def upsert(self, entry_id: str, text: str, created_at: str) -> None:
        """Embed text and store. Non-fatal on failure."""
        if not self.enabled:
            return

        vector = await self._embedder.embed_one(text)
        if not vector:
            return

        try:
            await self._db.execute(
                f"""INSERT OR REPLACE INTO {self._table}
                (entry_id, provider, model, dimensions, embedding, created_at)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    entry_id,
                    self._embedder.provider_id(),
                    self._embedder.model_id(),
                    len(vector),
                    _to_blob(vector),
                    created_at,
                ),
            )
        except Exception as e:
            logger.warning(f"VectorIndex({self._table}): upsert skipped — {e}")

    async def search(
        self,
        query: str,
        limit: int = 5,
        min_score: float = 0.6,
    ) -> list[tuple[str, float]]:
        """Semantic search. Returns (entry_id, score) pairs sorted by relevance."""
        if not query or not query.strip():
            return []
        if not self.enabled:
            return []

        query_vector = await self._embedder.embed_one(query)
        if not query_vector:
            return []

        rows = list(await self._db.fetchall(
            f"""SELECT entry_id, embedding, created_at FROM {self._table}
            WHERE provider = ? AND model = ? AND dimensions = ?
            ORDER BY created_at DESC
            LIMIT ?""",
            (
                self._embedder.provider_id(),
                self._embedder.model_id(),
                len(query_vector),
                self._MAX_CANDIDATES,
            ),
        ))

        if not rows:
            return []

        # Batch cosine scoring — single matrix op instead of per-row loop
        query_arr = np.asarray(query_vector, dtype=np.float32)
        query_norm = float(np.linalg.norm(query_arr))
        if query_norm == 0:
            return []

        dim = len(query_vector)
        entry_ids: list[str] = []
        blobs: list[bytes] = []
        ages_days: list[float] = []
        now = datetime.now(timezone.utc)
        for row in rows:
            entry_ids.append(row["entry_id"])
            blobs.append(row["embedding"])
            try:
                created = datetime.fromisoformat(row["created_at"])
                ages_days.append(max((now - created).total_seconds() / 86400, 0.0))
            except Exception:
                ages_days.append(0.0)

        matrix = np.frombuffer(b"".join(blobs), dtype=np.float32).reshape(-1, dim)
        norms = np.linalg.norm(matrix, axis=1)

        valid = norms > 0
        cosine = np.zeros(len(entry_ids), dtype=np.float32)
        cosine[valid] = (matrix[valid] @ query_arr) / (norms[valid] * query_norm)

        # Recency boost: exponential decay with configurable half-life.
        # Today = 1.0, after half-life days ≈ 0.85, floor at 0.7.
        age_arr = np.asarray(ages_days, dtype=np.float32)
        recency = np.maximum(0.7, np.exp(-0.2 * age_arr / _RECENCY_HALF_LIFE_DAYS))
        scores = cosine * recency

        results = [
            (entry_ids[i], float(scores[i]))
            for i in range(len(entry_ids))
            if scores[i] >= min_score
        ]
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]

    async def delete(self, entry_id: str) -> None:
        """Remove a vector from the index."""
        try:
            await self._db.execute(
                f"DELETE FROM {self._table} WHERE entry_id = ?", (entry_id,)
            )
        except Exception as e:
            logger.warning(f"VectorIndex({self._table}): delete failed — {e}")
