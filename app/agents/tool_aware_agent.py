from app.agents.chat_agent import ChatAgent
from app.obj.types import ToolCallEvent


class ToolAwareAgent(ChatAgent):
    def __init__(self, name: str, model: str, system_prompt: str):
        super().__init__(name=name, model=model, system_prompt=system_prompt)
        self.tool_event_history: list[ToolCallEvent] = []

    def on_tool_event(self, event: ToolCallEvent) -> None:
        self.tool_event_history.append(event)