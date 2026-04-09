from app.agents.agent_base import BaseAgent


class ChatAgent(BaseAgent):
    def __init__(self, name: str, model: str, system_prompt: str):
        super().__init__(name=name, model=model)
        self._system_prompt = system_prompt

    def get_system_prompt(self) -> str:
        return self._system_prompt

    def supports_tools(self) -> bool:
        return True