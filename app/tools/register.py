from app.core.tool_registry import ToolRegistry
from app.tools.builtin_tools import calculator, get_current_time


def build_default_registry() -> ToolRegistry:
    registry = ToolRegistry()

    registry.register({
        "name": "calculator",
        "description": "Calculate a math expression.",
        "parameters": {
            "type": "object",
            "properties": {
                "expression": {"type": "string"}
            },
            "required": ["expression"],
            "additionalProperties": False,
        },
        "handler": calculator,
    })

    registry.register({
        "name": "get_current_time",
        "description": "Get the current local time for a city.",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {"type": "string"}
            },
            "required": ["city"],
            "additionalProperties": False,
        },
        "handler": get_current_time,
    })

    return registry