"""Document memory tools exposed to the agent."""
from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.memory.document_store import DocumentMemoryStore


_memory_store: DocumentMemoryStore | None = None


def init_memory_store(store: DocumentMemoryStore) -> None:
    """Set the shared memory store instance used by all memory tools."""
    global _memory_store
    _memory_store = store


def _get_store() -> DocumentMemoryStore:
    global _memory_store
    if _memory_store is None:
        _memory_store = DocumentMemoryStore()
    return _memory_store


class MemoryReadInput(BaseModel):
    scope: Literal["project", "user", "session", "all"] = Field(
        ...,
        description="Existing memory scope to read. This does not save or modify memory.",
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Required when reading session memory; optional for reading all memory.",
    )


class MemoryAppendSessionSummaryInput(BaseModel):
    session_id: str = Field(..., description="Session ID where the new memory should be stored.")
    summary: str = Field(
        ...,
        description="New fact, preference, decision, or concise session note to remember.",
    )


def memory_read(scope: str, session_id: str | None = None) -> str:
    store = _get_store()
    if scope == "project":
        return store.read_project_memory() or "No project memory recorded."
    if scope == "user":
        return store.read_user_memory() or "No user memory recorded."
    if scope == "session":
        if not session_id:
            return "session_id is required when reading session memory."
        return store.read_session_memory(session_id) or "No session memory recorded."
    if scope == "all":
        context = store.build_context(session_id=session_id)
        return context or "No memory recorded."
    return f"Unknown memory scope: {scope}"


def memory_append_session_summary(session_id: str, summary: str) -> str:
    store = _get_store()
    store.append_session_summary(session_id=session_id, summary=summary)
    return "Session memory appended."


class MemorySearchInput(BaseModel):
    query: str = Field(
        ...,
        description="Natural language search query for semantic memory retrieval.",
    )
    scope: Optional[Literal["project", "user", "session", "all"]] = Field(
        default="all",
        description="Search scope: project, user, session, or all.",
    )
    top_k: int = Field(default=5, ge=1, le=20)


def memory_search(query: str, scope: str = "all", top_k: int = 5) -> str:
    """Semantic search over indexed memory entries.

    Falls back to text-based search when vector store is unavailable.
    """
    store = _get_store()
    vector_store = getattr(store, "_vector_store", None)
    embedding_service = getattr(store, "_embedding_service", None)

    if vector_store is None:
        return "Vector memory store is not enabled. Set MEMORY_VECTOR_ENABLED=true."

    search_scope = None if scope == "all" else scope
    query_embedding = None
    if embedding_service is not None:
        query_embedding = embedding_service.embed(query)

    if query_embedding is not None:
        results = vector_store.search(
            query_embedding, scope=search_scope, top_k=top_k, min_score=0.0,
        )
        if results:
            lines = [f"Semantic search results for: {query}"]
            for r in results:
                lines.append(
                    f"- [{r.entry.scope}] (score: {r.score:.2f}) {r.entry.content[:200]}"
                )
            return "\n".join(lines)

    # Fallback to text search
    entries = vector_store.search_by_text(query, scope=search_scope, top_k=top_k)
    if not entries:
        return f"No memory found matching: {query}"

    lines = [f"Text search results for: {query}"]
    for entry in entries:
        lines.append(f"- [{entry.scope}] {entry.content[:200]}")
    return "\n".join(lines)


class MemoryWriteInput(BaseModel):
    scope: Literal["project", "user"] = Field(
        ...,
        description="Target memory scope to write to.",
    )
    content: str = Field(
        ...,
        description="Memory content to write, in markdown format.",
    )
    mode: Literal["append", "replace"] = Field(
        default="append",
        description="append: add to existing memory; replace: overwrite all content.",
    )


def memory_write(scope: str, content: str, mode: str = "append") -> str:
    store = _get_store()
    if scope == "project":
        store.write_project_memory(content, mode=mode)
        return f"Project memory {mode}ed successfully."
    if scope == "user":
        store.write_user_memory(content, mode=mode)
        return f"User memory {mode}ed successfully."
    return f"Unknown memory scope: {scope}. Use 'project' or 'user'."


class MemoryStatsInput(BaseModel):
    pass


def memory_stats(**kwargs) -> str:
    """Return statistics about the memory system."""
    store = _get_store()
    vector_store = getattr(store, "_vector_store", None)

    lines = ["## Memory Statistics"]

    # File-based stats
    project = store.read_project_memory()
    user = store.read_user_memory()
    lines.append(f"- Project memory: {'present' if project else 'empty'} ({len(project)} chars)")
    lines.append(f"- User memory: {'present' if user else 'empty'} ({len(user)} chars)")

    if vector_store is not None:
        total = vector_store.count()
        by_scope = {}
        for scope in ("project", "user", "session", "cross_session"):
            by_scope[scope] = vector_store.count(scope=scope)
        lines.append(f"- Vector store entries: {total} total")
        for scope, count in by_scope.items():
            lines.append(f"  - {scope}: {count}")
    else:
        lines.append("- Vector store: disabled")

    return "\n".join(lines)


class MemoryConsolidateInput(BaseModel):
    pass


def memory_consolidate(**kwargs) -> str:
    """Manually trigger memory consolidation (dedup, decay, promotion)."""
    store = _get_store()

    # Access consolidator through an internal reference stored on the store
    consolidator = getattr(store, "_consolidator", None)
    if consolidator is None:
        return "Memory consolidator is not available. Set MEMORY_VECTOR_ENABLED=true."

    try:
        stats = consolidator.run()
        return (
            f"Consolidation complete: "
            f"{stats['deduplicated']} deduplicated, "
            f"{stats['decayed']} decayed, "
            f"{stats['promoted']} promoted to cross-session."
        )
    except Exception as exc:
        return f"Consolidation failed: {exc}"
