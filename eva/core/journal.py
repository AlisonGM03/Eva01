"""
EVA's journal — episodic memory stored in SQLite.

Pure database operations: write entries, read recent, search semantically.
Orchestration (flush, distill, LLM calls) lives in memory.py.
"""

import asyncio
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from config import logger
from eva.database.db import SQLiteHandler
from eva.database.vector_index import VectorIndex


class JournalDB:
    """EVA's journal — episodic memory store."""

    def __init__(self, db: SQLiteHandler, vectors: Optional[VectorIndex] = None):
        self._db = db
        self._vectors = vectors
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
            CREATE TABLE IF NOT EXISTS journal_source (
                entry_id    TEXT PRIMARY KEY,
                source      TEXT NOT NULL,
                FOREIGN KEY(entry_id) REFERENCES journal(id) ON DELETE CASCADE
            )
            """,
        )
        if self._vectors:
            await self._vectors.ensure_schema()
        self._initialized = True

    async def add(self, content: str, session_id: str, source: str = "") -> str:
        """Write an episode to the journal. Returns the entry id.

        Args:
            content: LLM-summarized journal entry (what EVA reads back).
            session_id: Session identifier for grouping entries.
            source: Raw conversation text. Embedded instead of content
                    for richer semantic search. Falls back to content if empty.
        """
        entry_id = uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc).isoformat()
        try:
            await self._db.execute(
                "INSERT INTO journal (id, content, session_id, created_at) VALUES (?, ?, ?, ?)",
                (entry_id, content, session_id, now)
            )
            if source:
                await self._db.execute(
                    "INSERT INTO journal_source (entry_id, source) VALUES (?, ?)",
                    (entry_id, source),
                )
            # Embed the source (rich) when available, fall back to content (summary)
            if self._vectors:
                embed_text = source or content
                asyncio.create_task(self._vectors.upsert(entry_id, embed_text, now))
            return entry_id
        except Exception as e:
            logger.error(f"JournalDB: failed to write journal — {e}")
            return ""

    async def get_recent(self, limit: int = 3) -> List[str]:
        """Get today's journal entries."""

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
        if not self._vectors:
            return ""

        results = await self._vectors.search(query, limit=limit)
        if not results:
            return ""

        entry_ids = [eid for eid, _ in results]
        placeholders = ",".join("?" * len(entry_ids))
        rows = list(await self._db.fetchall(
            f"SELECT id, content, created_at FROM journal WHERE id IN ({placeholders})",
            tuple(entry_ids),
        ))

        if not rows:
            return ""

        # Selection was by relevance, but present in chronological order
        rows.sort(key=lambda r: r["created_at"])
        return "\n\n".join(self._format_row(r) for r in rows)
