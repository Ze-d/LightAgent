# =============================================================================
# 标准库导入
# =============================================================================
import asyncio          # 异步 I/O，用于执行异步工具调用
import json             # JSON 序列化/反序列化，处理工具调用参数
import time             # 性能计时，用于计算整个运行耗时
from types import SimpleNamespace  # 将 dict 转为对象，便于兼容 function_call 结构
from typing import Any             # 类型标注
from uuid import uuid4             # 生成每次运行的唯一 ID

# =============================================================================
# 第三方库导入
# =============================================================================
from openai import OpenAI  # OpenAI SDK，通过 responses.create 调用 LLM

# =============================================================================
# 项目内部模块导入
# =============================================================================
from app.configs.logger import logger                     # 结构化日志
from app.core.hooks import BaseRunnerHooks                # 运行生命周期钩子基类
from app.core.middleware import BaseRunnerMiddleware, MiddlewareAbort  # 中间件及其中止异常
from app.obj.types import (
    AgentRunResult,       # 运行结果结构体
    ChatMessage,          # 聊天消息类型
    FunctionCallOutput,   # 工具调用返回结构
    RunEndEvent,          # 运行结束事件
    RunStartEvent,        # 运行开始事件
    ToolCallEvent,        # 工具调用事件（含成功/失败状态）
)
from app.agents.agent_base import BaseAgent               # Agent 基类
from app.core.tool_registry import ToolRegistry           # 工具注册中心，管理所有可用工具
from app.core.tool_selection import (
    ScopedToolRegistryView,
    ToolCatalog,
    ToolSelectionRequest,
)
from app.core.resilience import (
    with_timeout,                                         # 超时装饰器
    TimeoutError as ToolTimeoutError,                     # 超时异常（重命名为工具超时）
    RateLimitError,                                       # 限流异常
    CircuitBreaker,                                       # 熔断器
    CircuitBreakerOpenError,                              # 熔断器打开异常
)
from app.core.rate_limiter import TokenRateLimiter        # 令牌桶限流器
from app.core.tracing import get_tracer, AgentSpan        # 分布式追踪（Span）
from app.core.checkpoint import (
    Checkpoint,                                           # 检查点数据结构
    CheckpointOrchestrator,                               # 检查点编排器（保存/恢复/清理）
    CheckpointPhase,                                      # 检查点阶段枚举
    ResumeContext,                                        # 恢复上下文
    ToolExecutionRecord,                                  # 工具执行记录
)
from app.core.cancellation import CancellationToken, RunnerCancelledError
from app.core.context_builder import ProviderContextState  # Provider-side context state
from app.core.skill_dispatcher import SkillDispatcher     # 技能调度器（处理 /skill 命令）

# =============================================================================
# 默认配置常量
# =============================================================================
DEFAULT_LLM_TIMEOUT = 30.0      # LLM 调用默认超时时间（秒）
DEFAULT_MAX_RETRIES = 3         # LLM 调用失败后默认重试次数


