"""ContextPipeline: staged, pluggable context processing for LLM conversations."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.obj.types import ChatMessage


# ── Protocols & result types ──────────────────────────────────────────────


class ContextProcessor(Protocol):
    """A single stage in the context pipeline."""

    def process(
        self,
        messages: list[ChatMessage],
        metadata: dict[str, Any],
    ) -> ProcessResult:
        ...


@dataclass(frozen=True)
class ProcessResult:
    messages: list[ChatMessage]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PipelineResult:
    messages: list[ChatMessage]
    metadata: dict[str, Any] = field(default_factory=dict)
    stages_executed: list[str] = field(default_factory=list)


# ── Pipeline orchestrator ──────────────────────────────────────────────────


class ContextPipeline:
    """Runs a sequence of ContextProcessors, accumulating metadata."""

    def __init__(self, processors: list[ContextProcessor] | None = None) -> None:
        self._processors = processors or []

    def run(self, messages: list[ChatMessage]) -> PipelineResult:
        current = deepcopy(messages)
        accumulated_metadata: dict[str, Any] = {}
        stages: list[str] = []

        for processor in self._processors:
            result = processor.process(current, accumulated_metadata)
            current = result.messages
            accumulated_metadata.update(result.metadata)
            stages.append(type(processor).__name__)

        return PipelineResult(
            messages=current,
            metadata=accumulated_metadata,
            stages_executed=stages,
        )

    @property
    def processor_count(self) -> int:
        return len(self._processors)


# ── 1. DeduplicationProcessor ─────────────────────────────────────────────


class DeduplicationProcessor:
    """Remove consecutive duplicate messages.

    Two messages are considered duplicates when they share the same *role*
    and identical *content*.  Only the first occurrence is kept; a dedup
    count is recorded in metadata.
    """

    def process(
        self,
        messages: list[ChatMessage],
        metadata: dict[str, Any],
    ) -> ProcessResult:
        if not messages:
            return ProcessResult(messages=[], metadata={"dedup_count": 0})

        kept: list[ChatMessage] = [messages[0]]
        dedup_count = 0

        for message in messages[1:]:
            prev = kept[-1]
            if (
                message.get("role") == prev.get("role")
                and message.get("content") == prev.get("content")
            ):
                dedup_count += 1
            else:
                kept.append(message)

        return ProcessResult(
            messages=kept,
            metadata={"dedup_count": dedup_count},
        )


# ── 2. ImportanceScorer ────────────────────────────────────────────────────


@dataclass(frozen=True)
class ImportanceScore:
    score: int
    reason: str  # e.g. "system_prompt", "recent_exchange", "older_tool"


class ImportanceScorer:
    """Assign a 0-100 importance score to every message.

    Scoring rules are driven by the context config so they can be tuned per
    deployment without code changes.
    """

    SUMMARY_PREFIXES = ("[Previous conversation summary]", "[对话摘要:")

    def __init__(
        self,
        *,
        score_system_prompt: int = 100,
        score_recent_exchange: int = 90,
        score_recent_tool_output: int = 85,
        score_summary: int = 70,
        score_older_exchange: int = 60,
        score_older_tool_output: int = 50,
        score_transient_memory: int = 30,
        recent_window: int = 3,
        decay_per_turn: int = 5,
        decay_per_tool: int = 8,
        memory_prefix: str = "[Memory]\n",
    ) -> None:
        self.score_system_prompt = score_system_prompt
        self.score_recent_exchange = score_recent_exchange
        self.score_recent_tool_output = score_recent_tool_output
        self.score_summary = score_summary
        self.score_older_exchange = score_older_exchange
        self.score_older_tool_output = score_older_tool_output
        self.score_transient_memory = score_transient_memory
        self.recent_window = recent_window
        self.decay_per_turn = decay_per_turn
        self.decay_per_tool = decay_per_tool
        self.memory_prefix = memory_prefix

    def process(
        self,
        messages: list[ChatMessage],
        metadata: dict[str, Any],
    ) -> ProcessResult:
        if not messages:
            return ProcessResult(messages=[], metadata={"importance_scores": []})

        n = len(messages)
        scores: list[ImportanceScore] = []
        turn_index = 0
        tool_index = 0

        for i, message in enumerate(messages):
            distance_from_end = n - 1 - i

            if message.get("role") == "tool":
                tool_index += 1

            score = self._compute_score(
                message=message,
                index=i,
                distance_from_end=distance_from_end,
                total_messages=n,
                tool_count_from_end=self._count_tools_from_end(messages, i),
                turn_distance=self._turn_distance(messages, i),
            )
            scores.append(score)

        return ProcessResult(
            messages=deepcopy(messages),
            metadata={"importance_scores": scores},
        )

    def _compute_score(
        self,
        *,
        message: ChatMessage,
        index: int,
        distance_from_end: int,
        total_messages: int,
        tool_count_from_end: int,
        turn_distance: int,
    ) -> ImportanceScore:
        # First system message
        if index == 0 and message.get("role") == "system":
            if self._is_transient_memory(message):
                return ImportanceScore(self.score_transient_memory, "transient_memory")
            return ImportanceScore(self.score_system_prompt, "system_prompt")

        # Summary messages
        if self._is_summary(message):
            return ImportanceScore(
                max(0, self.score_summary - turn_distance * self.decay_per_turn),
                "summary",
            )

        # Transient memory messages (not first)
        if self._is_transient_memory(message):
            return ImportanceScore(self.score_transient_memory, "transient_memory")

        # Tool messages
        if message.get("role") == "tool":
            is_recent = tool_count_from_end < self.recent_window
            if is_recent:
                return ImportanceScore(self.score_recent_tool_output, "recent_tool_output")
            base = self.score_older_tool_output
            decay = max(0, (tool_count_from_end - self.recent_window + 1)) * self.decay_per_tool
            return ImportanceScore(max(0, base - decay), "older_tool_output")

        # User / assistant messages
        is_recent = distance_from_end < self.recent_window * 2
        if is_recent:
            return ImportanceScore(self.score_recent_exchange, "recent_exchange")

        base = self.score_older_exchange
        decay = max(0, (distance_from_end - self.recent_window * 2 + 1)) * self.decay_per_turn
        return ImportanceScore(max(0, base - decay), "older_exchange")

    def _is_transient_memory(self, message: ChatMessage) -> bool:
        return (
            message.get("role") == "system"
            and message.get("content", "").startswith(self.memory_prefix)
        )

    def _is_summary(self, message: ChatMessage) -> bool:
        if message.get("role") != "system":
            return False
        content = message.get("content", "")
        return any(content.startswith(p) for p in self.SUMMARY_PREFIXES)

    def _count_tools_from_end(self, messages: list[ChatMessage], index: int) -> int:
        count = 0
        for i in range(len(messages) - 1, index, -1):
            if messages[i].get("role") == "tool":
                count += 1
        return count

    def _turn_distance(self, messages: list[ChatMessage], index: int) -> int:
        turns = 0
        for i in range(len(messages) - 1, index, -1):
            if messages[i].get("role") in ("user", "assistant"):
                turns += 1
        return turns // 2


# ── 3. HierarchicalSummarizer ──────────────────────────────────────────────


class HierarchicalSummarizer:
    """Compress old messages into a multi-level summary pyramid.

    Level 1 — TurnSummary:  compresses TURNS_PER_GROUP user+assistant pairs.
    Level 2 — SegmentSummary: groups TurnSummaries.
    Level 3 — SessionSummary:  the running session-level synopsis.

    Summaries are injected as system messages at the boundary between old
    and recent content.
    """

    SUMMARY_PREFIX = "[Previous conversation summary]"

    def __init__(
        self,
        *,
        max_level: int = 3,
        turns_per_group: int = 5,
        target_messages: int = 20,
        max_summary_chars: int = 900,
        preserve_system: bool = True,
        llm_client: Any = None,
        llm_model: str = "gpt-4o-mini",
    ) -> None:
        self.max_level = max_level
        self.turns_per_group = turns_per_group
        self.target_messages = target_messages
        self.max_summary_chars = max_summary_chars
        self.preserve_system = preserve_system
        self.llm_client = llm_client
        self.llm_model = llm_model

    def process(
        self,
        messages: list[ChatMessage],
        metadata: dict[str, Any],
    ) -> ProcessResult:
        if len(messages) <= self.target_messages:
            return ProcessResult(messages=deepcopy(messages), metadata={"summary_generated": False})

        leading_system, conversation = self._split_leading_system(messages)
        if len(conversation) <= self.target_messages - len(leading_system):
            return ProcessResult(messages=deepcopy(messages), metadata={"summary_generated": False})

        preserved_count = max(self.target_messages - len(leading_system) - 1, 1)
        recent = conversation[-preserved_count:]
        old = conversation[:-preserved_count]

        summary = self._build_summary_pyramid(old)
        if not summary:
            return ProcessResult(messages=deepcopy(messages), metadata={"summary_generated": False})

        result = list(leading_system)
        result.append({"role": "system", "content": f"{self.SUMMARY_PREFIX}\n{summary}"})
        result.extend(recent)

        return ProcessResult(
            messages=result,
            metadata={
                "summary_generated": True,
                "summary_levels_used": self._detected_level(old),
                "messages_summarized": len(old),
            },
        )

    def _build_summary_pyramid(self, old_messages: list[ChatMessage]) -> str:
        if not old_messages:
            return ""

        turns = self._group_into_turns(old_messages)
        if not turns:
            return self._create_raw_summary(old_messages)

        turn_summaries = self._summarize_turns(turns)
        if self.max_level <= 1 or len(turn_summaries) <= 1:
            return self._render_level(turn_summaries, "Turn")

        segment_summaries = self._summarize_groups(
            turn_summaries,
            group_size=3,
        )
        if self.max_level <= 2 or len(segment_summaries) <= 1:
            return self._render_level(segment_summaries, "Segment")

        session_summary = self._render_session_summary(segment_summaries)
        return session_summary

    def _group_into_turns(
        self,
        messages: list[ChatMessage],
    ) -> list[list[ChatMessage]]:
        """Group messages into user+assistant turn pairs."""
        turns: list[list[ChatMessage]] = []
        current_turn: list[ChatMessage] = []

        for message in messages:
            role = message.get("role", "")
            if role == "tool":
                if current_turn:
                    current_turn.append(message)
                continue

            if role == "user" and current_turn:
                turns.append(current_turn)
                current_turn = [message]
            else:
                current_turn.append(message)

        if current_turn:
            turns.append(current_turn)
        return turns

    def _summarize_turns(self, turns: list[list[ChatMessage]]) -> list[str]:
        summaries: list[str] = []
        for i in range(0, len(turns), self.turns_per_group):
            group = turns[i : i + self.turns_per_group]
            summaries.append(self._summarize_turn_group(group, i // self.turns_per_group + 1))
        return summaries

    def _summarize_turn_group(self, turns: list[list[ChatMessage]], group_num: int) -> str:
        user_msgs: list[str] = []
        assistant_msgs: list[str] = []
        tool_count = 0

        for turn in turns:
            for msg in turn:
                role = msg.get("role", "")
                content = self._clean_content(msg.get("content", ""))
                if role == "user" and content:
                    user_msgs.append(content)
                elif role == "assistant" and content:
                    assistant_msgs.append(content)
                elif role == "tool":
                    tool_count += 1

        lines = [f"[Turn group {group_num}]"]
        if user_msgs:
            lines.append(f"- User asked about: {self._clip(' | '.join(user_msgs[-3:]), 300)}")
        if assistant_msgs:
            lines.append(f"- Assistant covered: {self._clip(' | '.join(assistant_msgs[-3:]), 300)}")
        if tool_count:
            lines.append(f"- Used {tool_count} tool(s)")
        return "\n".join(lines)

    def _summarize_groups(self, summaries: list[str], group_size: int) -> list[str]:
        grouped: list[str] = []
        for i in range(0, len(summaries), group_size):
            chunk = summaries[i : i + group_size]
            grouped.append(
                f"[Segment {i // group_size + 1}]\n"
                + "\n".join(f"  {line}" for line in chunk)
            )
        return grouped

    def _render_level(self, items: list[str], label: str) -> str:
        return self._clip(f"[{label} Summaries]\n" + "\n".join(items), self.max_summary_chars)

    def _render_session_summary(self, segments: list[str]) -> str:
        combined = "\n".join(segments)

        if self.llm_client is not None:
            llm_summary = self._llm_summarize(combined)
            if llm_summary:
                return self._clip(
                    f"[Session Summary]\n{llm_summary}",
                    self.max_summary_chars,
                )

        key_points = self._extract_key_points(combined)
        return self._clip(
            f"[Session Summary]\nKey conversation topics and decisions:\n{key_points}",
            self.max_summary_chars,
        )

    def _llm_summarize(self, text: str) -> str | None:
        """Use LLM to generate a concise abstractive summary."""
        from app.configs.logger import logger

        prompt = (
            "Summarize the following conversation segments into a concise paragraph "
            "(max 150 words) covering the main topics, key decisions, and important "
            "context for continuing the conversation:\n\n"
            f"{text[:3000]}\n\n"
            "Summary:"
        )
        try:
            response = self.llm_client.chat.completions.create(
                model=self.llm_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=200,
            )
            return response.choices[0].message.content or None
        except Exception:
            logger.warning("hierarchical_summarizer event=llm_failed", exc_info=True)
            return None

    def _extract_key_points(self, text: str) -> str:
        lines = text.splitlines()
        key_lines = [
            line.strip()
            for line in lines
            if line.strip()
            and any(
                keyword in line.lower()
                for keyword in ("user asked", "assistant", "used", "tool", "key", "decision")
            )
        ]
        if not key_lines:
            return text[: self.max_summary_chars // 2]
        return self._clip("\n".join(key_lines[-10:]), self.max_summary_chars // 2)

    def _create_raw_summary(self, messages: list[ChatMessage]) -> str:
        user_msgs = [
            self._clean_content(m.get("content", ""))
            for m in messages
            if m.get("role") == "user"
        ]
        assistant_msgs = [
            self._clean_content(m.get("content", ""))
            for m in messages
            if m.get("role") == "assistant"
        ]
        return self._clip(
            f"Compressed {len(user_msgs)} user messages and {len(assistant_msgs)} assistant messages.\n"
            f"- User topics: {' | '.join(user_msgs[-3:]) if user_msgs else 'none'}",
            self.max_summary_chars,
        )

    def _detected_level(self, old_messages: list[ChatMessage]) -> int:
        turns = len(self._group_into_turns(old_messages))
        if turns <= self.turns_per_group:
            return 1
        if turns <= self.turns_per_group * 3:
            return 2
        return 3

    def _split_leading_system(
        self,
        messages: list[ChatMessage],
    ) -> tuple[list[ChatMessage], list[ChatMessage]]:
        if not self.preserve_system:
            return [], list(messages)

        leading: list[ChatMessage] = []
        for i, message in enumerate(messages):
            if message.get("role") != "system":
                return leading, messages[i:]
            if self._is_summary_message(message):
                return leading, messages[i:]
            leading.append(message)
        return leading, []

    def _is_summary_message(self, message: ChatMessage) -> bool:
        if message.get("role") != "system":
            return False
        content = message.get("content", "")
        return content.startswith(self.SUMMARY_PREFIX)

    def _clean_content(self, content: str) -> str:
        return " ".join(str(content).split())

    def _clip(self, text: str, max_chars: int) -> str:
        if len(text) <= max_chars:
            return text
        return text[: max_chars - 3].rstrip() + "..."


# ── 4. DynamicBudgetAllocator ──────────────────────────────────────────────


@dataclass(frozen=True)
class BudgetAllocation:
    total: int
    reserved: int  # system prompt + memory (untouchable)
    for_tools: int
    for_summaries: int
    for_conversation: int
    conversation_type: str  # "tool_heavy", "long", "short", "balanced"


class DynamicBudgetAllocator:
    """Dynamically split the token budget based on conversation characteristics."""

    def __init__(
        self,
        *,
        max_input_tokens: int | None = None,
        tool_heavy_ratio: tuple[float, float, float] = (0.35, 0.25, 0.40),
        long_conversation_ratio: tuple[float, float, float] = (0.20, 0.40, 0.40),
        short_conversation_ratio: tuple[float, float, float] = (0.15, 0.10, 0.75),
        balanced_ratio: tuple[float, float, float] = (0.20, 0.30, 0.50),
        tool_heavy_threshold: float = 0.30,
        long_conversation_threshold: int = 20,
        short_conversation_threshold: int = 10,
    ) -> None:
        self.max_input_tokens = max_input_tokens
        self.tool_heavy_ratio = tool_heavy_ratio
        self.long_conversation_ratio = long_conversation_ratio
        self.short_conversation_ratio = short_conversation_ratio
        self.balanced_ratio = balanced_ratio
        self.tool_heavy_threshold = tool_heavy_threshold
        self.long_conversation_threshold = long_conversation_threshold
        self.short_conversation_threshold = short_conversation_threshold

    def process(
        self,
        messages: list[ChatMessage],
        metadata: dict[str, Any],
    ) -> ProcessResult:
        if not self.max_input_tokens or self.max_input_tokens <= 0:
            return ProcessResult(
                messages=deepcopy(messages),
                metadata={"budget_allocation": None, "budget_disabled": True},
            )

        reserved = self._estimate_reserved(messages)
        remaining = max(0, self.max_input_tokens - reserved)
        conv_type, ratios = self._classify(messages)

        allocation = BudgetAllocation(
            total=self.max_input_tokens,
            reserved=reserved,
            for_tools=int(remaining * ratios[0]),
            for_summaries=int(remaining * ratios[1]),
            for_conversation=int(remaining * ratios[2]),
            conversation_type=conv_type,
        )

        return ProcessResult(
            messages=deepcopy(messages),
            metadata={"budget_allocation": allocation},
        )

    def _estimate_reserved(self, messages: list[ChatMessage]) -> int:
        from app.core.token_budget import EstimatedTokenCounter

        counter = EstimatedTokenCounter()
        reserved = 0
        for message in messages:
            if message.get("role") == "system" and not self._is_summary_like(message):
                reserved += counter.count_message(message)
        return reserved

    def _classify(self, messages: list[ChatMessage]) -> tuple[str, tuple[float, float, float]]:
        total = len(messages)
        tool_count = sum(1 for m in messages if m.get("role") == "tool")
        tool_ratio = tool_count / max(total, 1)

        if tool_ratio > self.tool_heavy_threshold:
            return "tool_heavy", self.tool_heavy_ratio
        if total > self.long_conversation_threshold:
            return "long", self.long_conversation_ratio
        if total <= self.short_conversation_threshold:
            return "short", self.short_conversation_ratio
        return "balanced", self.balanced_ratio

    @staticmethod
    def _is_summary_like(message: ChatMessage) -> bool:
        if message.get("role") != "system":
            return False
        content = message.get("content", "")
        return any(
            content.startswith(p)
            for p in ("[Previous conversation summary]", "[Memory]\n", "[对话摘要:")
        )


# ── 5. IntelligentTrimmer ──────────────────────────────────────────────────


@dataclass(frozen=True)
class TrimResult:
    messages: list[ChatMessage]
    dropped_count: int
    summarized_count: int
    reason: str  # "within_budget", "trimmed", "minimum_exceeds_budget"


class IntelligentTrimmer:
    """Trim messages to fit a token budget using importance scores.

    Guarantees that mandatory messages are always kept:
    - First system prompt
    - Last user message + assistant reply
    - Last tool call + output pair
    """

    def __init__(
        self,
        *,
        max_input_tokens: int | None = None,
        budget_allocation: BudgetAllocation | None = None,
    ) -> None:
        self.max_input_tokens = max_input_tokens
        self.budget_allocation = budget_allocation

    def process(
        self,
        messages: list[ChatMessage],
        metadata: dict[str, Any],
    ) -> ProcessResult:
        from app.core.token_budget import EstimatedTokenCounter

        counter = EstimatedTokenCounter()

        if not self.max_input_tokens or self.max_input_tokens <= 0:
            return ProcessResult(
                messages=deepcopy(messages),
                metadata={"trim_result": TrimResult(
                    messages=messages, dropped_count=0, summarized_count=0,
                    reason="within_budget",
                )},
            )

        total_tokens = counter.count_messages(messages)
        if total_tokens <= self.max_input_tokens:
            return ProcessResult(
                messages=deepcopy(messages),
                metadata={"trim_result": TrimResult(
                    messages=messages, dropped_count=0, summarized_count=0,
                    reason="within_budget",
                )},
            )

        importance_scores: list[ImportanceScore] | None = metadata.get("importance_scores")
        allocation: BudgetAllocation | None = metadata.get("budget_allocation") or self.budget_allocation

        trimmed, dropped, summarized = self._trim(
            messages,
            counter,
            importance_scores,
            allocation,
        )
        reason = "trimmed"
        if counter.count_messages(trimmed) > self.max_input_tokens:
            reason = "minimum_exceeds_budget"

        return ProcessResult(
            messages=trimmed,
            metadata={"trim_result": TrimResult(
                messages=trimmed,
                dropped_count=dropped,
                summarized_count=summarized,
                reason=reason,
            )},
        )

    def _trim(
        self,
        messages: list[ChatMessage],
        counter: Any,
        importance_scores: list[ImportanceScore] | None,
        allocation: BudgetAllocation | None,
    ) -> tuple[list[ChatMessage], int, int]:
        n = len(messages)
        mandatory_indices: set[int] = self._find_mandatory(messages)

        if importance_scores is None:
            importance_scores = [ImportanceScore(50, "default") for _ in messages]

        scored: list[tuple[int, ChatMessage, ImportanceScore]] = [
            (i, messages[i], importance_scores[i]) for i in range(n)
        ]

        # Start with mandatory messages; if they already exceed budget,
        # keep only the highest-priority subset of mandatory messages.
        kept_indices: set[int] = set()
        token_used = 0
        mandatory_ordered = sorted(
            mandatory_indices,
            key=lambda i: importance_scores[i].score,
            reverse=True,
        )
        for idx in mandatory_ordered:
            msg_tokens = counter.count_message(messages[idx])
            if token_used + msg_tokens <= self.max_input_tokens:
                kept_indices.add(idx)
                token_used += msg_tokens

        # Fill remaining budget with highest-scored non-mandatory messages
        scored.sort(key=lambda item: item[2].score, reverse=True)
        for idx, msg, score in scored:
            if idx in kept_indices:
                continue
            msg_tokens = counter.count_message(msg)
            if token_used + msg_tokens <= self.max_input_tokens:
                kept_indices.add(idx)
                token_used += msg_tokens

        dropped = n - len(kept_indices)
        summarized = 0

        result = [msg for i, msg in enumerate(messages) if i in kept_indices]
        return result, dropped, summarized

    def _find_mandatory(self, messages: list[ChatMessage]) -> set[int]:
        mandatory: set[int] = set()
        n = len(messages)

        # First system message
        if messages and messages[0].get("role") == "system":
            mandatory.add(0)

        # Last user message
        for i in range(n - 1, -1, -1):
            if messages[i].get("role") == "user":
                mandatory.add(i)
                break

        # Last assistant message
        for i in range(n - 1, -1, -1):
            if messages[i].get("role") == "assistant":
                mandatory.add(i)
                break

        # Last tool output
        for i in range(n - 1, -1, -1):
            if messages[i].get("role") == "tool":
                mandatory.add(i)
                break

        return mandatory
