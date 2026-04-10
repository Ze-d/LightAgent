from app.core.middleware import BaseRunnerMiddleware, MiddlewareAbort
from app.obj.types import ToolContext


class ToolPermissionMiddleware(BaseRunnerMiddleware):
    def __init__(self, allowed_tools: set[str] | None = None, blocked_tools: set[str] | None = None):
        self.allowed_tools = allowed_tools or set()
        self.blocked_tools = blocked_tools or set()

    def before_tool(self, context: ToolContext) -> ToolContext:
        tool_name = context["tool_name"]

        if self.allowed_tools and tool_name not in self.allowed_tools:
            raise MiddlewareAbort(f"工具未授权：{tool_name}")

        if tool_name in self.blocked_tools:
            raise MiddlewareAbort(f"工具已被禁用：{tool_name}")

        return context