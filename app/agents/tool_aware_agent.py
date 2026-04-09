from collections.abc import Callable
from typing import override
from app.agents.chat_agent import ChatAgent
from app.obj.types import ToolCallEvent


class ToolAwareAgent(ChatAgent):
    def __init__(
        self,
        name: str,
        model: str,
        system_prompt: str,
        tool_call_listener: Callable[[ToolCallEvent], None] | None = None,
    ):
        super().__init__(name=name, model=model, system_prompt=system_prompt)
        self.tool_call_listener = tool_call_listener
    # 工具调用事件发出方法 
    @override   
    def emit_tool_event(self, event: ToolCallEvent) -> None:
        if self.tool_call_listener is not None:
            self.tool_call_listener(event)