"""File-backed memory store for project, user, and session context."""
from __future__ import annotations

import re
import threading
from datetime import datetime
from pathlib import Path

from app.memory.summarizer import MessageSummarizer


class DocumentMemoryStore:
    def __init__(
        self,
        base_dir: str | Path = ".memory",
        *,
        max_session_entries: int = 100,
    ) -> None:
        self.base_dir = Path(base_dir)
        self.project_file = self.base_dir / "project.md"
        self.user_file = self.base_dir / "user.md"
        self.sessions_dir = self.base_dir / "sessions"
        self.tasks_dir = self.base_dir / "tasks"
        self.max_session_entries = max_session_entries
        self.summarizer = MessageSummarizer()
        self._lock = threading.Lock()
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

    def _truncate(self, content: str, max_chars: int = 800) -> str:
        collapsed = " ".join(content.split())
        if len(collapsed) <= max_chars:
            return collapsed
        return collapsed[: max_chars - 3] + "..."
