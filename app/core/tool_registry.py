from typing import Any
import inspect

from app.obj.types import SideEffectPolicy, ToolSpec


DEFAULT_SIDE_EFFECT_POLICY: SideEffectPolicy = "read_only"


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        name = spec["name"]
        if name in self._tools:
            raise ValueError(f"Tool already registered: {name}")
        registered_spec: ToolSpec = dict(spec)
        registered_spec.setdefault("side_effect_policy", DEFAULT_SIDE_EFFECT_POLICY)
        self._tools[name] = registered_spec

    def get_handler(self, name: str):
        spec = self._tools.get(name)
        return None if spec is None else spec["handler"]

    def get_openai_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "name": spec["name"],
                "description": spec["description"],
                "parameters": spec["parameters"],
            }
            for spec in self._tools.values()
        ]

    def call(self, name: str, **kwargs: Any) -> str:
        handler = self.get_handler(name)
        if handler is None:
            raise ValueError(f"Unknown tool: {name}")
        return handler(**kwargs)

    async def call_async(self, name: str, **kwargs: Any) -> str:
        handler = self.get_handler(name)
        if handler is None:
            raise ValueError(f"Unknown tool: {name}")
        if inspect.iscoroutinefunction(handler):
            return await handler(**kwargs)
        return handler(**kwargs)

    def is_async(self, name: str) -> bool:
        handler = self.get_handler(name)
        return handler is not None and inspect.iscoroutinefunction(handler)

    def get_side_effect_policy(self, name: str) -> SideEffectPolicy:
        spec = self._tools.get(name)
        if spec is None:
            return DEFAULT_SIDE_EFFECT_POLICY
        return spec.get("side_effect_policy", DEFAULT_SIDE_EFFECT_POLICY)

    def list_names(self) -> list[str]:
        return list(self._tools.keys())
