import json
from openai import OpenAI
import asyncio

from app.configs.logger import logger
from app.core.hooks import BaseRunnerHooks
from app.core.middleware import BaseRunnerMiddleware, MiddlewareAbort
from app.obj.types import AgentRunResult, ChatMessage, FunctionCallOutput, RunStartEvent, ToolCallEvent
from app.agents.agent_base import BaseAgent
from app.core.tool_registry import ToolRegistry
from app.core.resilience import (
    with_timeout,
    TimeoutError as ToolTimeoutError,
    RateLimitError,
    CircuitBreaker,
    CircuitBreakerOpenError,
)
from app.core.tracing import get_tracer, AgentSpan

DEFAULT_LLM_TIMEOUT = 30.0
DEFAULT_MAX_RETRIES = 3


class AgentRunner:
    def __init__(
        self,
        client: OpenAI,
        max_steps: int = 5,
        hooks: BaseRunnerHooks | None = None,
        middleware: BaseRunnerMiddleware | None = None,
        llm_timeout: float = DEFAULT_LLM_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        enable_tracing: bool = True,
    ):
        self.client = client
        self.max_steps = max_steps
        self.hooks = hooks
        self.middleware = middleware
        self.llm_timeout = llm_timeout
        self.max_retries = max_retries
        self.enable_tracing = enable_tracing
        self._circuit_breakers: dict[str, CircuitBreaker] = {}

    def run(
        self,
        agent: BaseAgent,
        history: list[ChatMessage],
        tool_registry: ToolRegistry | None = None,
        hooks: BaseRunnerHooks | None = None,
    ) -> AgentRunResult:
        effective_hooks = hooks if hooks is not None else self.hooks
        tracer = get_tracer() if self.enable_tracing else None

        start_event: RunStartEvent = {
            "agent_name": agent.name,
            "history_length": len(history),
            "model": agent.model,
        }
        if effective_hooks:
            effective_hooks.on_run_start(start_event)

        current_input = history
        collected_events: list[ToolCallEvent] = []
        tools = (
            tool_registry.get_openai_tools()
            if (tool_registry and agent.supports_tools())
            else []
        )

        span = AgentSpan(tracer) if tracer else None
        if span:
            span.start_run_span(agent.name, agent.model, self.max_steps)

        try:
            for step in range(1, self.max_steps + 1):
                logger.info(f"runner step={step} agent={agent.name}")
                if span:
                    span.start_step_span(step)

                if effective_hooks:
                    effective_hooks.on_llm_start({
                        "agent_name": agent.name,
                        "step": step,
                        "model": agent.model,
                        "input_length": len(current_input),
                    })

                llm_context: dict = {
                    "agent_name": agent.name,
                    "model": agent.model,
                    "step": step,
                    "current_input": current_input,
                }
                try:
                    if self.middleware:
                        llm_context = self.middleware.before_llm(llm_context)
                except MiddlewareAbort as e:
                    if span:
                        span.end_current_span()
                        span.end_all()
                    return {
                        "answer": e.message,
                        "success": False,
                        "steps": step,
                        "tool_events": collected_events,
                        "error": "middleware_abort_before_llm",
                    }
                current_input = llm_context["current_input"]

                if span:
                    span.start_llm_span(len(current_input))

                def llm_call():
                    return self.client.responses.create(
                        model=agent.model,
                        input=current_input,
                        tools=tools if tools else None,
                    )

                try:
                    response = with_timeout(llm_call, self.llm_timeout)
                except ToolTimeoutError:
                    if span:
                        span.end_current_span(error=ToolTimeoutError(f"LLM call exceeded {self.llm_timeout}s"))
                    if self.max_retries > 1:
                        from tenacity import retry, stop_after_attempt, wait_exponential
                        retry_decorator = retry(
                            stop=stop_after_attempt(self.max_retries),
                            wait=wait_exponential(multiplier=1, min=1, max=10),
                            reraise=True,
                        )
                        response = retry_decorator(llm_call)()
                    else:
                        if span:
                            span.end_all()
                        return {
                            "answer": f"LLM 调用超时（{self.llm_timeout}s），请稍后重试。",
                            "success": False,
                            "steps": step,
                            "tool_events": collected_events,
                            "error": "llm_timeout",
                        }

                if span:
                    span.end_current_span()

                if effective_hooks:
                    effective_hooks.on_llm_end({
                        "agent_name": agent.name,
                        "step": step,
                        "output_items_count": len(response.output),
                    })
                function_calls = [
                    item for item in response.output
                    if item.type == "function_call"
                ]

                if not function_calls:
                    if span:
                        span.end_all()
                    return {
                        "answer": response.output_text or "模型没有返回文本结果。",
                        "success": True,
                        "steps": step,
                        "tool_events": collected_events,
                        "error": None,
                    }

                if tool_registry is None:
                    if span:
                        span.end_all()
                    return {
                        "answer": "当前 Agent 未配置工具注册中心。",
                        "success": False,
                        "steps": step,
                        "tool_events": collected_events,
                        "error": "missing_tool_registry",
                    }

                next_input: list[FunctionCallOutput] = []

                for fc in function_calls:
                    tool_name = fc.name
                    call_id = fc.call_id

                    if span:
                        try:
                            tool_args = json.loads(fc.arguments)
                        except json.JSONDecodeError:
                            tool_args = {}
                        span.start_tool_span(tool_name, tool_args)

                    try:
                        tool_args = json.loads(fc.arguments)
                        tool_context: dict = {
                            "agent_name": agent.name,
                            "step": step,
                            "tool_name": tool_name,
                            "arguments": tool_args,
                        }

                        try:
                            if self.middleware:
                                tool_context = self.middleware.before_tool(tool_context)
                        except MiddlewareAbort as e:
                            if span:
                                span.end_current_span()
                            error_event: ToolCallEvent = {
                                "agent_name": agent.name,
                                "step": step,
                                "tool_name": tool_name,
                                "arguments": tool_args,
                                "status": "error",
                                "error": e.message,
                            }
                            collected_events.append(error_event)
                            if effective_hooks:
                                effective_hooks.on_tool_end(error_event)
                            agent.on_tool_event(error_event)
                            result = e.message
                    except json.JSONDecodeError:
                        if span:
                            span.end_current_span()
                        result = "工具参数解析失败。"
                    else:
                        cb = self._circuit_breakers.get(tool_name)
                        if cb is None:
                            cb = CircuitBreaker(name=tool_name)
                            self._circuit_breakers[tool_name] = cb

                        def tool_call() -> str:
                            if tool_registry.is_async(tool_name):
                                return asyncio.run(
                                    tool_registry.call_async(tool_name, **tool_args)
                                )
                            return tool_registry.call(tool_name, **tool_args)

                        try:
                            if cb.state == CircuitBreaker.OPEN:
                                raise CircuitBreakerOpenError(f"Circuit breaker open for tool: {tool_name}")
                            result = cb.call(with_timeout, tool_call, 10.0)
                        except CircuitBreakerOpenError as e:
                            if span:
                                span.end_current_span(error=e)
                            result = f"工具暂时不可用（熔断器打开）：{e}"
                            tool_event = {
                                "agent_name": agent.name,
                                "step": step,
                                "tool_name": tool_name,
                                "arguments": tool_args,
                                "status": "error",
                                "error": str(e),
                            }
                            collected_events.append(tool_event)
                            agent.on_tool_event(tool_event)
                            if effective_hooks:
                                effective_hooks.on_tool_end(tool_event)
                        except ToolTimeoutError:
                            cb.record_failure()
                            if span:
                                span.end_current_span(error=ToolTimeoutError("Tool call timed out"))
                            result = f"工具执行超时（10s）：{tool_name}"
                            tool_event = {
                                "agent_name": agent.name,
                                "step": step,
                                "tool_name": tool_name,
                                "arguments": tool_args,
                                "status": "error",
                                "error": result,
                            }
                            collected_events.append(tool_event)
                            agent.on_tool_event(tool_event)
                            if effective_hooks:
                                effective_hooks.on_tool_end(tool_event)
                        except Exception as e:
                            cb.record_failure()
                            if span:
                                span.end_current_span(error=e)
                            result = f"工具执行失败：{e}"
                            tool_event = {
                                "agent_name": agent.name,
                                "step": step,
                                "tool_name": tool_name,
                                "arguments": tool_args,
                                "status": "error",
                                "error": str(e),
                            }
                            collected_events.append(tool_event)
                            agent.on_tool_event(tool_event)
                            if effective_hooks:
                                effective_hooks.on_tool_end(tool_event)
                        else:
                            if span:
                                span.end_current_span()
                            tool_event = {
                                "agent_name": agent.name,
                                "step": step,
                                "tool_name": tool_name,
                                "arguments": tool_args,
                                "status": "success",
                                "result": result,
                            }
                            collected_events.append(tool_event)
                            agent.on_tool_event(tool_event)
                            if effective_hooks:
                                effective_hooks.on_tool_end(tool_event)

                    next_input.append({
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": result,
                    })

                current_input = next_input

            if span:
                span.end_all()
            return {
                "answer": "抱歉，任务执行步数过多，已停止。",
                "success": False,
                "steps": self.max_steps,
                "tool_events": collected_events,
                "error": "max_steps_exceeded",
            }
        except Exception as e:
            if span:
                span.end_all(error=e)
            raise