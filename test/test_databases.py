"""
test/test_databases.py — Comprehensive unit tests for all EVA01 database modules.

Covers:
  - SQLiteHandler: connection pooling, WAL mode, write locks, execute/fetchall/fetchone/
                   executemany/close/close_all, concurrent access
  - VectorIndex: schema creation, upsert, search (cosine + recency), delete, disabled state
  - EmbeddingEngine: provider parsing, init_model, embed_one, embed_many,
                     disabled fallback, empty text handling
  - JournalDB: init_db, add entries, get_recent (today filter), get_semantic_context,
               _format_row
  - PeopleDB: init_db, add, get, get_name, get_all, get_many, get_id_name_map,
              touch (single + batch), append_notes, append_reflection_notes, render_people
  - TaskDB: init_db, create, get_open, update, complete, summary

Run: pytest test/test_databases.py -v
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from config import DATA_DIR
from eva.core.journal import JournalDB
from eva.core.people import PeopleDB
from eva.core.tasks import TaskDB
from eva.database.db import SQLiteHandler
from eva.database.embeddings import EmbeddingEngine
from eva.database.vector_index import VectorIndex


# ── Test Infrastructure ─────────────────────────────────────────────────────


class ScopedSQLiteHandler(SQLiteHandler):
    """SQLite handler scoped to an isolated test DB file."""

    def __init__(self, db_name: str) -> None:
        super().__init__()
        self._db_name = db_name

    async def execute(self, query, params=(), db_name=None):
        await super().execute(query, params, db_name or self._db_name)

    async def executemany(self, query, params_list, db_name=None):
        await super().executemany(query, params_list, db_name or self._db_name)

    async def fetchall(self, query, params=(), db_name=None):
        return await super().fetchall(query, params, db_name or self._db_name)

    async def fetchone(self, query, params=(), db_name=None):
        return await super().fetchone(query, params, db_name or self._db_name)

    async def close(self, db_name=None):
        await super().close(db_name or self._db_name)


def _make_db_name() -> str:
    """Generate a unique test DB name to prevent collisions."""
    return f"test_{uuid.uuid4().hex[:12]}.db"


def _db_path(db_name: str) -> Path:
    return DATA_DIR / "database" / db_name


async def _cleanup(db: ScopedSQLiteHandler, db_name: str) -> None:
    """Close connection and remove temp DB file."""
    await db.close()
    path = _db_path(db_name)
    if path.exists():
        path.unlink()


class DeterministicEmbedder:
    """Hash-based deterministic embedder for stable vector tests (no real model)."""

    enabled = True

    def provider_id(self) -> str:
        return "test"

    def model_id(self) -> str:
        return "deterministic-v1"

    async def embed_one(self, text: str) -> list[float]:
        h = hashlib.md5(text.encode()).hexdigest()
        return [int(c, 16) / 15.0 for c in h[:16]]

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed_one(t) for t in texts]


class DisabledEmbedder:
    """Stub embedder that is always disabled."""

    enabled = False

    def provider_id(self) -> str:
        return "disabled"

    def model_id(self) -> str:
        return "none"

    async def embed_one(self, text: str) -> Optional[list[float]]:
        return None


# ── SQLiteHandler Tests ──────────────────────────────────────────────────────


def test_sqlite_handler_execute_and_fetchone():
    """execute() writes a row; fetchone() reads it back."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        try:
            await db.execute("CREATE TABLE t (x TEXT)")
            await db.execute("INSERT INTO t (x) VALUES (?)", ("hello",))
            row = await db.fetchone("SELECT x FROM t")
            assert row is not None
            assert row["x"] == "hello"
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_sqlite_handler_fetchall_multiple_rows():
    """fetchall() returns all rows in the table."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        try:
            await db.execute("CREATE TABLE nums (n INTEGER)")
            for i in range(5):
                await db.execute("INSERT INTO nums (n) VALUES (?)", (i,))
            rows = list(await db.fetchall("SELECT n FROM nums ORDER BY n"))
            assert [r["n"] for r in rows] == [0, 1, 2, 3, 4]
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_sqlite_handler_fetchone_returns_none_when_empty():
    """fetchone() returns None when the query matches no rows."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        try:
            await db.execute("CREATE TABLE t (x TEXT)")
            row = await db.fetchone("SELECT x FROM t WHERE x = 'missing'")
            assert row is None
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_sqlite_handler_executemany():
    """executemany() inserts all rows in one call."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        try:
            await db.execute("CREATE TABLE items (v TEXT)")
            await db.executemany(
                "INSERT INTO items (v) VALUES (?)",
                [("a",), ("b",), ("c",)],
            )
            rows = list(await db.fetchall("SELECT v FROM items ORDER BY v"))
            assert [r["v"] for r in rows] == ["a", "b", "c"]
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_sqlite_handler_wal_mode_enabled():
    """WAL mode is set on new connections."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        try:
            row = await db.fetchone("PRAGMA journal_mode")
            assert row is not None
            assert row[0] == "wal"
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_sqlite_handler_close_removes_connection():
    """After close(), a new connection is created on the next access."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        try:
            # Trigger initial connection
            await db.execute("CREATE TABLE t (x INTEGER)")
            assert db_name in db._connections

            await db.close()
            assert db_name not in db._connections

            # After close, can still use the handler (reconnects)
            await db.execute("INSERT INTO t (x) VALUES (?)", (42,))
            row = await db.fetchone("SELECT x FROM t")
            assert row["x"] == 42
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_sqlite_handler_close_all():
    """close_all() closes every open connection."""

    async def _run():
        db_name_1 = _make_db_name()
        db_name_2 = _make_db_name()
        db = SQLiteHandler()
        try:
            # Open two separate DB connections
            await db.execute("CREATE TABLE t (x INTEGER)", db_name=db_name_1)
            await db.execute("CREATE TABLE t (x INTEGER)", db_name=db_name_2)
            assert db_name_1 in db._connections
            assert db_name_2 in db._connections

            await db.close_all()
            assert len(db._connections) == 0
            assert len(db._write_locks) == 0
        finally:
            for name in (db_name_1, db_name_2):
                p = _db_path(name)
                if p.exists():
                    p.unlink()

    asyncio.run(_run())


def test_sqlite_handler_concurrent_writes_do_not_corrupt():
    """Multiple concurrent execute() calls under the write lock complete without errors.

    The write lock serializes individual execute() calls, preventing aiosqlite
    database corruption. It does NOT provide atomicity across separate read+write
    calls — that would require an application-level lock. This test verifies that
    20 concurrent INSERTs all succeed and all rows are present in the DB.
    """

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        try:
            await db.execute("CREATE TABLE entries (val TEXT)")

            async def insert_one(i: int):
                await db.execute("INSERT INTO entries (val) VALUES (?)", (f"item_{i}",))

            # Run 20 inserts concurrently — all should complete without exception
            await asyncio.gather(*[insert_one(i) for i in range(20)])

            rows = list(await db.fetchall("SELECT val FROM entries"))
            # All 20 rows must be present — no data dropped by concurrent writes
            assert len(rows) == 20
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_sqlite_handler_separate_instances_use_separate_connections():
    """Two ScopedSQLiteHandler instances targeting different DBs don't share state."""

    async def _run():
        db_name_a = _make_db_name()
        db_name_b = _make_db_name()
        db_a = ScopedSQLiteHandler(db_name_a)
        db_b = ScopedSQLiteHandler(db_name_b)
        try:
            await db_a.execute("CREATE TABLE t (v TEXT)")
            await db_a.execute("INSERT INTO t (v) VALUES ('only_in_a')")

            await db_b.execute("CREATE TABLE t (v TEXT)")
            # db_b table is empty

            rows_a = list(await db_a.fetchall("SELECT v FROM t"))
            rows_b = list(await db_b.fetchall("SELECT v FROM t"))

            assert len(rows_a) == 1
            assert len(rows_b) == 0
        finally:
            await db_a.close()
            await db_b.close()
            for name in (db_name_a, db_name_b):
                p = _db_path(name)
                if p.exists():
                    p.unlink()

    asyncio.run(_run())


