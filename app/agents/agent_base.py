from abc import ABC, abstractmethod
from typing import Any
from app.obj.types import ToolCallEvent


class BaseAgent(ABC):
    def __init__(self, name: str, model: str):
        self.name = name
        self.model = model

    @abstractmethod
    def get_system_prompt(self) -> str:
        """Return current agent's system prompt"""
        pass

    @abstractmethod
    def supports_tools(self) -> bool:
        """Check if the agent supports tool calling"""
        pass

    def on_tool_event(self, event: ToolCallEvent) -> None:
        pass

    def get_state(self) -> dict[str, Any]:
        """Return agent state for checkpoint recovery"""
        return {}

    def restore_state(self, state: dict[str, Any]) -> None:
        """Restore agent state from checkpoint"""
        pass