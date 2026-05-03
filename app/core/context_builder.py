"""Build the normalized context envelope for one agent turn."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from app.core.context_state import ContextChannel, ContextState, ProviderMode
from app.obj.types import ChatMessage


MEMORY_CONTEXT_PREFIX = "[Memory]\n"
BudgetStatus = Literal["not_applied", "estimated", "exact"]


class MemoryContextProvider(Protocol):
    def build_context(self, session_id: str | None = None) -> str:
        pass


@dataclass(frozen=True)
class ProviderContextState:
    provider: str
    provider_mode: ProviderMode
    openai_conversation_id: str | None = None
    last_response_id: str | None = None


@dataclass(frozen=True)
class ContextBudget:
    status: BudgetStatus = "not_applied"
    max_input_tokens: int | None = None
    input_tokens: int | None = None
    reason: str = "token_budget_not_configured"


@dataclass(frozen=True)
class ContextEnvelope:
    session_id: str
    channel: ContextChannel
    history_version: int
    messages: list[ChatMessage]
    clean_history: list[ChatMessage]
    provider_state: ProviderContextState
    external_context_id: str | None = None
    memory_context: str = ""
    memory_injected: bool = False
    summary_messages: list[ChatMessage] = field(default_factory=list)
    tool_outputs: list[dict[str, Any]] = field(default_factory=list)
    checkpoint_input: list[dict[str, Any]] | str | None = None
    budget: ContextBudget = field(default_factory=ContextBudget)
    metadata: dict[str, Any] = field(default_factory=dict)


class ContextBuilder:
    def __init__(
        self,
        *,
        memory_store: MemoryContextProvider | None = None,
        memory_prefix: str = MEMORY_CONTEXT_PREFIX,
    ) -> None:
        self.memory_store = memory_store
        self.memory_prefix = memory_prefix

    def build(
        self,
        *,
        context_state: ContextState,
        history: list[ChatMessage],
        summary_messages: list[ChatMessage] | None = None,
        tool_outputs: list[dict[str, Any]] | None = None,
        checkpoint_input: list[dict[str, Any]] | str | None = None,
    ) -> ContextEnvelope:
        clean_history = self.strip_transient_context(history)
        memory_context = self._build_memory_context(context_state.session_id)
        messages = self._inject_memory_context(clean_history, memory_context)

        return ContextEnvelope(
            session_id=context_state.session_id,
            channel=context_state.channel,
            external_context_id=context_state.external_context_id,
            history_version=context_state.history_version,
            messages=messages,
            clean_history=clean_history,
            memory_context=memory_context,
            memory_injected=bool(memory_context),
            provider_state=ProviderContextState(
                provider=context_state.provider,
                provider_mode=context_state.provider_mode,
                openai_conversation_id=context_state.openai_conversation_id,
                last_response_id=context_state.last_response_id,
            ),
            summary_messages=deepcopy(summary_messages or []),
            tool_outputs=deepcopy(tool_outputs or []),
            checkpoint_input=deepcopy(checkpoint_input),
            metadata=deepcopy(context_state.metadata),
        )

    def strip_transient_context(
        self,
        history: list[ChatMessage],
    ) -> list[ChatMessage]:
        return [
            deepcopy(message)
            for message in history
            if not self._is_transient_memory_message(message)
        ]

    def _is_transient_memory_message(self, message: ChatMessage) -> bool:
        return (
            message.get("role") == "system"
            and message.get("content", "").startswith(self.memory_prefix)
        )

    def _build_memory_context(self, session_id: str) -> str:
        if self.memory_store is None:
            return ""
        return self.memory_store.build_context(session_id=session_id)

    def _inject_memory_context(
        self,
        history: list[ChatMessage],
        memory_context: str,
    ) -> list[ChatMessage]:
        clean_history = deepcopy(history)
        if not memory_context:
            return clean_history

        memory_message: ChatMessage = {
            "role": "system",
            "content": f"{self.memory_prefix}{memory_context}",
        }
        if clean_history and clean_history[0].get("role") == "system":
            return [clean_history[0], memory_message, *clean_history[1:]]
        return [memory_message, *clean_history]
