from app.agents.chat_agent import ChatAgent
from app.obj.types import ToolCallEvent


class ToolAwareAgent(ChatAgent):
    def __init__(self, name: str, model: str, system_prompt: str,
                 tool_call_listener: "Callable[[ToolCallEvent], None] | None" = None):
        super().__init__(name=name, model=model, system_prompt=system_prompt)
        self.tool_event_history: list[ToolCallEvent] = []
        self._listener = tool_call_listener

    def on_tool_event(self, event: ToolCallEvent) -> None:
        self.tool_event_history.append(event)
        if self._listener:
            self._listener(event)

    def emit_tool_event(self, event: ToolCallEvent) -> None:
        self.on_tool_event(event)