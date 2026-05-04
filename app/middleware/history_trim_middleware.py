from app.core.middleware import BaseRunnerMiddleware
from app.core.token_budget import TokenBudgetTrimmer
from app.obj.types import LLMContext
from app.memory.summarizer import MessageSummarizer


class HistoryTrimMiddleware(BaseRunnerMiddleware):
    def __init__(
        self,
        max_messages: int = 20,
        max_input_tokens: int | None = None,
    ):
        self.max_messages = max_messages
        self.summarizer = MessageSummarizer(target_messages=max_messages)
        self.token_budget = TokenBudgetTrimmer(max_input_tokens=max_input_tokens)

    def before_llm(self, context: LLMContext) -> LLMContext:
        current_input = context["current_input"]

        if not isinstance(current_input, list):
            return context

        if not self._is_chat_history(current_input):
            return context

        budget_result = self.token_budget.apply(current_input)
        if budget_result.reason != "token_budget_not_configured":
            context["current_input"] = budget_result.messages
            current_input = budget_result.messages

        if not self.max_messages or len(current_input) <= self.max_messages:
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