# ── EmbeddingEngine Tests ────────────────────────────────────────────────────


def test_embedding_engine_parse_openai_spec():
    """'openai:text-embedding-3-small' parses into correct provider/model."""
    engine = EmbeddingEngine("openai:text-embedding-3-small")
    assert engine.provider == "openai"
    assert engine.model == "text-embedding-3-small"


def test_embedding_engine_parse_fastembed_spec():
    """'fastembed:bge-small-en-v1.5' parses correctly."""
    engine = EmbeddingEngine("fastembed:bge-small-en-v1.5")
    assert engine.provider == "fastembed"
    assert engine.model == "bge-small-en-v1.5"


def test_embedding_engine_parse_colon_in_model_name():
    """Model names may contain colons; only first colon is the separator."""
    engine = EmbeddingEngine("openai:my:model:v2")
    assert engine.provider == "openai"
    assert engine.model == "my:model:v2"


def test_embedding_engine_parse_invalid_spec_raises():
    """Provider spec without ':' raises ValueError."""
    with pytest.raises(ValueError, match="provider:model"):
        EmbeddingEngine("invalid-spec-no-colon")


def test_embedding_engine_disabled_before_init():
    """EmbeddingEngine is not enabled until init_model() is called."""
    engine = EmbeddingEngine("openai:text-embedding-3-small")
    assert engine.enabled is False


def test_embedding_engine_init_model_openai_no_key_disables():
    """init_model() with openai but no API key sets enabled=False (no exception raised)."""
    engine = EmbeddingEngine("openai:text-embedding-3-small")
    # Patch AsyncOpenAI to raise on construction (simulates missing key)
    with patch("eva.database.embeddings.OpenAIEmbedding.init", side_effect=Exception("no key")):
        engine.init_model()
    assert engine.enabled is False


def test_embedding_engine_init_model_unknown_provider_disables():
    """init_model() with unsupported provider sets enabled=False."""
    engine = EmbeddingEngine("unknownprovider:some-model")
    engine.init_model()
    assert engine.enabled is False


def test_embedding_engine_provider_id_and_model_id():
    """provider_id() and model_id() return the parsed values."""
    engine = EmbeddingEngine("fastembed:bge-small-en-v1.5")
    assert engine.provider_id() == "fastembed"
    assert engine.model_id() == "bge-small-en-v1.5"


def test_embedding_engine_embed_one_disabled_returns_none():
    """embed_one() returns None when engine is disabled."""

    async def _run():
        engine = EmbeddingEngine("openai:text-embedding-3-small")
        # not initialized → disabled
        result = await engine.embed_one("hello world")
        assert result is None

    asyncio.run(_run())


