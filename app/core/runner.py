import json
import asyncio
import time
from typing import Any

from openai import OpenAI

from app.configs.logger import logger
from app.core.hooks import BaseRunnerHooks
from app.core.middleware import BaseRunnerMiddleware, MiddlewareAbort
from app.obj.types import (
    AgentRunResult,
    ChatMessage,
    FunctionCallOutput,
    RunEndEvent,
    RunStartEvent,
    ToolCallEvent,
)
from app.agents.agent_base import BaseAgent
from app.core.tool_registry import ToolRegistry
from app.core.resilience import (
    with_timeout,
    TimeoutError as ToolTimeoutError,
    RateLimitError,
    CircuitBreaker,
    CircuitBreakerOpenError,
)
from app.core.rate_limiter import TokenRateLimiter
from app.core.tracing import get_tracer, AgentSpan
from app.core.checkpoint import CheckpointManager
from app.core.skill_dispatcher import SkillDispatcher

DEFAULT_LLM_TIMEOUT = 30.0
DEFAULT_MAX_RETRIES = 3


class AgentRunner:
    """Run an agent turn through LLM reasoning, tools, hooks, and checkpoints.

    The public contract is intentionally small: callers pass an agent, chat
    history, and optional tool/checkpoint/hook integrations, then receive a
    structured AgentRunResult. The loop stays synchronous so FastAPI can choose
    whether to call it directly or move it to a worker thread for SSE streaming.
    """

    def __init__(
        self,
        client: OpenAI,
        max_steps: int = 5,
        hooks: BaseRunnerHooks | None = None,
        middleware: BaseRunnerMiddleware | None = None,
        llm_timeout: float = DEFAULT_LLM_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        enable_tracing: bool = True,
        rate_limiter: TokenRateLimiter | None = None,
        llm_circuit_breaker: CircuitBreaker | None = None,
        skill_dispatcher: SkillDispatcher | None = None,
    ):
        self.client = client
        self.max_steps = max_steps
        self.hooks = hooks
        self.middleware = middleware
        self.llm_timeout = llm_timeout
        self.max_retries = max_retries
        self.enable_tracing = enable_tracing
        self.rate_limiter = rate_limiter
        self.llm_circuit_breaker = llm_circuit_breaker
        self.skill_dispatcher = skill_dispatcher
        self._circuit_breakers: dict[str, CircuitBreaker] = {}

    def _clear_checkpoint(
        self,
        checkpoint_manager: CheckpointManager | None,
        session_id: str | None,
    ) -> None:
        """Clear saved progress once a run reaches a terminal state."""
        if checkpoint_manager and session_id:
            checkpoint_manager.clear(session_id)
            logger.debug("runner event=checkpoint_clear session_id=%s", session_id)

    def _emit_run_end(
        self,
        hooks: BaseRunnerHooks | None,
        agent: BaseAgent,
        result: AgentRunResult,
        started_at: float,
        session_id: str | None,
    ) -> None:
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        event: RunEndEvent = {
            "agent_name": agent.name,
            "success": result["success"],
            "steps": result["steps"],
            "error": result["error"],
        }
        if hooks:
            hooks.on_run_end(event)

        logger.info(
            "runner event=run_end agent=%s session_id=%s success=%s "
            "steps=%s error=%s duration_ms=%s",
            agent.name,
            session_id or "",
            result["success"],
            result["steps"],
            result["error"] or "",
            duration_ms,
        )

    def _finish_run(
        self,
        hooks: BaseRunnerHooks | None,
        agent: BaseAgent,
        result: AgentRunResult,
        started_at: float,
        session_id: str | None,
    ) -> AgentRunResult:
        self._emit_run_end(hooks, agent, result, started_at, session_id)
        return result

    def _build_result(
        self,
        answer: str,
        success: bool,
        steps: int,
        tool_events: list[ToolCallEvent],
        error: str | None,
    ) -> AgentRunResult:
        return {
            "answer": answer,
            "success": success,
            "steps": steps,
            "tool_events": tool_events,
            "error": error,
        }

    def _resolve_tools(
        self,
        agent: BaseAgent,
        tool_registry: ToolRegistry | None,
    ) -> list[dict[str, Any]]:
        if tool_registry and agent.supports_tools():
            return tool_registry.get_openai_tools()
        return []

    def _start_run_span(
        self,
        tracer: Any,
        agent: BaseAgent,
    ) -> AgentSpan | None:
        span = AgentSpan(tracer) if tracer else None
        if span:
            span.start_run_span(agent.name, agent.model, self.max_steps)
        return span

    def _try_invoke_skill(
        self,
        agent: BaseAgent,
        history: list[ChatMessage],
    ) -> tuple[bool, Any]:
        """Handle slash-style skill commands before spending an LLM call."""
        if not self.skill_dispatcher or not history:
            return False, None

        last_msg = history[-1]
        if not isinstance(last_msg, dict) or last_msg.get("role") != "user":
            return False, None

        raw_input = last_msg.get("content", "")
        invoked, result = self.skill_dispatcher.try_invoke(raw_input, agent.name)
        if invoked:
            logger.info("runner event=skill_invoked agent=%s", agent.name)
        return invoked, result

    def _apply_llm_middleware(
        self,
        agent: BaseAgent,
        current_input: list[dict] | str,
        step: int,
    ) -> list[dict] | str:
        """Allow middleware to inspect or replace the next LLM input."""
        llm_context: dict = {
            "agent_name": agent.name,
            "model": agent.model,
            "step": step,
            "current_input": current_input,
        }
        if self.middleware:
            llm_context = self.middleware.before_llm(llm_context)
        return llm_context["current_input"]

    def _call_llm_with_resilience(
        self,
        agent: BaseAgent,
        current_input: list[dict] | str,
        tools: list[dict[str, Any]],
        step: int,
        session_id: str | None,
        span: AgentSpan | None,
    ) -> Any:
        """Call the model with rate limiting, timeout, retry, and circuit breaker.

        User-facing error mapping stays in run(), so this method can focus on
        transport and resilience mechanics while preserving the old result
        messages for callers.
        """
        if self.rate_limiter:
            self.rate_limiter.acquire(timeout=5.0)

        if (
            self.llm_circuit_breaker
            and self.llm_circuit_breaker.state == CircuitBreaker.OPEN
        ):
            logger.warning(
                "runner event=llm_circuit_breaker_open agent=%s session_id=%s "
                "step=%s",
                agent.name,
                session_id or "",
                step,
            )
            raise CircuitBreakerOpenError("LLM circuit breaker is open")

        def llm_call():
            return self.client.responses.create(
                model=agent.model,
                input=current_input,
                tools=tools if tools else None,
            )

        try:
            response = with_timeout(llm_call, self.llm_timeout)
        except ToolTimeoutError:
            logger.warning(
                "runner event=llm_error agent=%s session_id=%s step=%s "
                "error_type=%s timeout_seconds=%s",
                agent.name,
                session_id or "",
                step,
                "TimeoutError",
                self.llm_timeout,
            )
            if span:
                span.end_current_span(
                    error=ToolTimeoutError(
                        f"LLM call exceeded {self.llm_timeout}s"
                    )
                )
            if self.llm_circuit_breaker:
                self.llm_circuit_breaker.record_failure()
            if self.max_retries > 1:
                from tenacity import retry, stop_after_attempt, wait_exponential

                retry_decorator = retry(
                    stop=stop_after_attempt(self.max_retries),
                    wait=wait_exponential(multiplier=1, min=1, max=10),
                    reraise=True,
                )
                response = retry_decorator(llm_call)()
            else:
                raise
        except RateLimitError as e:
            logger.warning(
                "runner event=llm_error agent=%s session_id=%s step=%s "
                "error_type=%s",
                agent.name,
                session_id or "",
                step,
                type(e).__name__,
            )
            if span:
                span.end_current_span(error=e)
            if self.llm_circuit_breaker:
                self.llm_circuit_breaker.record_failure()
            raise
        except Exception as e:
            logger.exception(
                "runner event=llm_error agent=%s session_id=%s step=%s "
                "error_type=%s",
                agent.name,
                session_id or "",
                step,
                type(e).__name__,
            )
            if self.llm_circuit_breaker:
                self.llm_circuit_breaker.record_failure()
            raise

        if self.llm_circuit_breaker:
            self.llm_circuit_breaker.record_success()

        if span:
            span.end_current_span()

        return response

    def _get_tool_circuit_breaker(self, tool_name: str) -> CircuitBreaker:
        cb = self._circuit_breakers.get(tool_name)
        if cb is None:
            cb = CircuitBreaker(name=tool_name)
            self._circuit_breakers[tool_name] = cb
        return cb

    def _execute_tool_call(
        self,
        agent: BaseAgent,
        tool_registry: ToolRegistry,
        hooks: BaseRunnerHooks | None,
        span: AgentSpan | None,
        collected_events: list[ToolCallEvent],
        step: int,
        fc: Any,
    ) -> FunctionCallOutput:
        """Execute one function_call item and emit the matching tool events.

        The final AgentRunResult keeps only success/error tool events. The
        start event is still sent to hooks so streaming clients can render a
        tool-start notification without changing historical result payloads.
        """
        tool_name = fc.name
        call_id = fc.call_id
        try:
            preview_args = json.loads(fc.arguments)
        except json.JSONDecodeError:
            preview_args = {}

        if span:
            span.start_tool_span(tool_name, preview_args)

        # Start events are observer-only; final tool_events keep their
        # historical success/error-only shape.
        if hooks:
            hooks.on_tool_start({
                "agent_name": agent.name,
                "step": step,
                "tool_name": tool_name,
                "arguments": preview_args,
                "status": "start",
            })

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
                    # before_tool may abort, but its returned context is not a
                    # supported mutation point for the actual tool arguments.
                    self.middleware.before_tool(tool_context)
            except MiddlewareAbort as e:
                if span:
                    span.end_current_span()
                logger.warning(
                    "runner event=tool_error agent=%s step=%s tool=%s "
                    "status=%s error_type=%s",
                    agent.name,
                    step,
                    tool_name,
                    "middleware_abort",
                    type(e).__name__,
                )
                error_event: ToolCallEvent = {
                    "agent_name": agent.name,
                    "step": step,
                    "tool_name": tool_name,
                    "arguments": tool_args,
                    "status": "error",
                    "error": e.message,
                }
                collected_events.append(error_event)
                if hooks:
                    hooks.on_tool_end(error_event)
                agent.on_tool_event(error_event)
                result = e.message
        except json.JSONDecodeError:
            if span:
                span.end_current_span()
            logger.warning(
                "runner event=tool_error agent=%s step=%s tool=%s "
                "status=%s error_type=%s",
                agent.name,
                step,
                tool_name,
                "invalid_arguments",
                "JSONDecodeError",
            )
            result = "工具参数解析失败。"
        else:
            cb = self._get_tool_circuit_breaker(tool_name)

            def tool_call() -> str:
                if tool_registry.is_async(tool_name):
                    return asyncio.run(
                        tool_registry.call_async(tool_name, **tool_args)
                    )
                return tool_registry.call(tool_name, **tool_args)

            try:
                if cb.state == CircuitBreaker.OPEN:
                    raise CircuitBreakerOpenError(
                        f"Circuit breaker open for tool: {tool_name}"
                    )
                result = cb.call(with_timeout, tool_call, 10.0)
            except CircuitBreakerOpenError as e:
                if span:
                    span.end_current_span(error=e)
                result = f"工具暂时不可用（熔断器打开）：{e}"
                logger.warning(
                    "runner event=tool_error agent=%s step=%s tool=%s "
                    "status=%s error_type=%s",
                    agent.name,
                    step,
                    tool_name,
                    "circuit_breaker_open",
                    type(e).__name__,
                )
                tool_event: ToolCallEvent = {
                    "agent_name": agent.name,
                    "step": step,
                    "tool_name": tool_name,
                    "arguments": tool_args,
                    "status": "error",
                    "error": str(e),
                }
                collected_events.append(tool_event)
                agent.on_tool_event(tool_event)
                if hooks:
                    hooks.on_tool_end(tool_event)
            except ToolTimeoutError:
                cb.record_failure()
                if span:
                    span.end_current_span(error=ToolTimeoutError("Tool call timed out"))
                result = f"工具执行超时（10s）：{tool_name}"
                logger.warning(
                    "runner event=tool_error agent=%s step=%s tool=%s "
                    "status=%s error_type=%s",
                    agent.name,
                    step,
                    tool_name,
                    "timeout",
                    "TimeoutError",
                )
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
                if hooks:
                    hooks.on_tool_end(tool_event)
            except Exception as e:
                cb.record_failure()
                if span:
                    span.end_current_span(error=e)
                result = f"工具执行失败：{e}"
                logger.warning(
                    "runner event=tool_error agent=%s step=%s tool=%s "
                    "status=%s error_type=%s",
                    agent.name,
                    step,
                    tool_name,
                    "exception",
                    type(e).__name__,
                )
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
                if hooks:
                    hooks.on_tool_end(tool_event)
            else:
                if span:
                    span.end_current_span()
                logger.info(
                    "runner event=tool_success agent=%s step=%s tool=%s "
                    "result_chars=%s",
                    agent.name,
                    step,
                    tool_name,
                    len(str(result)),
                )
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
                if hooks:
                    hooks.on_tool_end(tool_event)

        return {
            "type": "function_call_output",
            "call_id": call_id,
            "output": result,
        }

    def _save_checkpoint(
        self,
        checkpoint_manager: CheckpointManager | None,
        session_id: str | None,
        step: int,
        current_input: list[FunctionCallOutput],
        agent: BaseAgent,
    ) -> None:
        """Persist the next model input after a tool round completes."""
        if checkpoint_manager and session_id:
            checkpoint_manager.save(
                session_id=session_id,
                step=step,
                history=list(current_input),
                agent_state=agent.get_state(),
            )
            logger.debug(
                "runner event=checkpoint_save session_id=%s step=%s "
                "history_length=%s",
                session_id,
                step,
                len(current_input),
            )

    def run(
        self,
        agent: BaseAgent,
        history: list[ChatMessage],
        tool_registry: ToolRegistry | None = None,
        hooks: BaseRunnerHooks | None = None,
        session_id: str | None = None,
        checkpoint_manager: CheckpointManager | None = None,
    ) -> AgentRunResult:
        """Execute one agent turn.

        Flow:
        1. emit run start hooks and initialize tracing;
        2. short-circuit slash skills when present;
        3. repeat LLM call -> optional tool calls until a final answer appears;
        4. save checkpoints after tool rounds and clear them on any terminal
           result.
        """
        effective_hooks = hooks if hooks is not None else self.hooks
        tracer = get_tracer() if self.enable_tracing else None
        run_started_at = time.perf_counter()
        last_step = 0

        start_event: RunStartEvent = {
            "agent_name": agent.name,
            "history_length": len(history),
            "model": agent.model,
        }
        if effective_hooks:
            effective_hooks.on_run_start(start_event)

        current_input: list[dict] | str = history
        collected_events: list[ToolCallEvent] = []
        tools = self._resolve_tools(agent, tool_registry)
        logger.info(
            "runner event=run_start agent=%s session_id=%s model=%s "
            "history_length=%s max_steps=%s tools_count=%s",
            agent.name,
            session_id or "",
            agent.model,
            len(history),
            self.max_steps,
            len(tools),
        )
        # Tracing is owned by the runner so hook implementations can remain
        # lightweight observers rather than mandatory tracing adapters.
        span = self._start_run_span(tracer, agent)

        invoked, skill_result = self._try_invoke_skill(agent, history)
        if invoked:
            if span:
                span.end_all()
            self._clear_checkpoint(checkpoint_manager, session_id)
            return self._finish_run(
                effective_hooks,
                agent,
                self._build_result(
                    answer=skill_result,
                    success=True,
                    steps=0,
                    tool_events=[],
                    error=None,
                ),
                run_started_at,
                session_id,
            )

        try:
            for step in range(1, self.max_steps + 1):
                last_step = step
                logger.info(
                    "runner event=step_start agent=%s session_id=%s step=%s "
                    "input_length=%s",
                    agent.name,
                    session_id or "",
                    step,
                    len(current_input),
                )
                if span:
                    span.start_step_span(step)

                if effective_hooks:
                    effective_hooks.on_llm_start({
                        "agent_name": agent.name,
                        "step": step,
                        "model": agent.model,
                        "input_length": len(current_input),
                    })

                try:
                    current_input = self._apply_llm_middleware(
                        agent,
                        current_input,
                        step,
                    )
                except MiddlewareAbort as e:
                    if span:
                        span.end_current_span()
                        span.end_all()
                    self._clear_checkpoint(checkpoint_manager, session_id)
                    return self._finish_run(
                        effective_hooks,
                        agent,
                        self._build_result(
                            answer=e.message,
                            success=False,
                            steps=step,
                            tool_events=collected_events,
                            error="middleware_abort_before_llm",
                        ),
                        run_started_at,
                        session_id,
                    )

                if span:
                    span.start_llm_span(len(current_input))

                try:
                    response = self._call_llm_with_resilience(
                        agent=agent,
                        current_input=current_input,
                        tools=tools,
                        step=step,
                        session_id=session_id,
                        span=span,
                    )
                except CircuitBreakerOpenError:
                    if span:
                        span.end_current_span()
                        span.end_all()
                    self._clear_checkpoint(checkpoint_manager, session_id)
                    return self._finish_run(
                        effective_hooks,
                        agent,
                        self._build_result(
                            answer="LLM 服务暂时不可用（熔断器打开），请稍后重试。",
                            success=False,
                            steps=step,
                            tool_events=collected_events,
                            error="llm_circuit_breaker_open",
                        ),
                        run_started_at,
                        session_id,
                    )
                except ToolTimeoutError:
                    if span:
                        span.end_all()
                    self._clear_checkpoint(checkpoint_manager, session_id)
                    return self._finish_run(
                        effective_hooks,
                        agent,
                        self._build_result(
                            answer=f"LLM 调用超时（{self.llm_timeout}s），请稍后重试。",
                            success=False,
                            steps=step,
                            tool_events=collected_events,
                            error="llm_timeout",
                        ),
                        run_started_at,
                        session_id,
                    )
                except RateLimitError:
                    if span:
                        span.end_all()
                    self._clear_checkpoint(checkpoint_manager, session_id)
                    return self._finish_run(
                        effective_hooks,
                        agent,
                        self._build_result(
                            answer=f"请求过于频繁，请稍后重试。",
                            success=False,
                            steps=step,
                            tool_events=collected_events,
                            error="rate_limit_exceeded",
                        ),
                        run_started_at,
                        session_id,
                    )

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
                    self._clear_checkpoint(checkpoint_manager, session_id)
                    return self._finish_run(
                        effective_hooks,
                        agent,
                        self._build_result(
                            answer=response.output_text or "模型没有返回文本结果。",
                            success=True,
                            steps=step,
                            tool_events=collected_events,
                            error=None,
                        ),
                        run_started_at,
                        session_id,
                    )

                if tool_registry is None:
                    if span:
                        span.end_all()
                    self._clear_checkpoint(checkpoint_manager, session_id)
                    return self._finish_run(
                        effective_hooks,
                        agent,
                        self._build_result(
                            answer="当前 Agent 未配置工具注册中心。",
                            success=False,
                            steps=step,
                            tool_events=collected_events,
                            error="missing_tool_registry",
                        ),
                        run_started_at,
                        session_id,
                    )

                next_input = [
                    self._execute_tool_call(
                        agent=agent,
                        tool_registry=tool_registry,
                        hooks=effective_hooks,
                        span=span,
                        collected_events=collected_events,
                        step=step,
                        fc=fc,
                    )
                    for fc in function_calls
                ]

                current_input = next_input
                self._save_checkpoint(
                    checkpoint_manager,
                    session_id,
                    step,
                    next_input,
                    agent,
                )

            if span:
                span.end_all()
            self._clear_checkpoint(checkpoint_manager, session_id)
            return self._finish_run(
                effective_hooks,
                agent,
                self._build_result(
                    answer="抱歉，任务执行步数过多，已停止。",
                    success=False,
                    steps=self.max_steps,
                    tool_events=collected_events,
                    error="max_steps_exceeded",
                ),
                run_started_at,
                session_id,
            )
        except Exception as e:
            if span:
                span.end_all(error=e)
            logger.exception(
                "runner event=run_error agent=%s session_id=%s step=%s error_type=%s",
                agent.name,
                session_id or "",
                last_step,
                type(e).__name__,
            )
            self._emit_run_end(
                effective_hooks,
                agent,
                self._build_result(
                    answer="",
                    success=False,
                    steps=last_step,
                    tool_events=collected_events,
                    error=type(e).__name__,
                ),
                run_started_at,
                session_id,
            )
            raise
