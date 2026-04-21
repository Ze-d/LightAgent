from app.core.tool_registry import ToolRegistry
from app.tools.builtin_tools import (
    calculator,
    get_current_time,
    CalculatorInput,
    GetCurrentTimeInput,
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

    return registry