def test_embedding_engine_embed_one_empty_text_returns_none():
    """embed_one() returns None for empty or whitespace-only text even when enabled."""

    async def _run():
        engine = EmbeddingEngine("openai:text-embedding-3-small")
        # Force enabled with a mock backing model
        mock_backend = MagicMock()
        mock_backend.embed = AsyncMock(return_value=[0.1, 0.2])
        engine._enabled = True
        engine._embedding = mock_backend

        assert await engine.embed_one("") is None
        assert await engine.embed_one("   ") is None
        mock_backend.embed.assert_not_called()

    asyncio.run(_run())


def test_embedding_engine_embed_one_success():
    """embed_one() returns a float list when the backend works."""

    async def _run():
        engine = EmbeddingEngine("openai:text-embedding-3-small")
        mock_backend = MagicMock()
        mock_backend.embed = AsyncMock(return_value=[0.1, 0.2, 0.3])
        engine._enabled = True
        engine._embedding = mock_backend

        result = await engine.embed_one("some text")
        assert isinstance(result, list)
        assert result == [0.1, 0.2, 0.3]

    asyncio.run(_run())


def test_embedding_engine_embed_one_sets_dimension():
    """First successful embed_one() sets the _dimension property."""

    async def _run():
        engine = EmbeddingEngine("openai:text-embedding-3-small")
        mock_backend = MagicMock()
        mock_backend.embed = AsyncMock(return_value=[0.1] * 128)
        engine._enabled = True
        engine._embedding = mock_backend

        assert engine.dimension is None
        await engine.embed_one("any text")
        assert engine.dimension == 128

    asyncio.run(_run())


def test_embedding_engine_embed_many_disabled_returns_nones():
    """embed_many() returns a list of None when disabled."""

    async def _run():
        engine = EmbeddingEngine("openai:text-embedding-3-small")
        result = await engine.embed_many(["a", "b", "c"])
        assert result == [None, None, None]

    asyncio.run(_run())


def test_embedding_engine_embed_many_skips_empty_strings():
    """embed_many() passes only non-empty texts to backend, returns None for empties."""

    async def _run():
        engine = EmbeddingEngine("openai:text-embedding-3-small")
        mock_backend = MagicMock()
        # Backend receives 2 texts ("hello", "world"), returns 2 vectors
        mock_backend.embed_many = AsyncMock(return_value=[[0.1], [0.2]])
        engine._enabled = True
        engine._embedding = mock_backend

        result = await engine.embed_many(["hello", "", "world"])
        assert result[0] == [0.1]
        assert result[1] is None
        assert result[2] == [0.2]

    asyncio.run(_run())


def test_embedding_engine_embed_many_all_empty_returns_nones():
    """embed_many() with all empty texts skips backend call entirely."""

    async def _run():
        engine = EmbeddingEngine("openai:text-embedding-3-small")
        mock_backend = MagicMock()
        mock_backend.embed_many = AsyncMock(return_value=[])
        engine._enabled = True
        engine._embedding = mock_backend

        result = await engine.embed_many(["", "  ", ""])
        assert result == [None, None, None]
        mock_backend.embed_many.assert_not_called()

    asyncio.run(_run())


def test_embedding_engine_embed_one_exception_returns_none():
    """embed_one() returns None and doesn't raise when backend throws."""

    async def _run():
        engine = EmbeddingEngine("openai:text-embedding-3-small")
        mock_backend = MagicMock()
        mock_backend.embed = AsyncMock(side_effect=RuntimeError("API down"))
        engine._enabled = True
        engine._embedding = mock_backend

        result = await engine.embed_one("test")
        assert result is None

    asyncio.run(_run())


# ── VectorIndex Tests ────────────────────────────────────────────────────────


