"""Verification tests for new features: async tools, memory summarizer, and input guard."""
import pytest
import asyncio
from pathlib import Path
from uuid import uuid4
from app.core.tool_registry import ToolRegistry
from app.memory.document_store import DocumentMemoryStore
from app.memory.summarizer import MessageSummarizer
from app.security.input_guard import InputGuardMiddleware
from app.core.middleware import MiddlewareAbort
from app.tools import memory_tools
from app.tools.register import build_default_registry


class TestAsyncToolSupport:
    def test_tool_registry_sync_tool(self):
        """Test that sync tools still work via call()."""
        registry = ToolRegistry()
        registry.register({
            "name": "test_sync",
            "description": "A sync tool",
            "parameters": {"type": "object", "properties": {}},
            "handler": lambda: "sync_result",
        })

        assert not registry.is_async("test_sync")
        result = registry.call("test_sync")
        assert result == "sync_result"

    def test_tool_registry_async_tool(self):
        """Test that async tools work via call_async()."""
        registry = ToolRegistry()

        async def async_handler() -> str:
            await asyncio.sleep(0.01)
            return "async_result"

        registry.register({
            "name": "test_async",
            "description": "An async tool",
            "parameters": {"type": "object", "properties": {}},
            "handler": async_handler,
        })

        assert registry.is_async("test_async")
        result = asyncio.run(registry.call_async("test_async"))
        assert result == "async_result"


class TestMemorySummarizer:
    def test_no_summarize_when_small(self):
        """Test that small message lists are not summarized."""
        summarizer = MessageSummarizer(target_messages=10)
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]
        result = summarizer.summarize(messages)
        assert len(result) == 2

    def test_summarize_large_history(self):
        """Test that large histories are summarized."""
        summarizer = MessageSummarizer(target_messages=5)
        messages = [{"role": "system", "content": "You are a helpful assistant."}]
        for i in range(20):
            messages.append({"role": "user", "content": f"Message {i}"})
            messages.append({"role": "assistant", "content": f"Response {i}"})

        result = summarizer.summarize(messages)
        assert len(result) <= 6
        assert result[0]["role"] == "system"

    def test_preserve_system_message(self):
        """Test that system message is preserved."""
        summarizer = MessageSummarizer(target_messages=5, preserve_system=True)
        messages = [{"role": "system", "content": "System prompt"}]
        for i in range(15):
            messages.append({"role": "user", "content": f"Msg {i}"})

        result = summarizer.summarize(messages)
        assert result[0]["role"] == "system"
        assert result[0]["content"] == "System prompt"

    def test_summary_contains_structured_context(self):
        summarizer = MessageSummarizer(target_messages=4)
        messages = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "Plan SQLite persistence"},
            {"role": "assistant", "content": "Implemented SQLite state stores"},
            {"role": "user", "content": "Add token budgeting"},
            {"role": "assistant", "content": "Added token budget trimmer"},
            {"role": "user", "content": "Continue"},
        ]

        result = summarizer.summarize(messages)

        summary = result[1]["content"]
        assert summary.startswith("[Previous conversation summary]")
        assert "User topics:" in summary
        assert "Assistant covered:" in summary
        assert "SQLite persistence" in summary

    def test_existing_summary_is_merged_not_preserved_as_prompt(self):
        summarizer = MessageSummarizer(target_messages=4)
        messages = [
            {"role": "system", "content": "System prompt"},
            {
                "role": "system",
                "content": "[Previous conversation summary]\nOld context",
            },
            {"role": "user", "content": "New topic"},
            {"role": "assistant", "content": "New answer"},
            {"role": "user", "content": "Latest"},
        ]

        result = summarizer.summarize(messages)

        assert result[0]["content"] == "System prompt"
        assert result[1]["content"].startswith("[Previous conversation summary]")
        assert "Existing summary:" in result[1]["content"]
        assert result[-1]["content"] == "Latest"


