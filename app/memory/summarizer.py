"""Memory summarization module for semantic compression of message history."""
from typing import Any


SUMMARY_PREFIX = "[Previous conversation summary]"
LEGACY_SUMMARY_PREFIXES = (
    SUMMARY_PREFIX,
    "[对话摘要:",
)


class MessageSummarizer:
    def __init__(
        self,
        target_messages: int = 10,
        preserve_system: bool = True,
        max_summary_chars: int = 900,
    ):
        self.target_messages = target_messages
        self.preserve_system = preserve_system
        self.max_summary_chars = max_summary_chars

    def summarize(self, messages: list[dict[str, Any]], llm_client: Any = None) -> list[dict[str, Any]]:
        if not isinstance(messages, list) or len(messages) <= self.target_messages:
            return messages

        leading_system, non_system = self._split_leading_system(messages)
        available_slots = self.target_messages - len(leading_system)
        if len(non_system) <= available_slots:
            return messages
        if available_slots <= 1:
            return [*leading_system, *non_system[-1:]]

        preserved_count = max(available_slots - 1, 0)
        recent = non_system[-preserved_count:] if preserved_count else []
        old_messages = non_system[:-preserved_count] if preserved_count else non_system
        summary = self._create_summary(old_messages)

        result = list(leading_system)
        if summary:
            result.append({
                "role": "system",
                "content": f"{SUMMARY_PREFIX}\n{summary}",
            })
        result.extend(recent)
        return result

    def _create_summary(self, old_messages: list[dict[str, Any]]) -> str:
        if not old_messages:
            return ""

        previous_summaries = [
            self._strip_summary_marker(message.get("content", ""))
            for message in old_messages
            if self._is_summary_message(message)
        ]
        user_messages = [
            self._clean_content(message.get("content", ""))
            for message in old_messages
            if message.get("role") == "user"
        ]
        assistant_messages = [
            self._clean_content(message.get("content", ""))
            for message in old_messages
            if message.get("role") == "assistant"
        ]

        lines = [
            (
                f"- Compressed {len(user_messages)} user messages and "
                f"{len(assistant_messages)} assistant messages."
            )
        ]
        if previous_summaries:
            lines.append(
                "- Existing summary: "
                + self._clip(" ".join(previous_summaries), 240)
            )
        if user_messages:
            lines.append(
                "- User topics: "
                + self._join_recent(user_messages, limit=3, max_chars=320)
            )
        if assistant_messages:
            lines.append(
                "- Assistant covered: "
                + self._join_recent(assistant_messages, limit=3, max_chars=320)
            )

        return self._clip("\n".join(lines), self.max_summary_chars)

    def summarize_exchange(
        self,
        *,
        user_message: str,
        assistant_message: str,
    ) -> str:
        return (
            "- User intent: "
            + self._clip(self._clean_content(user_message), 300)
            + "\n- Assistant response: "
            + self._clip(self._clean_content(assistant_message), 500)
        )

    def _split_leading_system(
        self,
        messages: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        if not self.preserve_system:
            return [], messages
        leading: list[dict[str, Any]] = []
        for index, message in enumerate(messages):
            if message.get("role") != "system" or self._is_summary_message(message):
                return leading, messages[index:]
            leading.append(message)
        return leading, []

    def _is_summary_message(self, message: dict[str, Any]) -> bool:
        if message.get("role") != "system":
            return False
        content = message.get("content", "")
        return any(content.startswith(prefix) for prefix in LEGACY_SUMMARY_PREFIXES)

    def _strip_summary_marker(self, content: str) -> str:
        stripped = content.strip()
        for prefix in LEGACY_SUMMARY_PREFIXES:
            if stripped.startswith(prefix):
                stripped = stripped[len(prefix):].strip()
                return stripped.strip("[]: \n")
        return stripped

    def _join_recent(
        self,
        values: list[str],
        *,
        limit: int,
        max_chars: int,
    ) -> str:
        return self._clip(" | ".join(value for value in values[-limit:] if value), max_chars)

    def _clean_content(self, content: str) -> str:
        return " ".join(str(content).split())

    def _clip(self, content: str, max_chars: int) -> str:
        if len(content) <= max_chars:
            return content
        return content[: max_chars - 3].rstrip() + "..."

    def compress_with_llm(
        self,
        messages: list[dict[str, Any]],
        llm_client: Any,
        model: str = "gpt-4o-mini",
    ) -> list[dict[str, Any]]:
        if not llm_client or len(messages) <= self.target_messages:
            return messages

        leading_system, non_system = self._split_leading_system(messages)
        available_slots = self.target_messages - len(leading_system)
        if len(non_system) <= available_slots:
            return messages
        if available_slots <= 1:
            return [*leading_system, *non_system[-1:]]

        preserved_count = max(available_slots - 1, 0)
        recent = non_system[-preserved_count:] if preserved_count else []
        old_messages = non_system[:-preserved_count] if preserved_count else non_system

        conversation = "\n".join(
            f"{m.get('role', 'unknown')}: {m.get('content', '')}"
            for m in old_messages
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
            summary_text = response.output_text or self._create_summary(old_messages)
        except Exception:
            summary_text = self._create_summary(old_messages)

        result = list(leading_system)
        result.append({
            "role": "system",
            "content": f"{SUMMARY_PREFIX}\n{summary_text}",
        })
        result.extend(recent)
        return result
