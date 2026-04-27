from app.core.middleware import BaseRunnerMiddleware
from app.obj.types import LLMContext
from app.memory.summarizer import MessageSummarizer


class HistoryTrimMiddleware(BaseRunnerMiddleware):
    def __init__(self, max_messages: int = 20):
        self.max_messages = max_messages
        self.summarizer = MessageSummarizer(target_messages=max_messages)

    def before_llm(self, context: LLMContext) -> LLMContext:
        current_input = context["current_input"]

        if not isinstance(current_input, list):
            return context

        if len(current_input) <= self.max_messages:
            return context

        if not self._is_chat_history(current_input):
            return context

        context["current_input"] = self.summarizer.summarize(current_input)
        return context

    def _is_chat_history(self, current_input: list[dict]) -> bool:
        return all(
            isinstance(item, dict)
            and item.get("role") in {"system", "user", "assistant"}
            and "content" in item
            for item in current_input
        )
