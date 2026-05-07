"""Memory consolidation: deduplication, importance decay, and cross-session promotion."""
from __future__ import annotations

import threading
import uuid
from datetime import datetime, timedelta
from typing import Any

from app.configs.logger import logger
from app.memory.models import MemoryEntry


class MemoryConsolidator:
    """Periodic maintenance for the vector memory store.

    Responsibilities:
    - Deduplicate near-duplicate entries via cosine similarity
    - Decay importance of stale (unaccessed) entries
    - Promote facts verified across multiple sessions to cross_session scope
    """

    def __init__(
        self,
        vector_store: Any,
        *,
        dedup_threshold: float = 0.92,
        importance_decay: float = 0.1,
        cross_session_threshold: int = 3,
        decay_days: int = 7,
        consolidation_interval: int = 50,
    ) -> None:
        self._vector_store = vector_store
        self.dedup_threshold = dedup_threshold
        self.importance_decay = importance_decay
        self.cross_session_threshold = cross_session_threshold
        self.decay_days = decay_days
        self.consolidation_interval = consolidation_interval
        self._write_count = 0
        self._lock = threading.Lock()

    def on_write(self) -> None:
        """Notify the consolidator that a write occurred.

        Triggers consolidation when the interval threshold is reached.
        """
        with self._lock:
            self._write_count += 1
            if self._write_count >= self.consolidation_interval:
                self._write_count = 0
                # Run consolidation synchronously for simplicity;
                # personal-agent scale makes this acceptable.
                try:
                    self.run()
                except Exception:
                    logger.warning("consolidator event=run_failed", exc_info=True)

    def run(self) -> dict[str, int]:
        """Execute all consolidation passes. Returns a summary of actions."""
        stats: dict[str, int] = {"deduplicated": 0, "decayed": 0, "promoted": 0}

        try:
            dedup_count = self._deduplicate_session_entries()
            stats["deduplicated"] = dedup_count
        except Exception:
            logger.warning("consolidator event=dedup_failed", exc_info=True)

        try:
            decay_count = self._decay_stale_entries()
            stats["decayed"] = decay_count
        except Exception:
            logger.warning("consolidator event=decay_failed", exc_info=True)

        try:
            promote_count = self._promote_cross_session()
            stats["promoted"] = promote_count
        except Exception:
            logger.warning("consolidator event=promote_failed", exc_info=True)

        if any(stats.values()):
            logger.info(
                "consolidator event=run dedup=%d decay=%d promote=%d",
                stats["deduplicated"],
                stats["decayed"],
                stats["promoted"],
            )

        return stats

    # -- Deduplication -------------------------------------------------------

    def _deduplicate_session_entries(self) -> int:
        pairs = self._vector_store.find_duplicates(
            threshold=self.dedup_threshold, scope="session",
        )
        merged = 0
        for a, b, sim in pairs:
            # Keep the entry with higher importance or more recent update
            if a.importance >= b.importance:
                self._vector_store.merge_entries(a.id, b.id)
            else:
                self._vector_store.merge_entries(b.id, a.id)
            merged += 1
        return merged

    # -- Importance decay ----------------------------------------------------

    def _decay_stale_entries(self) -> int:
        """Reduce importance for entries not accessed in decay_days."""
        entries = self._vector_store.list_entries(limit=5000)
        cutoff = (datetime.now() - timedelta(days=self.decay_days)).isoformat(timespec="seconds")
        decayed = 0
        for entry in entries:
            if entry.updated_at > cutoff:
                continue
            new_imp = max(0.0, entry.importance - self.importance_decay)
            if new_imp <= 0.1:
                # Archive by deleting; file system source of truth remains.
                self._vector_store.delete(entry.id)
            else:
                self._vector_store.add(MemoryEntry(
                    id=entry.id,
                    scope=entry.scope,
                    session_id=entry.session_id,
                    content=entry.content,
                    embedding=entry.embedding,
                    importance=new_imp,
                    access_count=entry.access_count,
                    created_at=entry.created_at,
                    updated_at=datetime.now().isoformat(timespec="seconds"),
                    metadata=entry.metadata,
                ))
            decayed += 1
        return decayed

    # -- Cross-session promotion ---------------------------------------------

    def _promote_cross_session(self) -> int:
        """Find similar facts appearing across sessions and promote them."""
        # Group entries by approximate content match (rough heuristic).
        entries = self._vector_store.list_entries(scope="session", limit=5000)
        if len(entries) < self.cross_session_threshold:
            return 0

        # Build content fingerprint groups
        groups: dict[str, list[MemoryEntry]] = {}
        for entry in entries:
            fingerprint = self._fingerprint(entry.content)
            groups.setdefault(fingerprint, []).append(entry)

        promoted = 0
        for fingerprint, group in groups.items():
            unique_sessions = set(
                e.session_id for e in group if e.session_id
            )
            if len(unique_sessions) >= self.cross_session_threshold:
                # Pick the best representative
                best = max(group, key=lambda e: e.importance)
                best.scope = "cross_session"
                best.importance = min(1.0, best.importance + 0.2)
                self._vector_store.add(best)
                promoted += 1

        return promoted

    @staticmethod
    def _fingerprint(content: str, n: int = 3) -> str:
        """Create a rough content fingerprint using character n-grams."""
        content = content.lower().strip()
        if len(content) < n:
            return content
        grams = {content[i:i+n] for i in range(len(content)-n+1)}
        # Sort and take hash of top grams for stability
        return str(hash("".join(sorted(grams)[:20])))

    # -- Knowledge fact storage ----------------------------------------------

    def store_knowledge_facts(
        self,
        facts: list[dict[str, Any]],
        session_id: str,
    ) -> int:
        """Store extracted knowledge facts as cross-session memory entries."""
        if not facts:
            return 0

        count = 0
        for fact in facts:
            content = f"[{fact.get('category', 'fact')}] {fact.get('fact', '')}"
            confidence = fact.get("confidence", 0.5)
            entry = MemoryEntry(
                id=uuid.uuid4().hex,
                scope="cross_session",
                session_id=session_id,
                content=content,
                embedding=None,  # Will be indexed later if embedding service available
                importance=confidence,
                access_count=1,
                metadata={
                    "category": fact.get("category", "fact"),
                    "confidence": confidence,
                    "source_session": session_id,
                },
            )
            self._vector_store.add(entry)
            count += 1

        return count
