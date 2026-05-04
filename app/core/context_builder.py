"""Build the normalized context envelope for one agent turn."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.core.context_state import ContextChannel, ContextState, ProviderMode
from app.core.token_budget import (
    BudgetStatus,
    EstimatedTokenCounter,
    TokenBudgetTrimmer,
    trim_text_to_token_budget,
)
from app.obj.types import ChatMessage


MEMORY_CONTEXT_PREFIX = "[Memory]\n"


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
    dropped_messages: int = 0


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
    memory_context_tokens: int | None = None
    memory_max_tokens: int | None = None
    memory_truncated: bool = False
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
        max_input_tokens: int | None = None,
        memory_max_tokens: int | None = None,
    ) -> None:
        self.memory_store = memory_store
        self.memory_prefix = memory_prefix
        self.max_input_tokens = max_input_tokens
        self.memory_max_tokens = memory_max_tokens
        self.token_counter = EstimatedTokenCounter()
        self.token_budget = TokenBudgetTrimmer(
            max_input_tokens=max_input_tokens,
        )

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
        memory_context, memory_truncated = self._fit_memory_context(memory_context)
        messages = self._inject_memory_context(clean_history, memory_context)
        budget_result = self.token_budget.apply(messages)
        messages = budget_result.messages

        return ContextEnvelope(
            session_id=context_state.session_id,
            channel=context_state.channel,
            external_context_id=context_state.external_context_id,
            history_version=context_state.history_version,
            messages=messages,
            clean_history=clean_history,
            memory_context=memory_context,
            memory_injected=self._contains_transient_memory_message(messages),
            memory_context_tokens=(
                self.token_counter.count_text(memory_context)
                if memory_context
                else 0
            ),
            memory_max_tokens=self.memory_max_tokens,
            memory_truncated=memory_truncated,
            provider_state=ProviderContextState(
                provider=context_state.provider,
                provider_mode=context_state.provider_mode,
                openai_conversation_id=context_state.openai_conversation_id,
                last_response_id=context_state.last_response_id,
            ),
            summary_messages=deepcopy(summary_messages or []),
            tool_outputs=deepcopy(tool_outputs or []),
            checkpoint_input=deepcopy(checkpoint_input),
            budget=ContextBudget(
                status=budget_result.status,
                max_input_tokens=budget_result.max_input_tokens,
                input_tokens=budget_result.input_tokens,
                reason=budget_result.reason,
                dropped_messages=budget_result.dropped_messages,
            ),
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

    def _contains_transient_memory_message(
        self,
        messages: list[ChatMessage],
    ) -> bool:
        return any(self._is_transient_memory_message(message) for message in messages)

    def _build_memory_context(self, session_id: str) -> str:
        if self.memory_store is None:
            return ""
        return self.memory_store.build_context(session_id=session_id)

    def _fit_memory_context(self, memory_context: str) -> tuple[str, bool]:
        if (
            not memory_context
            or self.memory_max_tokens is None
            or self.memory_max_tokens <= 0
        ):
            return memory_context, False

        if self.token_counter.count_text(memory_context) <= self.memory_max_tokens:
            return memory_context, False

        trimmed = self._trim_memory_sections(memory_context)
        return trimmed, trimmed != memory_context

    def _trim_memory_sections(self, memory_context: str) -> str:
        sections = self._split_memory_sections(memory_context)
        if not sections:
            return trim_text_to_token_budget(
                memory_context,
                self.memory_max_tokens,
                keep="end",
                counter=self.token_counter,
            )

        session_sections = [
            section for section in sections
            if section.startswith("[Session Memory]")
        ]
        stable_sections = [
            section for section in sections
            if not section.startswith("[Session Memory]")
        ]

        if not session_sections or not stable_sections:
            keep = "end" if session_sections else "start"
            return trim_text_to_token_budget(
                "\n\n".join(sections),
                self.memory_max_tokens,
                keep=keep,
                counter=self.token_counter,
            )

        stable_context = "\n\n".join(stable_sections)
        session_context = "\n\n".join(session_sections)
        separator_tokens = self.token_counter.count_text("\n\n")
        stable_budget = max(1, self.memory_max_tokens // 3)
        session_budget = max(
            1,
            self.memory_max_tokens - stable_budget - separator_tokens,
        )

        stable_trimmed = self._trim_memory_section(
            stable_context,
            stable_budget,
            keep="start",
        )
        session_trimmed = self._trim_memory_section(
            session_context,
            session_budget,
            keep="end",
        )
        return "\n\n".join(
            section for section in [stable_trimmed, session_trimmed]
            if section
        )

    def _trim_memory_section(
        self,
        section: str,
        max_tokens: int,
        *,
        keep: str,
    ) -> str:
        lines = section.splitlines()
        if (
            not lines
            or not lines[0].startswith("[")
            or not lines[0].endswith("Memory]")
        ):
            return trim_text_to_token_budget(
                section,
                max_tokens,
                keep=keep,
                counter=self.token_counter,
            )

        header = lines[0]
        body = "\n".join(lines[1:]).strip()
        header_tokens = self.token_counter.count_text(header)
        body_budget = max(1, max_tokens - header_tokens)
        body_trimmed = trim_text_to_token_budget(
            body,
            body_budget,
            keep=keep,
            counter=self.token_counter,
        )
        return f"{header}\n{body_trimmed}".strip()

    def _split_memory_sections(self, memory_context: str) -> list[str]:
        sections: list[str] = []
        current: list[str] = []
        for line in memory_context.splitlines():
            if (
                line.startswith("[")
                and line.endswith("Memory]")
                and current
            ):
                sections.append("\n".join(current).strip())
                current = [line]
            else:
                current.append(line)
        if current:
            section = "\n".join(current).strip()
            if section:
                sections.append(section)
        return sections

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
