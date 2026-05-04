from app.core.context_builder import ContextBuilder, MEMORY_CONTEXT_PREFIX
from app.core.context_state import ContextState


class FakeMemoryStore:
    def __init__(self, context: str = "") -> None:
        self.context = context
        self.calls: list[str | None] = []

    def build_context(self, session_id: str | None = None) -> str:
        self.calls.append(session_id)
        return self.context


def _state() -> ContextState:
    return ContextState(
        session_id="session-1",
        channel="chat",
        provider="openai",
        provider_mode="openai_previous_response",
        last_response_id="resp_123",
        history_version=2,
        metadata={"tenant": "test"},
    )


def test_builds_envelope_without_memory():
    memory_store = FakeMemoryStore()
    builder = ContextBuilder(memory_store=memory_store)
    history = [
        {"role": "system", "content": "System prompt"},
        {"role": "user", "content": "hello"},
    ]

    envelope = builder.build(context_state=_state(), history=history)

    assert envelope.messages == history
    assert envelope.clean_history == history
    assert envelope.memory_injected is False
    assert envelope.provider_state.provider == "openai"
    assert envelope.provider_state.provider_mode == "openai_previous_response"
    assert envelope.provider_state.last_response_id == "resp_123"
    assert envelope.history_version == 2
    assert envelope.budget.status == "not_applied"
    assert envelope.summary_messages == []
    assert envelope.tool_outputs == []
    assert envelope.checkpoint_input is None
    assert envelope.metadata == {"tenant": "test"}
    assert memory_store.calls == ["session-1"]


def test_injects_memory_after_system_prompt():
    builder = ContextBuilder(memory_store=FakeMemoryStore("[Session Memory]\nremember"))
    history = [
        {"role": "system", "content": "System prompt"},
        {"role": "user", "content": "hello"},
    ]

    envelope = builder.build(context_state=_state(), history=history)

    assert envelope.memory_injected is True
    assert envelope.memory_context == "[Session Memory]\nremember"
    assert envelope.messages[0] == history[0]
    assert envelope.messages[1] == {
        "role": "system",
        "content": f"{MEMORY_CONTEXT_PREFIX}[Session Memory]\nremember",
    }
    assert envelope.messages[2] == history[1]


def test_strips_existing_transient_memory_before_rebuilding():
    builder = ContextBuilder(memory_store=FakeMemoryStore("fresh"))
    history = [
        {"role": "system", "content": "System prompt"},
        {"role": "system", "content": f"{MEMORY_CONTEXT_PREFIX}stale"},
        {"role": "user", "content": "hello"},
    ]

    envelope = builder.build(context_state=_state(), history=history)

    assert envelope.clean_history == [
        {"role": "system", "content": "System prompt"},
        {"role": "user", "content": "hello"},
    ]
    assert "stale" not in "\n".join(message["content"] for message in envelope.messages)
    assert "fresh" in envelope.messages[1]["content"]


def test_returns_copies_not_mutable_history_references():
    builder = ContextBuilder(memory_store=FakeMemoryStore())
    history = [{"role": "user", "content": "hello"}]

    envelope = builder.build(context_state=_state(), history=history)
    envelope.messages[0]["content"] = "mutated"

    assert history == [{"role": "user", "content": "hello"}]


def test_preserves_future_context_inputs_as_copies():
    builder = ContextBuilder(memory_store=FakeMemoryStore())
    summary_messages = [{"role": "system", "content": "summary"}]
    tool_outputs = [{"type": "function_call_output", "call_id": "1", "output": "ok"}]
    checkpoint_input = [{"role": "user", "content": "checkpoint"}]

    envelope = builder.build(
        context_state=_state(),
        history=[{"role": "user", "content": "hello"}],
        summary_messages=summary_messages,
        tool_outputs=tool_outputs,
        checkpoint_input=checkpoint_input,
    )
    summary_messages[0]["content"] = "mutated"
    tool_outputs[0]["output"] = "mutated"
    checkpoint_input[0]["content"] = "mutated"

    assert envelope.summary_messages == [{"role": "system", "content": "summary"}]
    assert envelope.tool_outputs == [
        {"type": "function_call_output", "call_id": "1", "output": "ok"}
    ]
    assert envelope.checkpoint_input == [{"role": "user", "content": "checkpoint"}]


def test_applies_token_budget_to_context_messages():
    builder = ContextBuilder(
        memory_store=FakeMemoryStore(),
        max_input_tokens=45,
    )
    history = [
        {"role": "system", "content": "System prompt"},
        {"role": "user", "content": "old " * 40},
        {"role": "assistant", "content": "old answer " * 40},
        {"role": "user", "content": "new question"},
    ]

    envelope = builder.build(context_state=_state(), history=history)

    assert envelope.messages == [
        {"role": "system", "content": "System prompt"},
        {"role": "user", "content": "new question"},
    ]
    assert envelope.clean_history == history
    assert envelope.budget.status == "estimated"
    assert envelope.budget.reason == "trimmed_history"
    assert envelope.budget.dropped_messages == 2
    assert envelope.budget.max_input_tokens == 45


def test_token_budget_can_drop_transient_memory_context():
    builder = ContextBuilder(
        memory_store=FakeMemoryStore("remember " * 60),
        max_input_tokens=35,
    )
    history = [
        {"role": "system", "content": "System prompt"},
        {"role": "user", "content": "new question"},
    ]

    envelope = builder.build(context_state=_state(), history=history)

    assert envelope.memory_context
    assert envelope.memory_injected is False
    assert envelope.messages == history
    assert envelope.budget.reason == "trimmed_history_and_optional_system"


def test_memory_context_has_own_budget_before_injection():
    memory_context = (
        "[Project Memory]\n" + "stable convention " * 50
        + "\n\n[Session Memory]\n"
        + "old detail " * 80
        + "latest decision"
    )
    builder = ContextBuilder(
        memory_store=FakeMemoryStore(memory_context),
        memory_max_tokens=60,
        max_input_tokens=200,
    )
    history = [
        {"role": "system", "content": "System prompt"},
        {"role": "user", "content": "new question"},
    ]

    envelope = builder.build(context_state=_state(), history=history)

    assert envelope.memory_truncated is True
    assert envelope.memory_context_tokens <= 60
    assert envelope.memory_max_tokens == 60
    assert "[Project Memory]" in envelope.memory_context
    assert "[Session Memory]" in envelope.memory_context
    assert "latest decision" in envelope.memory_context
    assert envelope.memory_injected is True
