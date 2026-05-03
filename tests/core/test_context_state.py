import pytest

from app.core.context_state import (
    ContextStateNotFoundError,
    InMemoryContextStore,
)


def test_create_chat_context_state_defaults_to_manual_provider_state():
    store = InMemoryContextStore()

    state = store.create(channel="chat", session_id="session-1")

    assert state.session_id == "session-1"
    assert state.channel == "chat"
    assert state.provider == "openai_compatible"
    assert state.provider_mode == "manual"
    assert state.history_version == 0
    assert state.openai_conversation_id is None
    assert state.last_response_id is None


def test_external_context_maps_to_namespaced_internal_session_id():
    store = InMemoryContextStore()

    state = store.get_or_create_for_external_context(
        channel="a2a",
        external_context_id="ctx-1",
    )
    same_state = store.get_or_create_for_external_context(
        channel="a2a",
        external_context_id="ctx-1",
    )

    assert state.session_id == "a2a:ctx-1"
    assert state.external_context_id == "ctx-1"
    assert same_state.session_id == state.session_id


def test_external_context_index_is_scoped_by_channel():
    store = InMemoryContextStore()

    chat_state = store.get_or_create_for_external_context(
        channel="chat",
        external_context_id="shared",
    )
    a2a_state = store.get_or_create_for_external_context(
        channel="a2a",
        external_context_id="shared",
    )

    assert chat_state.session_id == "chat:shared"
    assert a2a_state.session_id == "a2a:shared"


def test_store_returns_copies():
    store = InMemoryContextStore()
    store.create(
        channel="chat",
        session_id="session-1",
        metadata={"source": "test"},
    )

    state = store.require("session-1")
    state.metadata["source"] = "mutated"

    stored_state = store.require("session-1")
    assert stored_state.metadata == {"source": "test"}


def test_bump_history_version_and_update_provider_state():
    store = InMemoryContextStore()
    store.create(channel="chat", session_id="session-1")

    bumped = store.bump_history_version("session-1")
    updated = store.update_provider_state(
        "session-1",
        provider="openai",
        provider_mode="openai_previous_response",
        last_response_id="resp_123",
    )

    assert bumped.history_version == 1
    assert updated.history_version == 1
    assert updated.provider == "openai"
    assert updated.provider_mode == "openai_previous_response"
    assert updated.last_response_id == "resp_123"


def test_require_raises_for_missing_state():
    store = InMemoryContextStore()

    with pytest.raises(ContextStateNotFoundError):
        store.require("missing")