def test_vector_index_enabled_with_enabled_embedder():
    """VectorIndex.enabled is True when embedder.enabled is True."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        embedder = DeterministicEmbedder()
        vi = VectorIndex(db, embedder, prefix="test")
        try:
            assert vi.enabled is True
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_vector_index_disabled_with_disabled_embedder():
    """VectorIndex.enabled is False when embedder.enabled is False."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        embedder = DisabledEmbedder()
        vi = VectorIndex(db, embedder, prefix="test")
        try:
            assert vi.enabled is False
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_vector_index_disabled_with_none_embedder():
    """VectorIndex.enabled is False when embedder is None."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        vi = VectorIndex(db, None, prefix="test")
        try:
            assert vi.enabled is False
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_vector_index_ensure_schema_creates_table():
    """ensure_schema() creates the <prefix>_semantic_index table."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        vi = VectorIndex(db, DeterministicEmbedder(), prefix="journal")
        try:
            await vi.ensure_schema()
            row = await db.fetchone(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='journal_semantic_index'"
            )
            assert row is not None
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_vector_index_ensure_schema_idempotent():
    """ensure_schema() can be called multiple times without error."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        vi = VectorIndex(db, DeterministicEmbedder(), prefix="journal")
        try:
            await vi.ensure_schema()
            await vi.ensure_schema()  # Should not raise
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_vector_index_upsert_stores_vector():
    """upsert() embeds text and stores a row in the index table."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        vi = VectorIndex(db, DeterministicEmbedder(), prefix="test")
        try:
            await vi.ensure_schema()
            now = datetime.now(timezone.utc).isoformat()
            await vi.upsert("entry_001", "hello world", now)

            row = await db.fetchone(
                "SELECT entry_id, provider, model, dimensions FROM test_semantic_index WHERE entry_id = 'entry_001'"
            )
            assert row is not None
            assert row["entry_id"] == "entry_001"
            assert row["provider"] == "test"
            assert row["model"] == "deterministic-v1"
            assert row["dimensions"] == 16  # DeterministicEmbedder produces 16-dim vectors
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_vector_index_upsert_noop_when_disabled():
    """upsert() does nothing when the index is disabled."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        vi = VectorIndex(db, DisabledEmbedder(), prefix="test")
        try:
            await vi.ensure_schema()
            now = datetime.now(timezone.utc).isoformat()
            await vi.upsert("entry_disabled", "some text", now)

            row = await db.fetchone(
                "SELECT entry_id FROM test_semantic_index WHERE entry_id = 'entry_disabled'"
            )
            assert row is None
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_vector_index_upsert_replaces_existing():
    """upsert() with same entry_id replaces the existing row."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        vi = VectorIndex(db, DeterministicEmbedder(), prefix="test")
        try:
            await vi.ensure_schema()
            now = datetime.now(timezone.utc).isoformat()
            await vi.upsert("eid_1", "first text", now)
            await vi.upsert("eid_1", "second text", now)

            rows = list(await db.fetchall(
                "SELECT COUNT(*) AS n FROM test_semantic_index WHERE entry_id = 'eid_1'"
            ))
            assert rows[0]["n"] == 1
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_vector_index_delete_removes_row():
    """delete() removes the vector row from the index."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        vi = VectorIndex(db, DeterministicEmbedder(), prefix="test")
        try:
            await vi.ensure_schema()
            now = datetime.now(timezone.utc).isoformat()
            await vi.upsert("to_delete", "some text", now)

            # Confirm it's there
            row = await db.fetchone(
                "SELECT entry_id FROM test_semantic_index WHERE entry_id = 'to_delete'"
            )
            assert row is not None

            await vi.delete("to_delete")

            row = await db.fetchone(
                "SELECT entry_id FROM test_semantic_index WHERE entry_id = 'to_delete'"
            )
            assert row is None
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_vector_index_delete_nonexistent_is_silent():
    """delete() on a nonexistent entry_id does not raise."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        vi = VectorIndex(db, DeterministicEmbedder(), prefix="test")
        try:
            await vi.ensure_schema()
            await vi.delete("nonexistent_id")  # Should not raise
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_vector_index_search_returns_empty_when_no_data():
    """search() returns empty list when the index has no entries."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        vi = VectorIndex(db, DeterministicEmbedder(), prefix="test")
        try:
            await vi.ensure_schema()
            results = await vi.search("any query", limit=5)
            assert results == []
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_vector_index_search_returns_empty_for_empty_query():
    """search() returns empty list for empty or whitespace query."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        vi = VectorIndex(db, DeterministicEmbedder(), prefix="test")
        try:
            await vi.ensure_schema()
            assert await vi.search("") == []
            assert await vi.search("   ") == []
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_vector_index_search_returns_empty_when_disabled():
    """search() returns [] when index is disabled."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        vi = VectorIndex(db, DisabledEmbedder(), prefix="test")
        try:
            await vi.ensure_schema()
            results = await vi.search("anything", limit=5)
            assert results == []
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_vector_index_search_finds_identical_text():
    """An exact text match should score near 1.0 (modulo recency factor)."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        vi = VectorIndex(db, DeterministicEmbedder(), prefix="test")
        try:
            await vi.ensure_schema()
            now = datetime.now(timezone.utc).isoformat()
            text = "unique test phrase"
            await vi.upsert("entry_abc", text, now)

            results = await vi.search(text, limit=5, min_score=0.0)
            assert len(results) == 1
            entry_id, score = results[0]
            assert entry_id == "entry_abc"
            # DeterministicEmbedder: same text → same vector → cosine=1.0
            # Recency boost ≥ 0.7, so score ≥ 0.7
            assert score >= 0.7
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_vector_index_search_respects_min_score():
    """Results below min_score are excluded."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        vi = VectorIndex(db, DeterministicEmbedder(), prefix="test")
        try:
            await vi.ensure_schema()
            now = datetime.now(timezone.utc).isoformat()
            await vi.upsert("a", "hello world", now)

            # With min_score=1.0 (impossible), nothing should be returned
            results = await vi.search("hello world", limit=5, min_score=1.01)
            assert results == []
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_vector_index_search_respects_limit():
    """Results are capped at the requested limit."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        vi = VectorIndex(db, DeterministicEmbedder(), prefix="test")
        try:
            await vi.ensure_schema()
            now = datetime.now(timezone.utc).isoformat()
            # Insert identical text so they all score the same
            for i in range(10):
                await vi.upsert(f"e{i}", "same text", now)

            results = await vi.search("same text", limit=3, min_score=0.0)
            assert len(results) <= 3
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_vector_index_search_results_sorted_descending():
    """Search results are sorted by score descending."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        vi = VectorIndex(db, DeterministicEmbedder(), prefix="test")
        try:
            await vi.ensure_schema()
            now = datetime.now(timezone.utc).isoformat()
            await vi.upsert("e1", "alpha beta gamma", now)
            await vi.upsert("e2", "totally different xyz", now)

            results = await vi.search("alpha beta gamma", limit=10, min_score=0.0)
            if len(results) > 1:
                scores = [s for _, s in results]
                assert scores == sorted(scores, reverse=True)
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_vector_index_recency_boost_recent_higher_than_old():
    """A recent entry scores higher than an old entry for the same text."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        vi = VectorIndex(db, DeterministicEmbedder(), prefix="test")
        try:
            await vi.ensure_schema()
            text = "recency test text"
            recent = datetime.now(timezone.utc).isoformat()
            old = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()

            await vi.upsert("recent_entry", text, recent)
            await vi.upsert("old_entry", text, old)

            results = await vi.search(text, limit=10, min_score=0.0)
            result_map = {eid: score for eid, score in results}

            # Both must be present
            assert "recent_entry" in result_map
            assert "old_entry" in result_map

            # Recent should have higher score
            assert result_map["recent_entry"] > result_map["old_entry"]
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_vector_index_search_ignores_wrong_provider_model():
    """Vectors stored by a different provider/model are not returned."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        vi = VectorIndex(db, DeterministicEmbedder(), prefix="test")
        try:
            await vi.ensure_schema()
            now = datetime.now(timezone.utc).isoformat()

            # Manually insert a row with a different provider
            import numpy as np
            fake_vector = np.ones(16, dtype=np.float32).tobytes()
            await db.execute(
                "INSERT INTO test_semantic_index (entry_id, provider, model, dimensions, embedding, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                ("alien_entry", "other_provider", "other_model", 16, fake_vector, now),
            )

            results = await vi.search("anything", limit=10, min_score=0.0)
            entry_ids = [eid for eid, _ in results]
            assert "alien_entry" not in entry_ids
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


# ── JournalDB Tests ──────────────────────────────────────────────────────────


def test_journal_init_db_creates_tables():
    """init_db() creates journal and journal_source tables."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        journal = JournalDB(db)
        try:
            await journal.init_db()
            journal_row = await db.fetchone(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='journal'"
            )
            source_row = await db.fetchone(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='journal_source'"
            )
            assert journal_row is not None
            assert source_row is not None
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_journal_init_db_idempotent():
    """init_db() can be called multiple times without error."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        journal = JournalDB(db)
        try:
            await journal.init_db()
            await journal.init_db()  # Must not raise
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_journal_add_returns_entry_id():
    """add() returns a non-empty string ID."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        journal = JournalDB(db)
        try:
            await journal.init_db()
            entry_id = await journal.add("Test content", "session-1")
            assert isinstance(entry_id, str)
            assert len(entry_id) > 0
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_journal_add_entry_persists_to_db():
    """add() writes the entry to the journal table."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        journal = JournalDB(db)
        try:
            await journal.init_db()
            entry_id = await journal.add("My journal content", "sess-42")
            row = await db.fetchone(
                "SELECT id, content, session_id FROM journal WHERE id = ?", (entry_id,)
            )
            assert row is not None
            assert row["content"] == "My journal content"
            assert row["session_id"] == "sess-42"
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_journal_add_with_source_writes_journal_source():
    """add() with source= writes a row to journal_source."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        journal = JournalDB(db)
        try:
            await journal.init_db()
            entry_id = await journal.add(
                "Summary content", "sess-1", source="Raw conversation text"
            )
            row = await db.fetchone(
                "SELECT source FROM journal_source WHERE entry_id = ?", (entry_id,)
            )
            assert row is not None
            assert row["source"] == "Raw conversation text"
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_journal_add_without_source_no_journal_source_row():
    """add() without source= does not write to journal_source."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        journal = JournalDB(db)
        try:
            await journal.init_db()
            entry_id = await journal.add("Summary only", "sess-2")
            row = await db.fetchone(
                "SELECT source FROM journal_source WHERE entry_id = ?", (entry_id,)
            )
            assert row is None
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_journal_get_recent_returns_todays_entries():
    """get_recent() returns entries created today in chronological order."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        journal = JournalDB(db)
        try:
            await journal.init_db()
            await journal.add("First entry today", "s1")
            await journal.add("Second entry today", "s2")

            entries = await journal.get_recent(limit=10)
            assert len(entries) == 2
            # Returned in chronological order (oldest first)
            assert "First entry today" in entries[0]
            assert "Second entry today" in entries[1]
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_journal_get_recent_excludes_old_entries():
    """get_recent() only returns today's entries; older ones are excluded."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        journal = JournalDB(db)
        try:
            await journal.init_db()

            # Manually insert a yesterday entry
            yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
            await db.execute(
                "INSERT INTO journal (id, content, session_id, created_at) VALUES (?, ?, ?, ?)",
                ("old_entry", "Yesterday's entry", "s0", yesterday),
            )

            # Today's entry
            await journal.add("Today's entry", "s1")

            entries = await journal.get_recent(limit=10)
            # Only today
            assert len(entries) == 1
            assert "Today's entry" in entries[0]
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_journal_get_recent_respects_limit():
    """get_recent() returns at most limit entries."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        journal = JournalDB(db)
        try:
            await journal.init_db()
            for i in range(5):
                await journal.add(f"Entry {i}", "s")

            entries = await journal.get_recent(limit=2)
            assert len(entries) == 2
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_journal_get_recent_empty_when_no_entries():
    """get_recent() returns [] when journal is empty."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        journal = JournalDB(db)
        try:
            await journal.init_db()
            entries = await journal.get_recent()
            assert entries == []
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_journal_format_row_produces_timestamp_prefix():
    """_format_row() produces a string starting with '[<Month> ...]'."""
    from aiosqlite import Row

    # Build a minimal sqlite3 row-like dict via dict subclass
    class FakeRow(dict):
        def __getitem__(self, key):
            return super().__getitem__(key)

    now = datetime.now(timezone.utc).isoformat()
    row = FakeRow({"created_at": now, "content": "Hello journal"})
    formatted = JournalDB._format_row(row)
    assert "Hello journal" in formatted
    assert "[" in formatted and "]" in formatted


def test_journal_format_row_fallback_on_bad_timestamp():
    """_format_row() falls back to raw content on unparseable timestamp."""

    class FakeRow(dict):
        def __getitem__(self, key):
            return super().__getitem__(key)

    row = FakeRow({"created_at": "not-a-date", "content": "Raw content here"})
    formatted = JournalDB._format_row(row)
    assert formatted == "Raw content here"


def test_journal_get_semantic_context_no_vectors_returns_empty():
    """get_semantic_context() returns '' when no VectorIndex is attached."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        journal = JournalDB(db, vectors=None)
        try:
            await journal.init_db()
            result = await journal.get_semantic_context("any query")
            assert result == ""
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_journal_get_semantic_context_returns_formatted_results():
    """get_semantic_context() returns journal entries formatted as strings."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        embedder = DeterministicEmbedder()
        vi = VectorIndex(db, embedder, prefix="journal")
        journal = JournalDB(db, vectors=vi)
        try:
            await journal.init_db()
            await journal.add("I went running in the park", "s1")
            # Wait for fire-and-forget upsert tasks
            await asyncio.sleep(0.1)

            context = await journal.get_semantic_context("I went running in the park", limit=5)
            # The exact same text should be returned in context
            assert "running" in context
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_journal_get_semantic_context_empty_when_no_match():
    """get_semantic_context() returns '' when no entry meets the min_score threshold."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        embedder = DeterministicEmbedder()
        vi = VectorIndex(db, embedder, prefix="journal")
        journal = JournalDB(db, vectors=vi)
        try:
            await journal.init_db()
            # Empty journal — no entries to find
            await asyncio.sleep(0.05)
            context = await journal.get_semantic_context("some query")
            assert context == ""
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


