from abc import ABC, abstractmethod
from app.obj.types import ToolCallEvent

class BaseAgent(ABC):
    def __init__(self, name: str, model: str):
        self.name = name
        self.model = model

    @abstractmethod
    def get_system_prompt(self) -> str:
        """返回当前 Agent 的 system prompt"""
        pass

    @abstractmethod
    def supports_tools(self) -> bool:
        """标记当前 Agent 是否支持工具调用"""
        pass
    def emit_tool_event(self, event: ToolCallEvent) -> None:
        """默认什么都不做，子类可覆盖"""
        return