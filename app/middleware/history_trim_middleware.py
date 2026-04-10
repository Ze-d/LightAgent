from app.core.middleware import BaseRunnerMiddleware
from app.obj.types import LLMContext


class HistoryTrimMiddleware(BaseRunnerMiddleware):
    def __init__(self, max_messages: int = 20):
        self.max_messages = max_messages

    def before_llm(self, context: LLMContext) -> LLMContext:
        current_input = context["current_input"]

        if not isinstance(current_input, list):
            return context

        if len(current_input) <= self.max_messages:
            return context

        system_msg = current_input[0]
        recent_msgs = current_input[-(self.max_messages - 1):]
        context["current_input"] = [system_msg] + recent_msgs
        return context