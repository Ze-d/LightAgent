from app.tools.builtin_tools import calculator, get_current_time
from app.tools.register import build_default_registry

_registry = build_default_registry()
TOOL_MAP = {name: _registry.get_handler(name) for name in _registry.list_names()}
TOOLS = _registry.get_openai_tools()

__all__ = ["calculator", "get_current_time", "TOOLS", "TOOL_MAP"]
