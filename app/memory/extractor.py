"""LLM-driven knowledge extraction from session conversations."""
from __future__ import annotations

from typing import Any

from app.configs.logger import logger

_KNOWLEDGE_EXTRACTION_PROMPT = """Analyze the following conversation and extract reusable knowledge.
Output ONLY a JSON array of facts. Each fact must have these fields:
- "fact": the extracted knowledge (concise, 1-2 sentences)
- "category": one of "preference", "fact", "decision", "constraint"
- "confidence": a number between 0.0 and 1.0

- "preference": user likes, dislikes, style preferences, communication preferences
- "fact": objective information shared (project details, technical info, past events)
- "decision": choices made, agreed-upon approaches, resolved trade-offs
- "constraint": limitations, restrictions, must-not-do rules

Conversation:
{conversation}

Output:"""


class KnowledgeExtractor:
    """Extracts reusable knowledge from conversation history using an LLM."""

    def __init__(
        self,
        client: Any,
        model: str = "gpt-4o-mini",
        *,
        min_turns: int = 10,
    ) -> None:
        self._client = client
        self._model = model
        self.min_turns = min_turns

    def should_extract(self, turn_count: int) -> bool:
        return turn_count >= self.min_turns

    def extract(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Extract knowledge facts from a list of conversation messages.

        Returns a list of fact dicts with keys: fact, category, confidence.
        """
        conversation = self._format_conversation(messages)
        if not conversation.strip():
            return []

        prompt = _KNOWLEDGE_EXTRACTION_PROMPT.format(conversation=conversation)

        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
            raw = response.choices[0].message.content or ""
        except Exception:
            logger.warning("knowledge_extractor event=llm_failed", exc_info=True)
            return []

        facts = self._parse_response(raw)
        logger.info(
            "knowledge_extractor event=extracted fact_count=%d", len(facts),
        )
        return facts

    @staticmethod
    def _format_conversation(messages: list[dict[str, Any]]) -> str:
        lines: list[str] = []
        for m in messages:
            role = m.get("role", "unknown")
            content = str(m.get("content", ""))[:500]  # Truncate per message
            if content.strip():
                lines.append(f"{role}: {content}")
        return "\n".join(lines[-200:])  # Keep last 200 lines to avoid overwhelming

    @staticmethod
    def _parse_response(raw: str) -> list[dict[str, Any]]:
        import json

        raw = raw.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            lines = raw.splitlines()
            # Remove first and last line (the fences)
            if len(lines) >= 3:
                raw = "\n".join(lines[1:-1])

        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return [
                    f for f in data
                    if isinstance(f, dict) and "fact" in f
                ]
            return []
        except json.JSONDecodeError:
            logger.warning("knowledge_extractor event=parse_failed")
            return []
