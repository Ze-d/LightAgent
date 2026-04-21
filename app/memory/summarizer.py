"""Memory summarization module for semantic compression of message history."""
import json
from typing import Any


class MessageSummarizer:
    def __init__(
        self,
        target_messages: int = 10,
        preserve_system: bool = True,
    ):
        self.target_messages = target_messages
        self.preserve_system = preserve_system

    def summarize(self, messages: list[dict[str, Any]], llm_client: Any = None) -> list[dict[str, Any]]:
        if not isinstance(messages, list) or len(messages) <= self.target_messages:
            return messages

        system_msg = None
        non_system = messages
        if self.preserve_system and messages and messages[0].get("role") == "system":
            system_msg = messages[0]
            non_system = messages[1:]

        if len(non_system) <= self.target_messages - (1 if system_msg else 0):
            return messages

        preserved_count = self.target_messages - (1 if system_msg else 0)
        recent = non_system[-preserved_count:]
        summary = self._create_summary(non_system[:-preserved_count]) if len(non_system) > preserved_count else []

        result = []
        if system_msg:
            result.append(system_msg)
        if summary:
            result.append({
                "role": "system",
                "content": f"[Previous conversation summary: {summary}]"
            })
        result.extend(recent)
        return result

    def _create_summary(self, old_messages: list[dict[str, Any]]) -> str:
        if not old_messages:
            return ""

        total_length = sum(len(m.get("content", "")) for m in old_messages)
        num_turns = len([m for m in old_messages if m.get("role") == "user"])

        return f"{num_turns} user turns, ~{total_length} tokens of context"

    def compress_with_llm(
        self,
        messages: list[dict[str, Any]],
        llm_client: Any,
        model: str = "gpt-4o-mini",
    ) -> list[dict[str, Any]]:
        if not llm_client or len(messages) <= self.target_messages:
            return messages

        system_msg = None
        non_system = messages
        if self.preserve_system and messages and messages[0].get("role") == "system":
            system_msg = messages[0]
            non_system = messages[1:]

        if len(non_system) <= self.target_messages - (1 if system_msg else 0):
            return messages

        conversation = "\n".join(
            f"{m.get('role', 'unknown')}: {m.get('content', '')}"
            for m in non_system
        )

        prompt = f"""请用简洁的语言总结以下对话的主要内容和关键信息，以便后续上下文可以基于此继续。

对话内容:
{conversation}

请生成一段简洁的摘要（不超过100字），概括主要话题和关键决策。"""

        try:
            response = llm_client.responses.create(
                model=model,
                input=[{"role": "user", "content": prompt}],
            )
            summary_text = response.output_text or self._create_summary(non_system)
        except Exception:
            summary_text = self._create_summary(non_system)

        preserved_count = self.target_messages - (1 if system_msg else 0)
        recent = non_system[-preserved_count:]

        result = []
        if system_msg:
            result.append(system_msg)
        result.append({
            "role": "system",
            "content": f"[对话摘要: {summary_text}]"
        })
        result.extend(recent)
        return result