# =============================================================================
# AgentRunner —— Agent 运行核心引擎
# =============================================================================
# 职责：编排单次 Agent 回合的完整生命周期。
#
# 一条完整的运行链路如下：
#   1. 触发 run_start 钩子，初始化追踪 Span
#   2. 如果用户输入是 /skill 命令，直接调度技能并返回（跳过 LLM）
#   3. 进入逐步循环（最多 max_steps 步）：
#      a. 调用 LLM（带超时/重试/熔断/限流）
#      b. 如果 LLM 返回最终文本 → 结束，返回答案
#      c. 如果 LLM 返回 function_call → 执行工具 → 将结果喂回 LLM → 继续下一步
#   4. 每步在关键节点保存检查点，支持中断后恢复
#   5. 任何异常都会被捕获并映射为用户可读的错误结果
#
# 设计要点：
#   - 同步循环：FastAPI 可直接调用，也可放入线程池做 SSE 流式
#   - 可插拔：钩子、中间件、追踪、限流、熔断均可选配
#   - 可恢复：通过检查点机制支持中断后的断点续跑
# =============================================================================
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
        checkpoint: CheckpointOrchestrator | None = None,
        tool_selector: Any | None = None,
    ):
        # ---- LLM 客户端与基础配置 ----
        self.client = client                # OpenAI 客户端实例
        self.max_steps = max_steps          # 单次运行最大步数（防止无限循环）
        self.llm_timeout = llm_timeout      # LLM 调用超时（秒）
        self.max_retries = max_retries      # LLM 调用失败重试次数
        self.enable_tracing = enable_tracing  # 是否开启分布式追踪

        # ---- 可插拔组件 ----
        self.hooks = hooks                  # 生命周期钩子（on_run_start/end, on_tool_start/end 等）
        self.middleware = middleware        # 中间件（before_llm, before_tool）
        self.rate_limiter = rate_limiter    # 令牌桶限流器，控制 LLM 调用频率
        self.llm_circuit_breaker = llm_circuit_breaker  # LLM 级别熔断器
        self.skill_dispatcher = skill_dispatcher        # 技能调度器（处理 /skill 命令）
        self._checkpoint = checkpoint       # 检查点编排器（保存/恢复/清理，可选）
        self.tool_selector = tool_selector  # 可选：单轮工具暴露选择器

        # ---- 内部状态 ----
        # 按工具名存储的熔断器字典，每个工具独立熔断
        self._circuit_breakers: dict[str, CircuitBreaker] = {}

    # -------------------------------------------------------------------------
    # 触发运行结束事件
    # -------------------------------------------------------------------------
    # 1. 计算从 run() 开始到现在的总耗时（毫秒）
    # 2. 构造 RunEndEvent 并通知钩子（用于流式推送、监控等）
    # 3. 记录结构化日志
    # -------------------------------------------------------------------------
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

    # -------------------------------------------------------------------------
    # 统一收尾：触发结束事件 + 返回结果
    # -------------------------------------------------------------------------
    # 所有 run() 的返回路径（成功/失败/异常）都通过此方法统一收尾，
    # 确保每次运行都有 run_end 事件和日志。
    # -------------------------------------------------------------------------
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

    def _finish_cancelled_run(
        self,
        hooks: BaseRunnerHooks | None,
        agent: BaseAgent,
        started_at: float,
        session_id: str | None,
        steps: int,
        tool_events: list[ToolCallEvent],
        reason: str,
    ) -> AgentRunResult:
        if self._checkpoint:
            self._checkpoint.clear(session_id)
        return self._finish_run(
            hooks,
            agent,
            self._build_result(
                answer=f"任务已取消：{reason}",
                success=False,
                steps=steps,
                tool_events=tool_events,
                error="cancelled",
            ),
            started_at,
            session_id,
        )

    def _raise_if_cancelled(
        self,
        cancellation_token: CancellationToken | None,
    ) -> None:
        if cancellation_token is not None:
            cancellation_token.raise_if_cancelled()

    # -------------------------------------------------------------------------
    # 构造标准化的运行结果结构体
    # -------------------------------------------------------------------------
    # 将分散的返回值字段打包为 AgentRunResult 字典，统一调用方的消费格式。
    # -------------------------------------------------------------------------
    def _build_result(
        self,
        answer: str,
        success: bool,
        steps: int,
        tool_events: list[ToolCallEvent],
        error: str | None,
        response_id: str | None = None,
    ) -> AgentRunResult:
        result: AgentRunResult = {
            "answer": answer,
            "success": success,
            "steps": steps,
            "tool_events": tool_events,
            "error": error,
        }
        if response_id is not None:
            result["response_id"] = response_id
        return result

    # -------------------------------------------------------------------------
    # 解析 Agent 可用工具列表
    # -------------------------------------------------------------------------
    # 如果配置了 tool_registry 且 Agent 声明支持工具调用，
    # 则返回 OpenAI function calling 格式的工具定义列表；否则返回空列表。
    # 空列表表示本次运行不向 LLM 传递任何工具。
    # -------------------------------------------------------------------------
    def _resolve_tools(
        self,
        agent: BaseAgent,
        tool_registry: ToolRegistry | None,
    ) -> list[dict[str, Any]]:
        if tool_registry and agent.supports_tools():
            return tool_registry.get_openai_tools()
        return []

    def _resolve_tool_scope(
        self,
        agent: BaseAgent,
        tool_registry: Any | None,
        history: list[ChatMessage],
        resume_checkpoint: Checkpoint | None = None,
    ) -> tuple[list[dict[str, Any]], Any | None]:
        if not tool_registry or not agent.supports_tools():
            return [], tool_registry
        if self.tool_selector is None:
            return tool_registry.get_openai_tools(), tool_registry

        catalog = ToolCatalog.from_registry(tool_registry)
        required_tools = [
            record.tool_name
            for record in (resume_checkpoint.tool_calls if resume_checkpoint else [])
        ]
        selection = self.tool_selector.select(
            catalog,
            ToolSelectionRequest(
                query=self._tool_selection_query(history),
                history=history,
                required_tools=required_tools,
            ),
        )
        scoped_registry = ScopedToolRegistryView(
            tool_registry,
            selection.selected_names,
            catalog=catalog,
        )
        return scoped_registry.get_openai_tools(), scoped_registry

    def _tool_selection_query(self, history: list[ChatMessage]) -> str:
        for message in reversed(history):
            if message.get("role") == "user":
                return message.get("content", "")
        return ""

    # -------------------------------------------------------------------------
    # 启动追踪 Span
    # -------------------------------------------------------------------------
    # 如果启用了分布式追踪，创建 AgentSpan 并记录 run_start 事件，
    # 用于在 Jaeger/Zipkin 等系统中可视化完整的调用链路。
    # -------------------------------------------------------------------------
    def _start_run_span(
        self,
        tracer: Any,
        agent: BaseAgent,
    ) -> AgentSpan | None:
        span = AgentSpan(tracer) if tracer else None
        if span:
            span.start_run_span(agent.name, agent.model, self.max_steps)
        return span

    # -------------------------------------------------------------------------
    # 技能快速通道：在调用 LLM 之前拦截 /skill 命令
    # -------------------------------------------------------------------------
    # 如果用户最后一条消息以 / 开头且匹配已知技能，直接调度执行并返回结果，
    # 完全跳过 LLM 调用，大幅降低技能类命令的延迟和成本。
    #
    # 返回值：
    #   (True, result)  — 技能已匹配并执行，result 为技能输出
    #   (False, None)   — 不是技能命令，需走正常 LLM 流程
    # -------------------------------------------------------------------------
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

    # -------------------------------------------------------------------------
    # LLM 调用前置中间件
    # -------------------------------------------------------------------------
    # 在执行 LLM 调用前，允许中间件检查或修改输入内容。
    # 中间件可以：
    #   - 注入系统提示词
    #   - 过滤敏感内容
    #   - 添加上下文信息
    #   - 抛出 MiddlewareAbort 中止本次 LLM 调用
    # -------------------------------------------------------------------------
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

    def _uses_openai_previous_response(
        self,
        provider_state: ProviderContextState | None,
    ) -> bool:
        return (
            provider_state is not None
            and provider_state.provider == "openai"
            and provider_state.provider_mode == "openai_previous_response"
        )

    def _input_for_previous_response(
        self,
        current_input: list[dict] | str,
        previous_response_id: str | None,
    ) -> list[dict] | str:
        if previous_response_id is None or not isinstance(current_input, list):
            return current_input
        if not self._is_chat_message_history(current_input):
            return current_input

        system_messages = [
            item for item in current_input
            if item.get("role") == "system"
        ]
        latest_user_message = next(
            (
                item for item in reversed(current_input)
                if item.get("role") == "user"
            ),
            None,
        )
        if latest_user_message is None:
            return current_input
        return [*system_messages, latest_user_message]

    def _is_chat_message_history(self, current_input: list[dict]) -> bool:
        return all(
            isinstance(item, dict)
            and item.get("role") in {"system", "user", "assistant"}
            and "content" in item
            for item in current_input
        )

    # -------------------------------------------------------------------------
    # 带弹性机制的 LLM 调用
    # -------------------------------------------------------------------------
    # 本方法是 LLM 调用的核心防护层，按序执行以下保障措施：
    #
    #   1. 令牌桶限流  —— acquire() 阻塞等待令牌，防止超过 API 频率限制
    #   2. 熔断器检查  —— 如果 LLM 连续失败导致熔断器打开，直接拒绝调用
    #   3. 超时控制    —— with_timeout() 包装，防止 LLM 长时间无响应
    #   4. 指数退避重试 —— 超时后使用 tenacity 库自动重试（最多 max_retries 次）
    #
    # 错误处理策略：
    #   - 超时：记录日志 → 记录熔断失败 → 指数退避重试 → 仍失败则向上抛
    #   - 限流：记录日志 → 记录熔断失败 → 直接向上抛（不重试，让上层返回友好提示）
    #   - 其他异常：记录日志 → 记录熔断失败 → 直接向上抛
    #
    # 注意：用户可读的错误消息映射在 run() 方法中处理，本方法聚焦传输层弹性。
    # -------------------------------------------------------------------------
    def _call_llm_with_resilience(
        self,
        agent: BaseAgent,
        current_input: list[dict] | str,
        tools: list[dict[str, Any]],
        step: int,
        session_id: str | None,
        span: AgentSpan | None,
        previous_response_id: str | None = None,
        store_response: bool = False,
    ) -> Any:
        """Call the model with rate limiting, timeout, retry, and circuit breaker.

        User-facing error mapping stays in run(), so this method can focus on
        transport and resilience mechanics while preserving the old result
        messages for callers.
        """
        # ---- 第 1 层：令牌桶限流 ----
        # 阻塞等待获取令牌，超时 5s；如果令牌桶耗尽会在 run() 中捕获 RateLimitError
        if self.rate_limiter:
            self.rate_limiter.acquire(timeout=5.0)

        # ---- 第 2 层：熔断器前置检查 ----
        # 如果 LLM 熔断器已打开（之前连续失败），直接拒绝调用，快速失败
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

        # ---- 构建 LLM 调用闭包 ----
        # 使用闭包包装以便重试逻辑可以重复调用
        def llm_call():
            kwargs: dict[str, Any] = {
                "model": agent.model,
                "input": current_input,
                "tools": tools if tools else None,  # None 表示不传 tools 参数
            }
            if previous_response_id is not None:
                kwargs["previous_response_id"] = previous_response_id
            if store_response:
                kwargs["store"] = True
            return self.client.responses.create(**kwargs)

        # ---- 第 3 层：超时控制 + 第 4 层：指数退避重试 ----
        try:
            response = with_timeout(llm_call, self.llm_timeout)
        except ToolTimeoutError:
            # 超时日志，包含超时秒数便于排查
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
            # 通知熔断器：记录一次失败
            if self.llm_circuit_breaker:
                self.llm_circuit_breaker.record_failure()
            # 如果配置了重试，使用 tenacity 指数退避重试
            if self.max_retries > 1:
                from tenacity import retry, stop_after_attempt, wait_exponential

                retry_decorator = retry(
                    stop=stop_after_attempt(self.max_retries),
                    wait=wait_exponential(multiplier=1, min=1, max=10),
                    reraise=True,  # 重试耗尽后重新抛出原始异常
                )
                response = retry_decorator(llm_call)()
            else:
                raise
        except RateLimitError as e:
            # 限流异常：不重试，直接向上抛（run() 中返回友好错误消息）
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
            # 未知异常：记录完整堆栈，不重试
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

        # ---- 调用成功：通知熔断器 + 结束当前 Span ----
        if self.llm_circuit_breaker:
            self.llm_circuit_breaker.record_success()

        if span:
            span.end_current_span()

        return response

    # -------------------------------------------------------------------------
    # 获取或创建工具级别的熔断器（懒初始化）
    # -------------------------------------------------------------------------
    # 每个工具拥有独立的熔断器，某个工具连续失败不会影响其他工具的正常调用。
    # 熔断器按 tool_name 作为 key 存储在内部字典中。
    # -------------------------------------------------------------------------
    def _get_tool_circuit_breaker(self, tool_name: str) -> CircuitBreaker:
        cb = self._circuit_breakers.get(tool_name)
        if cb is None:
            cb = CircuitBreaker(name=tool_name)
            self._circuit_breakers[tool_name] = cb
        return cb

    # -------------------------------------------------------------------------
    # 执行单个工具调用（核心方法）
    # -------------------------------------------------------------------------
    # 完整的工具执行流水线：
    #
    #   1. 解析 JSON 参数（两次：预览用 + 实际用，分别处理解析失败）
    #   2. 启动追踪 Span → 触发 on_tool_start 钩子
    #   3. 中间件检查（before_tool）→ 可能被 MiddlewareAbort 中止
    #   4. 熔断器状态检查 → 打开则快速失败
    #   5. 实际调用工具（同步 or 异步）→ 带 10s 超时
    #   6. 成功：记录日志 → 触发 on_tool_end 钩子 → 返回 function_call_output
    #   7. 失败：通过 finish_error() 统一处理错误事件和返回格式
    #
    # 工具调用错误分类：
    #   - invalid_arguments      JSON 解析失败
    #   - middleware_abort        中间件主动中止
    #   - circuit_breaker_open   熔断器打开
    #   - timeout                执行超时（10s）
    #   - exception              运行时异常
    # -------------------------------------------------------------------------
    def _execute_tool_call(
        self,
        agent: BaseAgent,
        tool_registry: ToolRegistry,
        hooks: BaseRunnerHooks | None,
        span: AgentSpan | None,
        collected_events: list[ToolCallEvent],
        step: int,
        fc: Any,  # function_call 对象，需有 name, call_id, arguments 属性
    ) -> FunctionCallOutput:
        """Execute one function_call item and emit the matching tool events.

        The final AgentRunResult keeps only success/error tool events. The
        start event is still sent to hooks so streaming clients can render a
        tool-start notification without changing historical result payloads.
        """
        tool_name = fc.name
        call_id = fc.call_id

        # ---- 第 1 步：预览解析参数（仅用于日志和追踪） ----
        try:
            preview_args = json.loads(fc.arguments)
        except json.JSONDecodeError:
            preview_args = {}

        # ---- 第 2 步：启动追踪 Span + 触发 on_tool_start 钩子 ----
        if span:
            span.start_tool_span(tool_name, preview_args)

        if hooks:
            hooks.on_tool_start({
                "agent_name": agent.name,
                "step": step,
                "call_id": call_id,
                "tool_name": tool_name,
                "arguments": preview_args,
                "status": "start",
            })

        # -----------------------------------------------------------------
        # 内部辅助函数：统一处理所有工具调用失败场景
        # -----------------------------------------------------------------
        # 无论何种失败原因，都执行相同的收尾流程：
        #   1. 结束追踪 Span（可选带 error）
        #   2. 记录警告日志
        #   3. 构造 error 状态的 ToolCallEvent 并追加到 collected_events
        #   4. 通知 Agent 和钩子
        #   5. 返回 function_call_output 格式的结果（供 LLM 理解错误）
        # -----------------------------------------------------------------
        def finish_error(
            result: str,           # 返回给 LLM 的错误描述文本
            event_error: str,      # 事件中的错误摘要
            arguments: dict[str, Any],  # 工具参数
            status: str,           # 错误子类型标识
            error: Exception | None = None,  # 原始异常（用于 Span 记录）
        ) -> FunctionCallOutput:
            if span:
                if error:
                    span.end_current_span(error=error)
                else:
                    span.end_current_span()
            logger.warning(
                "runner event=tool_error agent=%s step=%s tool=%s "
                "status=%s error_type=%s",
                agent.name,
                step,
                tool_name,
                status,
                type(error).__name__ if error else status,
            )
            tool_event: ToolCallEvent = {
                "agent_name": agent.name,
                "step": step,
                "call_id": call_id,
                "tool_name": tool_name,
                "arguments": arguments,
                "status": "error",
                "error": event_error,
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

        # ---- 第 3 步：正式解析参数 ----
        # 如果解析失败，提前返回错误（不会进入中间件和熔断器检查）
        try:
            tool_args = json.loads(fc.arguments)
        except json.JSONDecodeError as e:
            return finish_error(
                result="工具参数解析失败。",
                event_error="工具参数解析失败。",
                arguments={},
                status="invalid_arguments",
                error=e,
            )

        # ---- 第 4 步：中间件检查 ----
        # 构造工具上下文并传递给中间件；中间件可中止执行
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
            return finish_error(
                result=e.message,
                event_error=e.message,
                arguments=tool_args,
                status="middleware_abort",
                error=e,
            )

        # ---- 第 5 步：获取工具级熔断器 ----
        cb = self._get_tool_circuit_breaker(tool_name)

        # ---- 构建工具调用闭包 ----
        # 根据工具注册类型自动选择同步或异步调用方式
        def tool_call() -> str:
            if tool_registry.is_async(tool_name):
                # 异步工具：通过 asyncio.run() 在同步上下文中执行
                return asyncio.run(
                    tool_registry.call_async(tool_name, **tool_args)
                )
            return tool_registry.call(tool_name, **tool_args)

        # ---- 第 6 步：带熔断器和超时的工具调用 ----
        try:
            # 熔断器前置检查：如果已打开则直接拒绝
            if cb.state == CircuitBreaker.OPEN:
                raise CircuitBreakerOpenError(
                    f"Circuit breaker open for tool: {tool_name}"
                )
            # cb.call() 会自动记录成功/失败，影响熔断器状态
            result = cb.call(with_timeout, tool_call, 10.0)
        except CircuitBreakerOpenError as e:
            result = f"工具暂时不可用（熔断器打开）：{e}"
            return finish_error(
                result=result,
                event_error=str(e),
                arguments=tool_args,
                status="circuit_breaker_open",
                error=e,
            )
        except ToolTimeoutError as e:
            result = f"工具执行超时（10s）：{tool_name}"
            return finish_error(
                result=result,
                event_error=result,
                arguments=tool_args,
                status="timeout",
                error=e,
            )
        except Exception as e:
            result = f"工具执行失败：{e}"
            return finish_error(
                result=result,
                event_error=str(e),
                arguments=tool_args,
                status="exception",
                error=e,
            )

        # ---- 第 7 步：工具执行成功 ----
        if span:
            span.end_current_span()
        logger.info(
            "runner event=tool_success agent=%s step=%s tool=%s "
            "result_chars=%s",
            agent.name,
            step,
            tool_name,
            len(str(result)),  # 记录结果字符数，便于评估返回数据量
        )
        # 构造成功状态的事件
        tool_event: ToolCallEvent = {
            "agent_name": agent.name,
            "step": step,
            "call_id": call_id,
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

    # -------------------------------------------------------------------------
    # 批量执行工具记录（用于检查点恢复场景）
    # -------------------------------------------------------------------------
    # 遍历 tool_records 列表，逐条执行或跳过已完成记录。
    #
    # 执行策略（按记录状态分流）：
    #   1. 状态为 succeeded/failed 且 output 非空 → 已完成，直接复用输出
    #   2. 状态为 running/unknown 且副作用策略为 non_idempotent →
    #      无法确认工具是否已执行，为防止重复执行副作用，暂停恢复，
    #      返回 blocked_record 让上层提示用户手动处理
    #   3. 其他情况 → 标记为 running，执行工具调用
    #
    # 每执行完一条记录就保存检查点（渐进式持久化），
    # 确保即使批量执行中途崩溃，已完成的工具结果也不会丢失。
    #
    # 返回值：
    #   (function_outputs, None)            — 全部执行完成
    #   (function_outputs, blocked_record)  — 遇到不可重放的记录，暂停执行
    # -------------------------------------------------------------------------
    def _execute_tool_records(
        self,
        agent: BaseAgent,
        tool_registry: ToolRegistry,
        hooks: BaseRunnerHooks | None,
        span: AgentSpan | None,
        collected_events: list[ToolCallEvent],
        step: int,
        current_input: list[dict[str, Any]] | str,
        tool_records: list[ToolExecutionRecord],
        session_id: str | None,
        run_id: str,
        cancellation_token: CancellationToken | None = None,
    ) -> tuple[list[FunctionCallOutput], ToolExecutionRecord | None]:
        """Execute pending tool records and checkpoint every stable result."""
        function_outputs: list[FunctionCallOutput] = []
        ck = self._checkpoint

        for record in tool_records:
            self._raise_if_cancelled(cancellation_token)

            # ---- 情况 1：已完成记录，直接复用 ----
            if CheckpointOrchestrator.is_record_complete(record):
                function_outputs.append(
                    CheckpointOrchestrator.record_to_function_output(record)
                )
                continue

            # ---- 情况 2：非幂等工具状态未知，暂停恢复 ----
            if (
                record.status in {"running", "unknown"}
                and record.side_effect_policy == "non_idempotent"
            ):
                if ck:
                    ck.save(
                        session_id=session_id,
                        step=step,
                        phase="tool_partial_done",
                        current_input=current_input,
                        agent=agent,
                        run_id=run_id,
                        tool_calls=tool_records,
                        function_outputs=function_outputs,
                        error="non_idempotent_tool_state_unknown",
                    )
                    logger.debug(
                        "runner event=checkpoint_save session_id=%s step=%s "
                        "phase=tool_partial_done tool_calls=%s function_outputs=%s",
                        session_id, step, len(tool_records), len(function_outputs),
                    )
                return function_outputs, record

            # ---- 情况 3：执行工具 ----
            record.status = "running"
            if ck:
                ck.save(
                    session_id=session_id,
                    step=step,
                    phase="tool_partial_done",
                    current_input=current_input,
                    agent=agent,
                    run_id=run_id,
                    tool_calls=tool_records,
                    function_outputs=function_outputs,
                )
                logger.debug(
                    "runner event=checkpoint_save session_id=%s step=%s "
                    "phase=tool_partial_done tool_calls=%s function_outputs=%s",
                    session_id, step, len(tool_records), len(function_outputs),
                )

            # 将 ToolExecutionRecord 转为 SimpleNamespace 以兼容 _execute_tool_call
            fc = SimpleNamespace(
                type="function_call",
                name=record.tool_name,
                arguments=json.dumps(record.arguments, ensure_ascii=False),
                call_id=record.call_id,
            )
            event_count = len(collected_events)
            output = self._execute_tool_call(
                agent=agent,
                tool_registry=tool_registry,
                hooks=hooks,
                span=span,
                collected_events=collected_events,
                step=step,
                fc=fc,
            )
            function_outputs.append(output)
            record.output = output["output"]

            # 根据最新事件判断执行结果
            latest_event = (
                collected_events[-1]
                if len(collected_events) > event_count
                else None
            )
            if latest_event and latest_event.get("status") == "error":
                record.status = "failed"
                record.error = latest_event.get("error")
            else:
                record.status = "succeeded"
                record.error = None

            # ---- 判断整体阶段：全部完成 vs 部分完成 ----
            phase: CheckpointPhase = (
                "tool_output_ready"
                if all(
                    CheckpointOrchestrator.is_record_complete(item)
                    for item in tool_records
                )
                else "tool_partial_done"
            )
            next_llm_input: list[dict[str, Any]] | str = (
                function_outputs if phase == "tool_output_ready" else current_input
            )
            if ck:
                ck.save(
                    session_id=session_id,
                    step=step,
                    phase=phase,
                    current_input=next_llm_input,
                    agent=agent,
                    run_id=run_id,
                    tool_calls=tool_records,
                    function_outputs=function_outputs,
                )
                logger.debug(
                    "runner event=checkpoint_save session_id=%s step=%s phase=%s "
                    "tool_calls=%s function_outputs=%s",
                    session_id, step, phase, len(tool_records), len(function_outputs),
                )
            self._raise_if_cancelled(cancellation_token)

        return function_outputs, None

    # =========================================================================
    # run() —— AgentRunner 的主入口方法
    # =========================================================================
    # 执行一次完整的 Agent 回合，协调所有子组件完成以下流程：
    #
    # ┌─────────────────────────────────────────────────────────────────┐
    # │                      run() 主流程                               │
    # ├─────────────────────────────────────────────────────────────────┤
    # │  1. 初始化阶段                                                  │
    # │     - 确定有效钩子（参数传入 > 构造传入）                          │
    # │     - 初始化追踪器 + 生成 run_id                                 │
    # │     - 触发 on_run_start 钩子                                     │
    # ├─────────────────────────────────────────────────────────────────┤
    # │  2. 检查点恢复（如果有 resume_checkpoint）                        │
    # │     - 恢复 Agent 状态和工具事件历史                               │
    # │     - 根据 phase 决定从哪一步继续                                 │
    # ├─────────────────────────────────────────────────────────────────┤
    # │  3. 技能快速通道（仅非恢复模式）                                   │
    # │     - 检查是否为 /skill 命令 → 直接调度并返回                     │
    # ├─────────────────────────────────────────────────────────────────┤
    # │  4. 主循环（step = start_step .. max_steps）                     │
    # │     │                                                           │
    # │     ├─ 4a. 工具恢复（如果有待执行的 resume_tool_records）          │
    # │     ├─ 4b. 中间件处理（before_llm）                              │
    # │     ├─ 4c. 保存检查点（before_llm）                              │
    # │     ├─ 4d. LLM 调用（带弹性防护：超时/重试/熔断/限流）             │
    # │     ├─ 4e. 解析 LLM 响应 → 文本答案 or 工具调用请求              │
    # │     └─ 4f. 执行工具调用 → 输出喂回下一步 LLM                      │
    # ├─────────────────────────────────────────────────────────────────┤
    # │  5. 终态处理                                                    │
    # │     - 达到 max_steps → max_steps_exceeded 错误                   │
    # │     - 未捕获异常 → 记录 + 触发 run_end + 重新抛出                 │
    # │     - 所有终态：清除检查点                                       │
    # └─────────────────────────────────────────────────────────────────┘
    #
    # 参数：
    #   agent              - 要运行的 Agent 实例
    #   history            - 对话历史记录
    #   tool_registry      - 工具注册中心（可选）
    #   hooks              - 钩子（覆盖构造时传入的 hooks）
    #   session_id         - 会话 ID（用于检查点关联）
    #   resume_checkpoint  - 恢复检查点（提供则从断点继续执行）
    #
    # 返回值：AgentRunResult 包含 answer/success/steps/tool_events/error
    # =========================================================================
    def run(
        self,
        agent: BaseAgent,
        history: list[ChatMessage],
        tool_registry: ToolRegistry | None = None,
        hooks: BaseRunnerHooks | None = None,
        session_id: str | None = None,
        resume_checkpoint: Checkpoint | None = None,
        provider_state: ProviderContextState | None = None,
        cancellation_token: CancellationToken | None = None,
    ) -> AgentRunResult:
        """Execute one agent turn.

        Flow:
        1. emit run start hooks and initialize tracing;
        2. short-circuit slash skills when present;
        3. repeat LLM call -> optional tool calls until a final answer appears;
        4. save checkpoints after tool rounds and clear them on any terminal
           result.
        """
        # =================================================================
        # 阶段 1：初始化
        # =================================================================
        # 钩子优先级：方法参数传入的 hooks > 构造时传入的 hooks
        effective_hooks = hooks if hooks is not None else self.hooks
        tracer = get_tracer() if self.enable_tracing else None
        run_started_at = time.perf_counter()  # 使用高精度计时器
        last_step = 0  # 记录最后执行的步数，异常处理时使用

        # 触发 on_run_start 钩子，通知所有观察者运行已开始
        start_event: RunStartEvent = {
            "agent_name": agent.name,
            "history_length": len(history),
            "model": agent.model,
        }
        if effective_hooks:
            effective_hooks.on_run_start(start_event)

        # ---- 初始化循环变量 ----
        current_input: list[dict] | str = history     # LLM 输入，每步迭代会更新
        collected_events: list[ToolCallEvent] = []     # 收集所有工具调用事件（成功+失败）
        start_step = 1                                 # 起始步数，恢复模式可能 > 1
        run_id = str(uuid4())                          # 本次运行的唯一标识
        resume_tool_records: list[ToolExecutionRecord] | None = None  # 待恢复工具记录
        use_openai_previous_response = self._uses_openai_previous_response(
            provider_state
        )
        previous_response_id = (
            provider_state.last_response_id
            if use_openai_previous_response and provider_state is not None
            else None
        )
        last_response_id: str | None = None

        # =================================================================
        # 阶段 2：检查点恢复
        # =================================================================
        # 如果提供了 resume_checkpoint，根据 phase 恢复状态：
        #   tool_requested / tool_partial_done → 先执行工具恢复再继续
        #   tool_output_ready → 跳过工具执行，直接用输出作为 LLM 输入
        #   completed / failed → 设为 max_steps+1，跳过主循环
        # =================================================================
        if resume_checkpoint is not None and self._checkpoint is not None:
            ctx: ResumeContext = self._checkpoint.prepare_resume(
                resume_checkpoint, agent, self.max_steps
            )
            run_id = ctx.run_id or run_id
            collected_events = ctx.collected_events
            current_input = ctx.current_input
            start_step = ctx.start_step
            resume_tool_records = ctx.resume_tool_records
        elif resume_checkpoint is not None:
            # Backward compat: raw checkpoint without orchestrator
            run_id = resume_checkpoint.run_id or run_id
            agent.restore_state(resume_checkpoint.agent_state)
            if resume_checkpoint.phase in {"completed", "failed"}:
                start_step = self.max_steps + 1

        # ---- 解析工具列表 + 记录运行开始日志 ----
        tools, effective_tool_registry_for_run = self._resolve_tool_scope(
            agent,
            tool_registry,
            history,
            resume_checkpoint,
        )
        logger.info(
            "runner event=run_start agent=%s session_id=%s model=%s "
            "history_length=%s max_steps=%s tools_count=%s resume=%s "
            "start_step=%s",
            agent.name,
            session_id or "",
            agent.model,
            len(history),
            self.max_steps,
            len(tools),
            resume_checkpoint is not None,
            start_step,
        )
        # 追踪由 Runner 管理，钩子只需作为轻量观察者，无需实现追踪适配器
        span = self._start_run_span(tracer, agent)

        if cancellation_token is not None and cancellation_token.is_cancelled():
            if span:
                span.end_all()
            return self._finish_cancelled_run(
                effective_hooks,
                agent,
                run_started_at,
                session_id,
                last_step,
                collected_events,
                cancellation_token.reason,
            )

        # =================================================================
        # 阶段 3：技能快速通道（仅非恢复模式）
        # =================================================================
        # 从检查点恢复时不走技能通道（恢复的是已在进行中的正常 LLM 流程）
        # =================================================================
        invoked, skill_result = (
            (False, None)
            if resume_checkpoint is not None
            else self._try_invoke_skill(agent, history)
        )
        if invoked:
            if span:
                span.end_all()
            if self._checkpoint:
                self._checkpoint.clear(session_id)
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

        # =================================================================
        # 阶段 4：主循环 —— LLM 推理 ⇄ 工具调用交替进行
        # =================================================================
        # 可能的退出路径：
        #   a. LLM 返回纯文本（无 function_call）→ 成功返回答案
        #   b. LLM 请求工具但无 tool_registry → 返回配置错误
        #   c. 工具恢复遇到不可重放记录 → 返回暂停提示
        #   d. LLM 调用弹性防护异常 → 返回中文错误消息
        #   e. 达到 max_steps → 循环结束后返回 max_steps_exceeded
        # =================================================================
        try:
            for step in range(start_step, self.max_steps + 1):
                last_step = step
                self._raise_if_cancelled(cancellation_token)
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

                # ---------------------------------------------------------
                # 4a. 工具恢复路径（从检查点恢复时，先完成未执行的工具调用）
                # ---------------------------------------------------------
                if resume_tool_records is not None:
                    if effective_tool_registry_for_run is None:
                        if span:
                            span.end_all()
                        return self._finish_run(
                            effective_hooks,
                            agent,
                            self._build_result(
                                answer="恢复需要工具注册中心，但当前未配置。",
                                success=False,
                                steps=step,
                                tool_events=collected_events,
                                error="missing_tool_registry",
                            ),
                            run_started_at,
                            session_id,
                        )

                    next_input, blocked_record = self._execute_tool_records(
                        agent=agent,
                        tool_registry=effective_tool_registry_for_run,
                        hooks=effective_hooks,
                        span=span,
                        collected_events=collected_events,
                        step=step,
                        current_input=current_input,
                        tool_records=resume_tool_records,
                        session_id=session_id,
                        run_id=run_id,
                        cancellation_token=cancellation_token,
                    )
                    resume_tool_records = None
                    if blocked_record is not None:
                        if span:
                            span.end_all()
                        return self._finish_run(
                            effective_hooks,
                            agent,
                            self._build_result(
                                answer=(
                                    "检测到工具可能已经执行，但结果未确认。"
                                    f"工具 {blocked_record.tool_name} 可能有副作用，"
                                    "已暂停自动恢复以避免重复调用。"
                                ),
                                success=False,
                                steps=step,
                                tool_events=collected_events,
                                error="tool_requires_manual_resume",
                            ),
                            run_started_at,
                            session_id,
                        )

                    current_input = next_input
                    continue

                # ---------------------------------------------------------
                # 4b. 触发 on_llm_start 钩子
                # ---------------------------------------------------------
                if effective_hooks:
                    effective_hooks.on_llm_start({
                        "agent_name": agent.name,
                        "step": step,
                        "model": agent.model,
                        "input_length": len(current_input),
                    })

                # ---------------------------------------------------------
                # 4c. LLM 调用前置中间件（可修改输入或中止调用）
                # ---------------------------------------------------------
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
                    if self._checkpoint:
                        self._checkpoint.clear(session_id)
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

                self._raise_if_cancelled(cancellation_token)
                llm_input = self._input_for_previous_response(
                    current_input,
                    previous_response_id
                    if use_openai_previous_response
                    else None,
                )

                # ---------------------------------------------------------
                # 4d. 保存检查点（before_llm 阶段）
                # ---------------------------------------------------------
                if self._checkpoint:
                    self._checkpoint.save(
                        session_id=session_id,
                        step=step,
                        phase="before_llm",
                        current_input=llm_input,
                        agent=agent,
                        run_id=run_id,
                    )
                    logger.debug(
                        "runner event=checkpoint_save session_id=%s step=%s "
                        "phase=before_llm",
                        session_id, step,
                    )

                if span:
                    span.start_llm_span(len(llm_input))

                # ---------------------------------------------------------
                # 4e. LLM 调用（带超时/重试/熔断/限流弹性防护）
                # ---------------------------------------------------------
                self._raise_if_cancelled(cancellation_token)
                try:
                    response = self._call_llm_with_resilience(
                        agent=agent,
                        current_input=llm_input,
                        tools=tools,
                        step=step,
                        session_id=session_id,
                        span=span,
                        previous_response_id=(
                            previous_response_id
                            if use_openai_previous_response
                            else None
                        ),
                        store_response=use_openai_previous_response,
                    )
                except CircuitBreakerOpenError:
                    if span:
                        span.end_current_span()
                        span.end_all()
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

                # ---------------------------------------------------------
                # 4f. LLM 调用成功 → 触发 on_llm_end 钩子
                # ---------------------------------------------------------
                if effective_hooks:
                    effective_hooks.on_llm_end({
                        "agent_name": agent.name,
                        "step": step,
                        "output_items_count": len(response.output),
                    })

                response_id = getattr(response, "id", None)
                if isinstance(response_id, str) and response_id:
                    last_response_id = response_id
                    if use_openai_previous_response:
                        previous_response_id = response_id

                self._raise_if_cancelled(cancellation_token)
                # ---------------------------------------------------------
                # 4g. 解析 LLM 响应：文本答案 vs 工具调用请求
                # ---------------------------------------------------------
                function_calls = [
                    item for item in response.output
                    if item.type == "function_call"
                ]

                if not function_calls:
                    # LLM 返回了最终文本答案 → 成功退出
                    if span:
                        span.end_all()
                    if self._checkpoint:
                        self._checkpoint.clear(session_id)
                    return self._finish_run(
                        effective_hooks,
                        agent,
                        self._build_result(
                            answer=response.output_text or "模型没有返回文本结果。",
                            success=True,
                            steps=step,
                            tool_events=collected_events,
                            error=None,
                            response_id=last_response_id,
                        ),
                        run_started_at,
                        session_id,
                    )

                # LLM 请求了工具调用，但未配置工具注册中心 → 返回配置错误
                if effective_tool_registry_for_run is None:
                    if span:
                        span.end_all()
                    if self._checkpoint:
                        self._checkpoint.clear(session_id)
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

                # ---------------------------------------------------------
                # 4h. 构建工具执行记录 + 保存检查点（tool_requested）
                # ---------------------------------------------------------
                tool_records = CheckpointOrchestrator.build_tool_records(
                    function_calls=function_calls,
                    tool_registry=effective_tool_registry_for_run,
                    run_id=run_id,
                )
                if self._checkpoint:
                    self._checkpoint.save(
                        session_id=session_id,
                        step=step,
                        phase="tool_requested",
                        current_input=current_input,
                        agent=agent,
                        run_id=run_id,
                        tool_calls=tool_records,
                    )
                    logger.debug(
                        "runner event=checkpoint_save session_id=%s step=%s "
                        "phase=tool_requested tool_calls=%s",
                        session_id, step, len(tool_records),
                    )

                # ---------------------------------------------------------
                # 4i. 批量执行工具调用 → 输出作为下一步 LLM 输入
                # ---------------------------------------------------------
                next_input, blocked_record = self._execute_tool_records(
                    agent=agent,
                    tool_registry=effective_tool_registry_for_run,
                    hooks=effective_hooks,
                    span=span,
                    collected_events=collected_events,
                    step=step,
                    current_input=current_input,
                    tool_records=tool_records,
                    session_id=session_id,
                    run_id=run_id,
                    cancellation_token=cancellation_token,
                )
                if blocked_record is not None:
                    if span:
                        span.end_all()
                    return self._finish_run(
                        effective_hooks,
                        agent,
                        self._build_result(
                            answer=(
                                "检测到工具可能已经执行，但结果未确认。"
                                f"工具 {blocked_record.tool_name} 可能有副作用，"
                                "已暂停自动恢复以避免重复调用。"
                            ),
                            success=False,
                            steps=step,
                            tool_events=collected_events,
                            error="tool_requires_manual_resume",
                        ),
                        run_started_at,
                        session_id,
                    )
                current_input = next_input

            # =================================================================
            # 阶段 5a：达到最大步数 —— 安全阀，防止无限循环
            # =================================================================
            if span:
                span.end_all()
            if self._checkpoint:
                self._checkpoint.clear(session_id)
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
        except RunnerCancelledError as e:
            if span:
                span.end_all()
            logger.info(
                "runner event=run_cancelled agent=%s session_id=%s step=%s",
                agent.name,
                session_id or "",
                last_step,
            )
            return self._finish_cancelled_run(
                effective_hooks,
                agent,
                run_started_at,
                session_id,
                last_step,
                collected_events,
                e.reason,
            )
        # =================================================================
        # 阶段 5b：未捕获异常 —— 最后防线
        # =================================================================
        # 所有未被内层显式处理的异常在此兜底：
        # 记录完整堆栈 + 触发 run_end 事件 + 重新抛出异常
        # =================================================================
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
