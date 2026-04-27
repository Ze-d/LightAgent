from app.core.tool_registry import ToolRegistry
from app.tools.builtin_tools import (
    calculator,
    get_current_time,
    CalculatorInput,
    GetCurrentTimeInput,
)
from app.tools.memory_tools import (
    memory_append_session_summary,
    memory_read,
    MemoryAppendSessionSummaryInput,
    MemoryReadInput,
)
from app.tools.validator import create_tool_spec


def build_default_registry() -> ToolRegistry:
    registry = ToolRegistry()

    registry.register(create_tool_spec(
        name="calculator",
        description="Calculate a math expression and return the result.",
        model_cls=CalculatorInput,
        handler=calculator,
    ))

    registry.register(create_tool_spec(
        name="get_current_time",
        description="Get the current local time for a city.",
        model_cls=GetCurrentTimeInput,
        handler=get_current_time,
    ))

    registry.register(create_tool_spec(
        name="memory_read",
        description="Read project, user, session, or combined document memory.",
        model_cls=MemoryReadInput,
        handler=memory_read,
    ))

    registry.register(create_tool_spec(
        name="memory_append_session_summary",
        description="Append a concise summary to the current session memory document.",
        model_cls=MemoryAppendSessionSummaryInput,
        handler=memory_append_session_summary,
    ))

    return registry
