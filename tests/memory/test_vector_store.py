"""Tests for VectorMemoryStore."""
import tempfile
from pathlib import Path

import pytest

from app.memory.models import MemoryEntry
from app.memory.vector_store import VectorMemoryStore


class TestVectorMemoryStore:
    def _store(self) -> VectorMemoryStore:
        db_path = Path(tempfile.mkdtemp()) / "test_memory.db"
        return VectorMemoryStore(db_path)

    def test_add_and_get(self):
        store = self._store()
        entry = MemoryEntry(
            id="e1",
            scope="session",
            session_id="s1",
            content="The user asked about the project architecture.",
            embedding=[0.1, 0.2, 0.3],
            importance=0.7,
        )
        store.add(entry)

        retrieved = store.get("e1")
        assert retrieved is not None
        assert retrieved.content == entry.content
        assert retrieved.scope == "session"
        assert retrieved.session_id == "s1"
        assert retrieved.importance == 0.7

    def test_add_generates_id_when_empty(self):
        store = self._store()
        entry = MemoryEntry(
            id="",
            scope="project",
            content="Project uses FastAPI.",
            embedding=[0.5, 0.5],
        )
        new_id = store.add(entry)
        assert new_id
        assert len(new_id) == 32  # hex uuid

    def test_count_by_scope(self):
        store = self._store()
        store.add(MemoryEntry(id="a", scope="session", content="s1", embedding=[0.1]))
        store.add(MemoryEntry(id="b", scope="session", content="s2", embedding=[0.2]))
        store.add(MemoryEntry(id="c", scope="project", content="p1", embedding=[0.3]))

        assert store.count() == 3
        assert store.count(scope="session") == 2
        assert store.count(scope="project") == 1
        assert store.count(scope="user") == 0

    def test_delete(self):
        store = self._store()
        store.add(MemoryEntry(id="e1", scope="session", content="test", embedding=[0.1]))
        assert store.get("e1") is not None

        store.delete("e1")
        assert store.get("e1") is None

    def test_update_importance(self):
        store = self._store()
        store.add(MemoryEntry(
            id="e1", scope="session", content="test",
            embedding=[0.1], importance=0.5, access_count=0,
        ))

        store.update_importance("e1", 0.1)
        entry = store.get("e1")
        assert entry is not None
        assert entry.importance == 0.6
        assert entry.access_count == 1

    def test_search_by_embedding(self):
        store = self._store()
        # Add entries with known embeddings
        store.add(MemoryEntry(
            id="a", scope="session", content="Python programming tips",
            embedding=[1.0, 0.0, 0.0],
        ))
        store.add(MemoryEntry(
            id="b", scope="session", content="Cooking recipes for pasta",
            embedding=[0.0, 1.0, 0.0],
        ))
        store.add(MemoryEntry(
            id="c", scope="session", content="Python FastAPI guide",
            embedding=[0.9, 0.1, 0.0],
        ))

        # Search with query embedding close to Python topics
        results = store.search([1.0, 0.1, 0.0], top_k=2)
        assert len(results) == 2
        # First result should be the most similar (Python programming)
        assert results[0].entry.id in ("a", "c")
        assert results[0].score > 0.9

    def test_search_with_min_score(self):
        store = self._store()
        store.add(MemoryEntry(
            id="a", scope="session", content="Python",
            embedding=[1.0, 0.0],
        ))
        store.add(MemoryEntry(
            id="b", scope="session", content="Cooking",
            embedding=[0.0, 1.0],
        ))

        results = store.search([1.0, 0.0], min_score=0.8)
        assert len(results) == 1
        assert results[0].entry.id == "a"

    def test_search_by_text_fallback(self):
        store = self._store()
        store.add(MemoryEntry(
            id="a", scope="session", content="FastAPI deployment guide",
            embedding=None,
        ))

        results = store.search_by_text("deployment", top_k=3)
        assert len(results) == 1
        assert "FastAPI" in results[0].content

    def test_find_duplicates(self):
        store = self._store()
        store.add(MemoryEntry(
            id="a", scope="session", content="User prefers dark mode",
            embedding=[1.0, 0.0],
        ))
        store.add(MemoryEntry(
            id="b", scope="session", content="User likes dark theme",
            embedding=[0.99, 0.01],  # Nearly identical
        ))
        store.add(MemoryEntry(
            id="c", scope="session", content="User enjoys cooking",
            embedding=[0.0, 1.0],  # Very different
        ))

        pairs = store.find_duplicates(threshold=0.9, scope="session")
        assert len(pairs) == 1
        a, b, sim = pairs[0]
        assert sim >= 0.9

    def test_merge_entries(self):
        store = self._store()
        store.add(MemoryEntry(
            id="keep", scope="session", content="This will stay",
            embedding=[0.5], importance=0.8, access_count=5,
        ))
        store.add(MemoryEntry(
            id="discard", scope="session", content="This will go",
            embedding=[0.5], importance=0.3, access_count=3,
        ))

        store.merge_entries("keep", "discard")

        assert store.get("keep") is not None
        assert store.get("discard") is None
        kept = store.get("keep")
        assert kept is not None
        assert kept.access_count == 8  # 5 + 3
        assert kept.importance == 0.8  # max(0.8, 0.3)

    def test_list_entries_with_filters(self):
        store = self._store()
        store.add(MemoryEntry(
            id="a", scope="session", session_id="s1", content="s1 data",
        ))
        store.add(MemoryEntry(
            id="b", scope="session", session_id="s2", content="s2 data",
        ))
        store.add(MemoryEntry(
            id="c", scope="cross_session", content="cross data",
        ))

        results = store.list_entries(session_id="s1")
        assert len(results) == 1
        assert results[0].id == "a"

        results = store.list_entries(scope="session", limit=10)
        assert len(results) == 2