class TestDocumentMemoryStore:
    def _store(self) -> DocumentMemoryStore:
        return DocumentMemoryStore(Path("test-runtime") / "memory" / str(uuid4()))

    def test_comment_only_defaults_do_not_enter_context(self):
        store = self._store()
        session_id = f"test-{uuid4()}"

        assert store.build_context(session_id=session_id) == ""

    def test_builds_context_from_project_user_and_session_memory(self):
        store = self._store()
        session_id = f"test-{uuid4()}"
        store.append_session_summary(session_id, "- User asked about memory.")

        context = store.build_context(session_id=session_id)

        assert "[Session Memory]" in context
        assert "User asked about memory." in context

    def test_session_exchange_memory_is_structured(self):
        store = self._store()
        session_id = f"test-{uuid4()}"

        store.append_session_exchange(
            session_id=session_id,
            user_message="Please remember my deployment preference.",
            assistant_message="I will keep SQLite as the default local backend.",
        )

        memory = store.read_session_memory(session_id)
        assert "User intent:" in memory
        assert "Assistant response:" in memory
        assert "SQLite as the default local backend" in memory

    def test_session_memory_prunes_old_entries(self):
        store = DocumentMemoryStore(
            Path("test-runtime") / "memory" / str(uuid4()),
            max_session_entries=2,
        )
        session_id = f"test-{uuid4()}"

        store.append_session_summary(session_id, "- first")
        store.append_session_summary(session_id, "- second")
        store.append_session_summary(session_id, "- third")

        memory = store.read_session_memory(session_id)
        assert "first" not in memory
        assert "second" in memory
        assert "third" in memory

    def test_memory_tools_use_document_store(self):
        store = self._store()
        session_id = f"test-{uuid4()}"
        memory_tools.init_memory_store(store)

        registry = build_default_registry()
        append_result = registry.call(
            "memory_append_session_summary",
            session_id=session_id,
            summary="- Remember this session.",
        )
        read_result = registry.call(
            "memory_read",
            scope="session",
            session_id=session_id,
        )

        assert append_result == "Session memory appended."
        assert "Remember this session." in read_result


class TestInputGuardMiddleware:
    def test_allows_normal_input(self):
        """Test that normal input passes through."""
        guard = InputGuardMiddleware()
        context = {
            "current_input": [{"role": "user", "content": "Hello, how are you?"}]
        }
        result = guard.before_llm(context)
        assert "Hello, how are you?" in result["current_input"][0]["content"]

    def test_blocks_html_tags(self):
        """Test that HTML tags are blocked."""
        guard = InputGuardMiddleware(block_html=True)
        context = {
            "current_input": [{"role": "user", "content": "<script>alert('xss')</script>"}]
        }
        result = guard.before_llm(context)
        assert "[HTML_REMOVED]" in result["current_input"][0]["content"]
        assert "<script>" not in result["current_input"][0]["content"]

    def test_blocks_sql_injection(self):
        """Test that SQL injection patterns are blocked."""
        guard = InputGuardMiddleware(block_sql=True)
        context = {
            "current_input": [{"role": "user", "content": "'; DROP TABLE users; --"}]
        }
        result = guard.before_llm(context)
        assert "[SQL_REMOVED]" in result["current_input"][0]["content"]

    def test_blocks_path_traversal(self):
        """Test that path traversal is blocked."""
        guard = InputGuardMiddleware(block_path_traversal=True)
        context = {
            "current_input": [{"role": "user", "content": "../../../etc/passwd"}]
        }
        result = guard.before_llm(context)
        assert "[PATH_REMOVED]" in result["current_input"][0]["content"]

    def test_rejects_overlength_input(self):
        """Test that overlength input raises MiddlewareAbort."""
        guard = InputGuardMiddleware(max_length=50)
        context = {
            "current_input": [{"role": "user", "content": "x" * 100}]
        }
        with pytest.raises(MiddlewareAbort):
            guard.before_llm(context)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
