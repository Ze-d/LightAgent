from app.obj.types import (
    RunStartEvent,
    RunEndEvent,
    LLMStartEvent,
    LLMEndEvent,
    ToolCallEvent,
)


class BaseRunnerHooks:
    def on_run_start(self, event: RunStartEvent) -> None:
        pass

    def on_run_end(self, event: RunEndEvent) -> None:
        pass

    def on_llm_start(self, event: LLMStartEvent) -> None:
        pass

    def on_llm_end(self, event: LLMEndEvent) -> None:
        pass

    def on_tool_start(self, event: ToolCallEvent) -> None:
        pass

    def on_tool_end(self, event: ToolCallEvent) -> None:
        pass
    
class CompositeRunnerHooks(BaseRunnerHooks):
    def __init__(self, hooks: list[BaseRunnerHooks] | None = None):
        self.hooks = hooks or []

    def on_run_start(self, event: RunStartEvent) -> None:
        for hook in self.hooks:
            hook.on_run_start(event)

    def on_run_end(self, event: RunEndEvent) -> None:
        for hook in self.hooks:
            hook.on_run_end(event)

    def on_llm_start(self, event: LLMStartEvent) -> None:
        for hook in self.hooks:
            hook.on_llm_start(event)

    def on_llm_end(self, event: LLMEndEvent) -> None:
        for hook in self.hooks:
            hook.on_llm_end(event)

    def on_tool_start(self, event: ToolCallEvent) -> None:
        for hook in self.hooks:
            hook.on_tool_start(event)

    def on_tool_end(self, event: ToolCallEvent) -> None:
        for hook in self.hooks:
            hook.on_tool_end(event)