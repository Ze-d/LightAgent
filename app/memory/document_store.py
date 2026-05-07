"""File-backed memory store for project, user, and session context."""
from __future__ import annotations

import re
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from app.configs.logger import logger
from app.memory.summarizer import MessageSummarizer


class DocumentMemoryStore:
    def __init__(
        self,
        base_dir: str | Path = ".memory",
        *,
        max_session_entries: int = 100,
        vector_store: Any = None,
        embedding_service: Any = None,
    ) -> None:
        self.base_dir = Path(base_dir)
        self.project_file = self.base_dir / "project.md"
        self.user_file = self.base_dir / "user.md"
        self.sessions_dir = self.base_dir / "sessions"
        self.tasks_dir = self.base_dir / "tasks"
        self.max_session_entries = max_session_entries
        self.summarizer = MessageSummarizer()
        self._lock = threading.Lock()
        self._vector_store = vector_store
        self._embedding_service = embedding_service
        self.ensure_layout()

    def ensure_layout(self) -> None:
        with self._lock:
            self.base_dir.mkdir(parents=True, exist_ok=True)
            self.sessions_dir.mkdir(parents=True, exist_ok=True)
            self.tasks_dir.mkdir(parents=True, exist_ok=True)
            self._ensure_file(
                self.project_file,
                "<!-- Add stable project context, architecture notes, and conventions here. -->\n",
            )
            self._ensure_file(
                self.user_file,
                "<!-- Add stable user preferences, style choices, and recurring constraints here. -->\n",
            )

    def read_project_memory(self) -> str:
        return self._read_memory_file(self.project_file)

    def read_user_memory(self) -> str:
        return self._read_memory_file(self.user_file)

    def read_session_memory(self, session_id: str) -> str:
        return self._read_memory_file(self._session_file(session_id))

    def write_project_memory(self, content: str, mode: str = "append") -> None:
        """Write to project memory. mode: 'append' or 'replace'."""
        content = content.strip()
        if not content:
            return
        with self._lock:
            if mode == "replace":
                self.project_file.write_text(content + "\n", encoding="utf-8")
            else:
                with self.project_file.open("a", encoding="utf-8") as f:
                    f.write("\n" + content + "\n")
        # Re-index after write
        self.index_project_memory()

    def write_user_memory(self, content: str, mode: str = "append") -> None:
        """Write to user memory. mode: 'append' or 'replace'."""
        content = content.strip()
        if not content:
            return
        with self._lock:
            if mode == "replace":
                self.user_file.write_text(content + "\n", encoding="utf-8")
            else:
                with self.user_file.open("a", encoding="utf-8") as f:
                    f.write("\n" + content + "\n")
        self.index_user_memory()

    def append_session_summary(self, session_id: str, summary: str) -> None:
        summary = summary.strip()
        if not summary:
            return

        timestamp = datetime.now().isoformat(timespec="seconds")
        entry = f"\n## {timestamp}\n\n{summary}\n"
        session_file = self._session_file(session_id)
        self._append(session_file, entry)
        self._prune_session_file(session_file)

    def append_session_exchange(
        self,
        session_id: str,
        user_message: str,
        assistant_message: str,
    ) -> None:
        summary = self.summarizer.summarize_exchange(
            user_message=user_message,
            assistant_message=assistant_message,
        )
        self.append_session_summary(session_id, summary)

    def build_context(self, session_id: str | None = None) -> str:
        sections: list[str] = []
        project_memory = self.read_project_memory()
        user_memory = self.read_user_memory()

        if project_memory:
            sections.append(f"[Project Memory]\n{project_memory}")
        if user_memory:
            sections.append(f"[User Memory]\n{user_memory}")
        if session_id:
            session_memory = self.read_session_memory(session_id)
            if session_memory:
                sections.append(f"[Session Memory]\n{session_memory}")

        return "\n\n".join(sections)

    def semantic_build_context(
        self,
        query: str,
        session_id: str | None = None,
        *,
        top_k: int = 5,
        min_score: float = 0.3,
    ) -> str:
        """Build context via semantic search over indexed memory entries.

        Falls back to full text build_context() when vector store or embedding
        service is unavailable.
        """
        if self._vector_store is None or self._embedding_service is None:
            return self.build_context(session_id=session_id)

        query_embedding = self._embedding_service.embed(query)
        if query_embedding is None:
            # Embedding failed; try text search then fall back to full dump.
            return self._text_search_context(query, session_id, top_k) or self.build_context(session_id=session_id)

        sections: list[str] = []

        # Search project-level memory
        project_results = self._vector_store.search(
            query_embedding, scope="project", top_k=top_k, min_score=min_score,
        )
        for r in project_results:
            sections.append(
                f"[Memory - Project] (relevance: {r.score:.2f})\n{r.entry.content}"
            )

        # Search user-level memory
        user_results = self._vector_store.search(
            query_embedding, scope="user", top_k=top_k, min_score=min_score,
        )
        for r in user_results:
            sections.append(
                f"[Memory - User] (relevance: {r.score:.2f})\n{r.entry.content}"
            )

        # Search session-level memory
        if session_id:
            session_results = self._vector_store.search(
                query_embedding, scope="session", top_k=top_k, min_score=min_score,
            )
            for r in session_results:
                if r.entry.session_id == session_id:
                    sections.append(
                        f"[Memory - Session] (relevance: {r.score:.2f})\n{r.entry.content}"
                    )

        # Also search cross-session knowledge
        cross_results = self._vector_store.search(
            query_embedding, scope="cross_session", top_k=top_k, min_score=min_score,
        )
        for r in cross_results:
            sections.append(
                f"[Memory - Knowledge] (relevance: {r.score:.2f})\n{r.entry.content}"
            )

        return "\n\n".join(sections) if sections else self.build_context(session_id=session_id)

    def _text_search_context(
        self,
        query: str,
        session_id: str | None,
        top_k: int,
    ) -> str | None:
        """Text-based fallback when embedding fails."""
        if self._vector_store is None:
            return None
        entries = self._vector_store.search_by_text(query, top_k=top_k)
        if not entries:
            return None
        sections: list[str] = []
        for entry in entries:
            sections.append(f"[Memory - {entry.scope}] (text match)\n{entry.content}")
        return "\n\n".join(sections)

    # -- Vector store indexing helpers ----------------------------------------

    def _index_entry(
        self,
        entry_id: str,
        scope: str,
        session_id: str | None,
        content: str,
    ) -> None:
        """Index a memory entry into the vector store."""
        if self._vector_store is None or self._embedding_service is None:
            return
        embedding = self._embedding_service.embed(content)
        if embedding is None:
            return
        from app.memory.models import MemoryEntry
        entry = MemoryEntry(
            id=entry_id,
            scope=scope,
            session_id=session_id,
            content=content,
            embedding=embedding,
        )
        try:
            self._vector_store.add(entry)
        except Exception:
            logger.warning(
                "document_memory event=index_failed entry_id=%s scope=%s",
                entry_id,
                scope,
                exc_info=True,
            )

    def index_session_entry(
        self,
        session_id: str,
        summary: str,
    ) -> str | None:
        """Index a single session summary into the vector store. Returns entry id."""
        entry_id = uuid.uuid4().hex
        self._index_entry(entry_id, "session", session_id, summary)
        return entry_id

    def index_project_memory(self) -> None:
        """Index the project.md content into the vector store."""
        content = self.read_project_memory()
        if not content:
            return
        # Remove old project entries
        if self._vector_store is not None:
            for entry in self._vector_store.list_entries(scope="project", limit=1000):
                self._vector_store.delete(entry.id)
        self._index_entry(
            uuid.uuid4().hex,
            "project",
            None,
            f"[Project Memory]\n{content}",
        )

    def index_user_memory(self) -> None:
        """Index the user.md content into the vector store."""
        content = self.read_user_memory()
        if not content:
            return
        if self._vector_store is not None:
            for entry in self._vector_store.list_entries(scope="user", limit=1000):
                self._vector_store.delete(entry.id)
        self._index_entry(
            uuid.uuid4().hex,
            "user",
            None,
            f"[User Memory]\n{content}",
        )

    def _session_file(self, session_id: str) -> Path:
        safe_id = self._safe_name(session_id)
        return self.sessions_dir / f"{safe_id}.md"

    def _safe_name(self, value: str) -> str:
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
        if not safe:
            raise ValueError("Memory file name cannot be empty")
        return safe[:128]

    def _ensure_file(self, path: Path, default_content: str) -> None:
        if not path.exists():
            path.write_text(default_content, encoding="utf-8")

    def _read_memory_file(self, path: Path) -> str:
        if not path.exists():
            return ""

        with self._lock:
            content = path.read_text(encoding="utf-8").strip()
        if self._is_comment_only(content):
            return ""
        return content

    def _append(self, path: Path, content: str) -> None:
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as file:
                file.write(content)

    def _prune_session_file(self, path: Path) -> None:
        if self.max_session_entries <= 0 or not path.exists():
            return

        with self._lock:
            content = path.read_text(encoding="utf-8")
            entries = self._split_session_entries(content)
            if len(entries) <= self.max_session_entries:
                return
            retained = entries[-self.max_session_entries:]
            path.write_text("\n".join(retained).strip() + "\n", encoding="utf-8")

    def _split_session_entries(self, content: str) -> list[str]:
        entries: list[str] = []
        current: list[str] = []
        for line in content.splitlines():
            if line.startswith("## ") and current:
                entries.append("\n".join(current).strip())
                current = [line]
            else:
                current.append(line)
        if current:
            entry = "\n".join(current).strip()
            if entry:
                entries.append(entry)
        return entries

    def _is_comment_only(self, content: str) -> bool:
        return content.startswith("<!--") and content.endswith("-->")

