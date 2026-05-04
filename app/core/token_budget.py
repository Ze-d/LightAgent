"""Token budget estimation and chat history trimming."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from math import ceil
from typing import Any, Literal

from app.obj.types import ChatMessage


BudgetStatus = Literal["not_applied", "estimated", "exact"]
TextKeepMode = Literal["start", "end"]


@dataclass(frozen=True)
class TokenBudgetResult:
    messages: list[ChatMessage]
    status: BudgetStatus
    max_input_tokens: int | None
    input_tokens: int | None
    reason: str
    dropped_messages: int = 0


class EstimatedTokenCounter:
    """Deterministic local token estimator.

    This intentionally avoids a tokenizer dependency. It counts CJK characters
    closer to one token each and non-CJK text at roughly four chars per token.
    """

    def count_messages(self, messages: list[dict[str, Any]]) -> int:
        return 2 + sum(self.count_message(message) for message in messages)

    def count_message(self, message: dict[str, Any]) -> int:
        role = str(message.get("role", ""))
        content = str(message.get("content", ""))
        return 4 + self.count_text(role) + self.count_text(content)

    def count_text(self, text: str) -> int:
        if not text:
            return 0

        cjk_chars = 0
        non_cjk_chars = 0
        for char in text:
            if self._is_cjk(char):
                cjk_chars += 1
            elif not char.isspace():
                non_cjk_chars += 1
        return cjk_chars + ceil(non_cjk_chars / 4)

    def _is_cjk(self, char: str) -> bool:
        codepoint = ord(char)
        return (
            0x4E00 <= codepoint <= 0x9FFF
            or 0x3400 <= codepoint <= 0x4DBF
            or 0x3040 <= codepoint <= 0x30FF
            or 0xAC00 <= codepoint <= 0xD7AF
        )


def trim_text_to_token_budget(
    text: str,
    max_tokens: int | None,
    *,
    keep: TextKeepMode = "start",
    counter: EstimatedTokenCounter | None = None,
    marker: str = "[truncated]\n",
) -> str:
    if max_tokens is None or max_tokens <= 0:
        return text

    resolved_counter = counter or EstimatedTokenCounter()
    if resolved_counter.count_text(text) <= max_tokens:
        return text

    marker_tokens = resolved_counter.count_text(marker)
    if max_tokens <= marker_tokens:
        return marker.strip()

    budget_for_text = max_tokens - marker_tokens
    low = 0
    high = len(text)
    best = ""
    while low <= high:
        mid = (low + high) // 2
        candidate = text[:mid] if keep == "start" else text[-mid:]
        if resolved_counter.count_text(candidate) <= budget_for_text:
            best = candidate
            low = mid + 1
        else:
            high = mid - 1

    best = best.strip()
    if keep == "start":
        return f"{best}\n{marker.strip()}".strip()
    return f"{marker.strip()}\n{best}".strip()


class TokenBudgetTrimmer:
    def __init__(
        self,
        *,
        max_input_tokens: int | None = None,
        counter: EstimatedTokenCounter | None = None,
    ) -> None:
        self.max_input_tokens = max_input_tokens
        self.counter = counter or EstimatedTokenCounter()

    def apply(self, messages: list[ChatMessage]) -> TokenBudgetResult:
        copied_messages = deepcopy(messages)
        if self.max_input_tokens is None or self.max_input_tokens <= 0:
            return TokenBudgetResult(
                messages=copied_messages,
                status="not_applied",
                max_input_tokens=self.max_input_tokens,
                input_tokens=None,
                reason="token_budget_not_configured",
            )

        input_tokens = self.counter.count_messages(copied_messages)
        if input_tokens <= self.max_input_tokens:
            return TokenBudgetResult(
                messages=copied_messages,
                status="estimated",
                max_input_tokens=self.max_input_tokens,
                input_tokens=input_tokens,
                reason="within_budget",
            )

        trimmed, dropped_messages = self._trim_chat_history(copied_messages)
        trimmed_tokens = self.counter.count_messages(trimmed)
        reason = "trimmed_history"

        if trimmed_tokens > self.max_input_tokens:
            trimmed, additional_drops = self._drop_optional_system_messages(trimmed)
            dropped_messages += additional_drops
            trimmed_tokens = self.counter.count_messages(trimmed)
            reason = "trimmed_history_and_optional_system"

        if trimmed_tokens > self.max_input_tokens:
            reason = "minimum_context_exceeds_budget"

        return TokenBudgetResult(
            messages=trimmed,
            status="estimated",
            max_input_tokens=self.max_input_tokens,
            input_tokens=trimmed_tokens,
            reason=reason,
            dropped_messages=dropped_messages,
        )

    def _trim_chat_history(
        self,
        messages: list[ChatMessage],
    ) -> tuple[list[ChatMessage], int]:
        leading_system, conversation = self._split_leading_system(messages)
        if not conversation:
            return leading_system, 0

        kept_reversed: list[ChatMessage] = []
        dropped = 0
        token_total = self._sum_message_tokens(leading_system) + 2

        for message in reversed(conversation):
            message_tokens = self.counter.count_message(message)
            is_newest_message = not kept_reversed
            if (
                token_total + message_tokens <= self.max_input_tokens
                or is_newest_message
            ):
                kept_reversed.append(message)
                token_total += message_tokens
            else:
                dropped += 1

        kept = list(reversed(kept_reversed))
        return [*leading_system, *kept], dropped

    def _drop_optional_system_messages(
        self,
        messages: list[ChatMessage],
    ) -> tuple[list[ChatMessage], int]:
        if len(messages) <= 1:
            return messages, 0

        kept = deepcopy(messages)
        dropped = 0
        index = 1
        while (
            index < len(kept)
            and kept[index].get("role") == "system"
            and self.counter.count_messages(kept) > self.max_input_tokens
        ):
            kept.pop(index)
            dropped += 1
        return kept, dropped

    def _split_leading_system(
        self,
        messages: list[ChatMessage],
    ) -> tuple[list[ChatMessage], list[ChatMessage]]:
        leading_system: list[ChatMessage] = []
        index = 0
        for index, message in enumerate(messages):
            if message.get("role") != "system":
                return leading_system, messages[index:]
            leading_system.append(message)
        return leading_system, []

    def _sum_message_tokens(self, messages: list[ChatMessage]) -> int:
        return sum(self.counter.count_message(message) for message in messages)