# ── PeopleDB Tests ───────────────────────────────────────────────────────────


def test_people_init_db_creates_table():
    """init_db() creates the people table."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        people = PeopleDB(db)
        try:
            await people.init_db()
            row = await db.fetchone(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='people'"
            )
            assert row is not None
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_people_init_db_idempotent():
    """init_db() can be called multiple times without error."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        people = PeopleDB(db)
        try:
            await people.init_db()
            await people.init_db()
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_people_add_and_get():
    """add() stores a person; get() returns them from cache."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        people = PeopleDB(db)
        try:
            await people.init_db()
            result = await people.add("alice", "Alice Smith", "friend")
            assert result is True

            person = people.get("alice")
            assert person is not None
            assert person["name"] == "Alice Smith"
            assert person["relationship"] == "friend"
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_people_add_persists_to_db():
    """add() writes the person row to SQLite (not just cache)."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        people = PeopleDB(db)
        try:
            await people.init_db()
            await people.add("bob", "Bob Jones", "colleague")

            row = await db.fetchone("SELECT name FROM people WHERE id = 'bob'")
            assert row is not None
            assert row["name"] == "Bob Jones"
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_people_add_duplicate_returns_false():
    """add() returns False and doesn't overwrite when person already exists."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        people = PeopleDB(db)
        try:
            await people.init_db()
            await people.add("carol", "Carol White", "friend")
            result = await people.add("carol", "Carol White Updated", "enemy")
            assert result is False
            # Original name still in cache
            assert people.get("carol")["name"] == "Carol White"
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_people_get_returns_none_for_unknown():
    """get() returns None when person_id is not known."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        people = PeopleDB(db)
        try:
            await people.init_db()
            assert people.get("nonexistent_id") is None
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_people_get_name():
    """get_name() returns just the name string, or None for unknown."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        people = PeopleDB(db)
        try:
            await people.init_db()
            await people.add("dave", "Dave Brown")

            assert people.get_name("dave") == "Dave Brown"
            assert people.get_name("unknown_id") is None
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_people_get_all_returns_full_cache():
    """get_all() returns all people in the cache."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        people = PeopleDB(db)
        try:
            await people.init_db()
            await people.add("p1", "Person One")
            await people.add("p2", "Person Two")

            all_people = people.get_all()
            assert "p1" in all_people
            assert "p2" in all_people
            assert len(all_people) == 2
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_people_get_many_returns_subset():
    """get_many() returns only the requested IDs that are known."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        people = PeopleDB(db)
        try:
            await people.init_db()
            await people.add("a", "Alice")
            await people.add("b", "Bob")
            await people.add("c", "Carol")

            subset = people.get_many(["a", "c", "unknown"])
            assert "a" in subset
            assert "c" in subset
            assert "b" not in subset
            assert "unknown" not in subset
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_people_get_id_name_map():
    """get_id_name_map() returns a dict of id → name."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        people = PeopleDB(db)
        try:
            await people.init_db()
            await people.add("x1", "Xena")
            await people.add("x2", "Xerxes")

            id_map = people.get_id_name_map()
            assert id_map == {"x1": "Xena", "x2": "Xerxes"}
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_people_touch_single_updates_last_seen():
    """touch() with a single ID updates last_seen in cache and DB."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        people = PeopleDB(db)
        try:
            await people.init_db()
            await people.add("t1", "Tester One")
            original_last_seen = people.get("t1")["last_seen"]

            # Small sleep so the new timestamp will differ
            await asyncio.sleep(0.01)
            await people.touch("t1")

            new_last_seen = people.get("t1")["last_seen"]
            assert new_last_seen >= original_last_seen

            # Also verify in DB
            row = await db.fetchone("SELECT last_seen FROM people WHERE id = 't1'")
            assert row["last_seen"] == new_last_seen
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_people_touch_batch_updates_multiple():
    """touch() with a set of IDs updates all of them."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        people = PeopleDB(db)
        try:
            await people.init_db()
            await people.add("b1", "Batch One")
            await people.add("b2", "Batch Two")

            await asyncio.sleep(0.01)
            before_b1 = people.get("b1")["last_seen"]
            before_b2 = people.get("b2")["last_seen"]

            await asyncio.sleep(0.01)
            await people.touch({"b1", "b2"})

            assert people.get("b1")["last_seen"] >= before_b1
            assert people.get("b2")["last_seen"] >= before_b2
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_people_touch_empty_is_noop():
    """touch() with empty string or empty set does nothing."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        people = PeopleDB(db)
        try:
            await people.init_db()
            # Must not raise
            await people.touch("")
            await people.touch(set())
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_people_append_notes_sets_notes():
    """append_notes() adds a timestamped block to the person's notes."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        people = PeopleDB(db)
        try:
            await people.init_db()
            await people.add("n1", "Note Person")

            await people.append_notes("n1", "Seemed happy today.")

            notes = people.get("n1")["notes"]
            assert notes is not None
            assert "Seemed happy today." in notes
            # Timestamp header prefix
            assert "##" in notes
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_people_append_notes_accumulates():
    """append_notes() called twice accumulates both impressions."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        people = PeopleDB(db)
        try:
            await people.init_db()
            await people.add("n2", "Accumulate Person")

            await people.append_notes("n2", "First impression.")
            await people.append_notes("n2", "Second impression.")

            notes = people.get("n2")["notes"]
            assert "First impression." in notes
            assert "Second impression." in notes
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_people_append_notes_noop_for_unknown():
    """append_notes() silently does nothing for an unknown person_id."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        people = PeopleDB(db)
        try:
            await people.init_db()
            # Should not raise
            await people.append_notes("does_not_exist", "Ignored impression.")
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_people_append_notes_persists_to_db():
    """append_notes() writes updated notes to SQLite, not just cache."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        people = PeopleDB(db)
        try:
            await people.init_db()
            await people.add("persist_p", "Persist Person")
            await people.append_notes("persist_p", "Noted in DB.")

            row = await db.fetchone("SELECT notes FROM people WHERE id = 'persist_p'")
            assert row is not None
            assert "Noted in DB." in row["notes"]
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_people_append_reflection_notes_filters_by_mentioned():
    """append_reflection_notes() only writes impressions for IDs in `mentioned`."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        people = PeopleDB(db)
        try:
            await people.init_db()
            await people.add("in_scope", "In Scope")
            await people.add("out_scope", "Out Scope")

            class FakeImpression:
                def __init__(self, pid, imp):
                    self.person_id = pid
                    self.impression = imp

            impressions = [
                FakeImpression("in_scope", "This one applies."),
                FakeImpression("out_scope", "This one should not apply."),
            ]

            await people.append_reflection_notes({"in_scope"}, impressions)

            assert "This one applies." in (people.get("in_scope")["notes"] or "")
            assert people.get("out_scope")["notes"] is None
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_people_cache_loaded_on_init():
    """After init_db(), people already in the DB are loaded into the cache."""

    async def _run():
        db_name = _make_db_name()
        # First instance: add a person
        db1 = ScopedSQLiteHandler(db_name)
        people1 = PeopleDB(db1)
        await people1.init_db()
        await people1.add("loaded_p", "Loaded Person")
        await db1.close()

        # Second instance: should load from DB on init
        db2 = ScopedSQLiteHandler(db_name)
        people2 = PeopleDB(db2)
        await people2.init_db()
        try:
            assert people2.get("loaded_p") is not None
            assert people2.get("loaded_p")["name"] == "Loaded Person"
        finally:
            await _cleanup(db2, db_name)

    asyncio.run(_run())


