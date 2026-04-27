"""Document memory tools exposed to the agent."""
from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.memory.document_store import DocumentMemoryStore


_memory_store = DocumentMemoryStore()


class MemoryReadInput(BaseModel):
    scope: Literal["project", "user", "session", "all"] = Field(
        ...,
        description="Memory scope to read.",
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Required when scope is 'session'; optional for 'all'.",
    )


class MemoryAppendSessionSummaryInput(BaseModel):
    session_id: str = Field(..., description="Session ID to append memory to.")
    summary: str = Field(..., description="Concise memory summary to append.")


def memory_read(scope: str, session_id: str | None = None) -> str:
    if scope == "project":
        return _memory_store.read_project_memory() or "No project memory recorded."
    if scope == "user":
        return _memory_store.read_user_memory() or "No user memory recorded."
    if scope == "session":
        if not session_id:
            return "session_id is required when reading session memory."
        return _memory_store.read_session_memory(session_id) or "No session memory recorded."
    if scope == "all":
        context = _memory_store.build_context(session_id=session_id)
        return context or "No memory recorded."
    return f"Unknown memory scope: {scope}"


def memory_append_session_summary(session_id: str, summary: str) -> str:
    _memory_store.append_session_summary(session_id=session_id, summary=summary)
    return "Session memory appended."
