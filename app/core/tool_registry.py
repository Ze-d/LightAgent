from app.obj.types import ToolSpec
from typing import Any
# 工具注册中心，负责管理工具的注册和调用
class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, ToolSpec] = {}
    # 注册工具
    def register(self, spec: ToolSpec) -> None:
        name = spec["name"]
        if name in self._tools:
            raise ValueError(f"Tool already registered: {name}")
        self._tools[name] = spec
    # 获取工具处理函数
    def get_handler(self, name: str):
        spec = self._tools.get(name)
        return None if spec is None else spec["handler"]
    # 获取工具的OpenAI格式描述
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
    # 调用工具
    def call(self, name: str, **kwargs: Any) -> str:
        handler = self.get_handler(name)
        if handler is None:
            raise ValueError(f"Unknown tool: {name}")
        return handler(**kwargs)
    # 列出所有注册的工具名称
    def list_names(self) -> list[str]:
        return list(self._tools.keys())