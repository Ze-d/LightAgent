"""Data models for the semantic memory system."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class MemoryEntry:
    id: str  # UUID
    scope: str  # "project" | "user" | "session" | "cross_session"
    session_id: str | None = None
    content: str = ""
    embedding: list[float] | None = None
    importance: float = 0.5  # 0.0 - 1.0
    access_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MemorySearchResult:
    entry: MemoryEntry
    score: float  # cosine similarity 0-1
