from typing import Any
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

    def get_state(self) -> dict[str, Any]:
        return {"tool_event_history": list(self.tool_event_history)}

    def restore_state(self, state: dict[str, Any]) -> None:
        self.tool_event_history = list(state.get("tool_event_history", []))