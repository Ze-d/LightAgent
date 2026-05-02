from app.obj.types import LLMContext, ToolContext


class MiddlewareAbort(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class BaseRunnerMiddleware:
    def before_llm(self, context: LLMContext) -> LLMContext:
        return context

    def before_tool(self, context: ToolContext) -> ToolContext:
        return context


class CompositeRunnerMiddleware(BaseRunnerMiddleware):
    def __init__(self, middlewares: list[BaseRunnerMiddleware] | None = None):
        self.middlewares = middlewares or []

    def before_llm(self, context: LLMContext) -> LLMContext:
        for middleware in self.middlewares:
            context = middleware.before_llm(context)
        return context

    def before_tool(self, context: ToolContext) -> ToolContext:
        for middleware in self.middlewares:
            context = middleware.before_tool(context)
        return context
