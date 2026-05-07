"""Tests for MemoryConsolidator."""
import tempfile
from pathlib import Path

from app.memory.models import MemoryEntry
from app.memory.vector_store import VectorMemoryStore
from app.memory.consolidator import MemoryConsolidator


class TestMemoryConsolidator:
    def _store_and_consolidator(self, **kwargs):
        db_path = Path(tempfile.mkdtemp()) / "test_memory.db"
        store = VectorMemoryStore(db_path)
        consolidator = MemoryConsolidator(
            vector_store=store,
            dedup_threshold=kwargs.get("dedup_threshold", 0.92),
            importance_decay=kwargs.get("importance_decay", 0.1),
            cross_session_threshold=kwargs.get("cross_session_threshold", 3),
            decay_days=kwargs.get("decay_days", 7),
            consolidation_interval=kwargs.get("consolidation_interval", 50),
        )
        return store, consolidator

    def test_run_returns_stats(self):
        store, consolidator = self._store_and_consolidator()
        stats = consolidator.run()
        assert "deduplicated" in stats
        assert "decayed" in stats
        assert "promoted" in stats
        assert stats["deduplicated"] == 0
        assert stats["decayed"] == 0
        assert stats["promoted"] == 0

    def test_deduplication(self):
        store, consolidator = self._store_and_consolidator(dedup_threshold=0.9)
        store.add(MemoryEntry(
            id="a", scope="session", content="Same content",
            embedding=[1.0, 0.0],
        ))
        store.add(MemoryEntry(
            id="b", scope="session", content="Same content",
            embedding=[0.999, 0.001],  # Nearly identical
        ))

        stats = consolidator.run()
        assert stats["deduplicated"] == 1
        # One entry should survive, the other merged
        surviving = store.get("a")
        if surviving is None:
            surviving = store.get("b")
        assert surviving is not None
        assert surviving.access_count == 0  # Both had access_count=0

    def test_write_counting(self):
        store, consolidator = self._store_and_consolidator(consolidation_interval=3)

        consolidator.on_write()
        consolidator.on_write()
        consolidator.on_write()  # This should trigger consolidation

        # After consolidation, count should reset
        consolidator.on_write()
        assert consolidator._write_count == 1

    def test_store_knowledge_facts(self):
        store, consolidator = self._store_and_consolidator()

        facts = [
            {"fact": "User prefers concise answers", "category": "preference", "confidence": 0.9},
            {"fact": "Project uses SQLite", "category": "fact", "confidence": 0.95},
        ]
        count = consolidator.store_knowledge_facts(facts, "session-1")
        assert count == 2

        entries = store.list_entries(scope="cross_session")
        assert len(entries) == 2

    def test_fingerprint_stability(self):
        store = VectorMemoryStore(Path(tempfile.mkdtemp()) / "test.db")
        consolidator = MemoryConsolidator(
            vector_store=store,
            dedup_threshold=0.9,
            importance_decay=0.1,
            cross_session_threshold=3,
        )
        fp1 = consolidator._fingerprint("The user asked about Python programming")
        fp2 = consolidator._fingerprint("The user asked about Python programming")
        assert fp1 == fp2

        fp3 = consolidator._fingerprint("Completely different topic here")
        assert fp1 != fp3

    def test_promote_cross_session(self):
        store, consolidator = self._store_and_consolidator(cross_session_threshold=2)
        store.add(MemoryEntry(
            id="a", scope="session", session_id="s1",
            content="User likes dark mode",
            embedding=[0.5, 0.5],
        ))
        store.add(MemoryEntry(
            id="b", scope="session", session_id="s2",
            content="User likes dark mode",
            embedding=[0.5, 0.5],
        ))

        promoted = consolidator._promote_cross_session()
        assert promoted >= 1