def test_people_render_people_formats_correctly():
    """render_people() produces 'id: name (relationship)' lines."""
    people_dict = {
        "p1": {"name": "Alice", "relationship": "friend"},
        "p2": {"name": "Bob", "relationship": None},
    }
    rendered = PeopleDB.render_people(people_dict)
    assert "p1: Alice (friend)" in rendered
    assert "p2: Bob (no relationship noted)" in rendered


def test_people_render_people_empty():
    """render_people() on empty dict returns empty string."""
    rendered = PeopleDB.render_people({})
    assert rendered == ""


# ── TaskDB Tests ─────────────────────────────────────────────────────────────


def test_task_init_db_creates_table():
    """init_db() creates the tasks table."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        tasks = TaskDB(db)
        try:
            await tasks.init_db()
            row = await db.fetchone(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'"
            )
            assert row is not None
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_task_init_db_idempotent():
    """init_db() can be called multiple times without error."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        tasks = TaskDB(db)
        try:
            await tasks.init_db()
            await tasks.init_db()
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_task_create_returns_short_id():
    """create() returns a 6-character hex ID."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        tasks = TaskDB(db)
        try:
            await tasks.init_db()
            task_id = await tasks.create("Do something interesting")
            assert isinstance(task_id, str)
            assert len(task_id) == 6
            assert re.match(r"^[0-9a-f]{6}$", task_id)
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_task_create_persists_to_db():
    """create() writes a row with status='open' to SQLite."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        tasks = TaskDB(db)
        try:
            await tasks.init_db()
            task_id = await tasks.create("Check the weather")
            row = await db.fetchone(
                "SELECT id, objective, status FROM tasks WHERE id = ?", (task_id,)
            )
            assert row is not None
            assert row["objective"] == "Check the weather"
            assert row["status"] == "open"
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_task_get_open_returns_open_tasks():
    """get_open() returns tasks that are not 'done'."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        tasks = TaskDB(db)
        try:
            await tasks.init_db()
            id1 = await tasks.create("Task one")
            id2 = await tasks.create("Task two")
            await tasks.complete(id2)

            open_tasks = await tasks.get_open()
            ids = [t["id"] for t in open_tasks]
            assert id1 in ids
            assert id2 not in ids
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_task_get_open_returns_all_non_done_statuses():
    """get_open() includes both 'open' and 'in_progress' tasks."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        tasks = TaskDB(db)
        try:
            await tasks.init_db()
            id_open = await tasks.create("Open task")
            id_inprogress = await tasks.create("In-progress task")
            await tasks.update(id_inprogress, "Started working on it")

            open_tasks = await tasks.get_open()
            ids = [t["id"] for t in open_tasks]
            assert id_open in ids
            assert id_inprogress in ids
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_task_get_open_empty_when_all_done():
    """get_open() returns empty list when all tasks are done."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        tasks = TaskDB(db)
        try:
            await tasks.init_db()
            task_id = await tasks.create("Finish me")
            await tasks.complete(task_id)

            open_tasks = await tasks.get_open()
            assert open_tasks == []
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_task_update_sets_in_progress_and_scratchpad():
    """update() changes status to 'in_progress' and writes scratchpad."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        tasks = TaskDB(db)
        try:
            await tasks.init_db()
            task_id = await tasks.create("Research quantum computing")
            await tasks.update(task_id, "Found some papers, need to read them.")

            row = await db.fetchone(
                "SELECT status, scratchpad FROM tasks WHERE id = ?", (task_id,)
            )
            assert row["status"] == "in_progress"
            assert row["scratchpad"] == "Found some papers, need to read them."
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_task_complete_sets_done():
    """complete() changes status to 'done'."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        tasks = TaskDB(db)
        try:
            await tasks.init_db()
            task_id = await tasks.create("Learn something new")
            await tasks.complete(task_id)

            row = await db.fetchone(
                "SELECT status FROM tasks WHERE id = ?", (task_id,)
            )
            assert row["status"] == "done"
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_task_summary_no_tasks():
    """summary() returns 'No pending tasks.' when task list is empty."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        tasks = TaskDB(db)
        try:
            await tasks.init_db()
            result = await tasks.summary()
            assert result == "No pending tasks."
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_task_summary_includes_objective_and_status():
    """summary() includes each task's objective and status."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        tasks = TaskDB(db)
        try:
            await tasks.init_db()
            task_id = await tasks.create("Write unit tests")

            result = await tasks.summary()
            assert "Write unit tests" in result
            assert "open" in result
            assert task_id in result
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_task_summary_includes_scratchpad():
    """summary() includes scratchpad notes when present."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        tasks = TaskDB(db)
        try:
            await tasks.init_db()
            task_id = await tasks.create("Build something")
            await tasks.update(task_id, "Already started the scaffolding.")

            result = await tasks.summary()
            assert "Already started the scaffolding." in result
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_task_summary_excludes_done_tasks():
    """summary() does not include completed tasks."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        tasks = TaskDB(db)
        try:
            await tasks.init_db()
            done_id = await tasks.create("Completed task")
            open_id = await tasks.create("Still open")
            await tasks.complete(done_id)

            result = await tasks.summary()
            assert "Still open" in result
            assert "Completed task" not in result
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())


def test_task_full_lifecycle():
    """Full create → update → complete → summary reflects each state change."""

    async def _run():
        db_name = _make_db_name()
        db = ScopedSQLiteHandler(db_name)
        tasks = TaskDB(db)
        try:
            await tasks.init_db()

            task_id = await tasks.create("Explore the universe")

            # After create: appears in get_open with status open
            open_tasks = await tasks.get_open()
            assert any(t["id"] == task_id for t in open_tasks)
            summary = await tasks.summary()
            assert "open" in summary

            # After update: status changes to in_progress
            await tasks.update(task_id, "Started with the observable part.")
            open_tasks = await tasks.get_open()
            task = next(t for t in open_tasks if t["id"] == task_id)
            assert task["status"] == "in_progress"
            assert task["scratchpad"] == "Started with the observable part."

            # After complete: disappears from get_open
            await tasks.complete(task_id)
            open_tasks = await tasks.get_open()
            assert not any(t["id"] == task_id for t in open_tasks)

            summary = await tasks.summary()
            assert "No pending tasks." in summary
        finally:
            await _cleanup(db, db_name)

    asyncio.run(_run())
