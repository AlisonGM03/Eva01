"""
EVA's journal — episodic memory stored in SQLite.

Pure database operations: write entries, read recent, create tables.
Orchestration (flush, distill, LLM calls) lives in memory.py.
"""

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from config import logger
from eva.database import SQLiteHandler
from eva.database.vector_utils import blob_to_vector, cosine_similarity, vector_to_blob
from eva.database.embeddings import EmbeddingEngine


class JournalDB:
    """EVA's journal — episodic memory store."""
    
    def __init__(self, db: SQLiteHandler, embedder: Optional[EmbeddingEngine] = None):
        self._db = db
        self._embedder = embedder
        self._initialized = False

    @staticmethod
    def _format_row(row) -> str:
        try:
            dt = datetime.fromisoformat(row["created_at"])
            ts = dt.strftime("%B %d, at %I%p")
            ts = ts.replace(" at 0", " at ")
            return f"[{ts}]\n {row['content']}"
        except Exception:
            return row["content"]

    async def init_db(self) -> None:
        """initialize_database."""
        if self._initialized:
            return
        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS journal (
                id          TEXT PRIMARY KEY,
                content     TEXT NOT NULL,
                session_id  TEXT,
                created_at  TIMESTAMP
            )
            """,
        )
        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS knowledge (
                id          TEXT PRIMARY KEY,
                content     TEXT NOT NULL,
                created_at  TIMESTAMP
            )
            """,
        )
        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS journal_semantic_index (
                entry_id     TEXT PRIMARY KEY,
                provider     TEXT NOT NULL,
                model        TEXT NOT NULL,
                dimensions   INTEGER NOT NULL,
                embedding    BLOB NOT NULL,
                created_at   TIMESTAMP,
                FOREIGN KEY(entry_id) REFERENCES journal(id) ON DELETE CASCADE
            )
            """,
        )
        self._initialized = True

    async def _index_entry(self, entry_id: str, content: str, created_at: str) -> None:
        """Index journal text for semantic retrieval. Non-fatal on failure."""
        if not self._embedder or not self._embedder.enabled:
            return

        vector = await self._embedder.embed_one(content)
        if not vector:
            return

        try:
            await self._db.execute(
                """
                INSERT OR REPLACE INTO journal_semantic_index
                (entry_id, provider, model, dimensions, embedding, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    entry_id,
                    self._embedder.provider_id(),
                    self._embedder.model_id(),
                    len(vector),
                    vector_to_blob(vector),
                    created_at,
                ),
            )
        except Exception as e:
            logger.warning(f"JournalDB: semantic index write skipped — {e}")

    async def add(self, content: str, session_id: str) -> str:
        """Write an episode to the journal. Returns the entry id."""
        
        entry_id = uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc).isoformat()
        try:
            await self._db.execute(
                "INSERT INTO journal (id, content, session_id, created_at) VALUES (?, ?, ?, ?)",
                (entry_id, content, session_id, now)
            )
            await self._index_entry(entry_id, content, now)
            return entry_id
        except Exception as e:
            logger.error(f"JournalDB: failed to write journal — {e}")
            return ""

    async def get_recent(self, limit: int = 3) -> List[str]:
        """Get recent journal entries — today's entries, or last session's if none today."""
        
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ).isoformat()

        rows = list(await self._db.fetchall(
            "SELECT content, created_at FROM journal WHERE created_at >= ? ORDER BY created_at DESC LIMIT ?",
            (today_start, limit),
        ))

        if rows:
            return [self._format_row(r) for r in reversed(rows)]
        else:
            return []

    async def get_semantic_context(self, query: str, limit: int = 5) -> str:
        """Return formatted journal snippets semantically close to query text."""
        if not query or not query.strip():
            return ""
        if not self._embedder or not self._embedder.enabled:
            return ""

        query_vector = await self._embedder.embed_one(query)
        if not query_vector:
            return ""

        rows = list(await self._db.fetchall(
            """
            SELECT j.content, j.created_at, s.embedding
            FROM journal_semantic_index s
            JOIN journal j ON j.id = s.entry_id
            WHERE s.provider = ? AND s.model = ? AND s.dimensions = ?
            ORDER BY s.created_at DESC
            LIMIT 256
            """,
            (
                self._embedder.provider_id(),
                self._embedder.model_id(),
                len(query_vector),
            ),
        ))

        if not rows:
            return ""

        scored: list[tuple[float, object]] = []
        for row in rows:
            try:
                row_vec = blob_to_vector(row["embedding"])
                score = cosine_similarity(query_vector, row_vec)
                if score > 0:
                    scored.append((score, row))
            except Exception:
                continue

        if not scored:
            return ""

        scored.sort(key=lambda item: item[0], reverse=True)
        selected = [self._format_row(row) for _, row in scored[:limit]]
        return "\n\n".join(selected)
