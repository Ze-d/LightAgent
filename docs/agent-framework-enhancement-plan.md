# MyAgent 框架功能扩展计划 —— 面向 Agent 开发面试

## Context

MyAgent 是一个 Python Agent 开发框架，已实现核心组件：
- Agent 体系：BaseAgent → ChatAgent → ToolAwareAgent
- AgentRunner 执行引擎、ToolRegistry、Hooks、Middleware
- InMemorySessionManager、EventChannel (SSE)

**现有缺陷**：无记忆系统、无多 Agent 协作、无可观测性、安全层薄弱（calculator 用 eval）、无生产级韧性（超时/重试/限流/熔断）。

---

## 推荐扩展方向（按优先级）

### P0 —— 立即修复/实现

| 功能 | 状态 | 关键文件 |
|------|------|---------|
| **工具沙箱** | ✅ 已实现 (`app/tools/sandbox.py`) | `app/tools/builtin_tools.py` |
| **请求超时 + 重试** | ✅ 已实现 (`app/core/resilience.py`) | `app/core/runner.py` |
| **OpenTelemetry Tracing** | ✅ 已实现 (`app/core/tracing.py`) | `app/core/hooks.py` |

### P1 —— 完善生产可用性

| 功能 | 状态 | 关键文件 |
|------|------|---------|
| **Pydantic 参数校验装饰器** | ✅ 已实现 (`app/tools/validator.py`) | 新建 `app/tools/validator.py` |
| **异步工具支持** | 🔲 待实现 | `app/core/runner.py` |
| **记忆摘要压缩** | ✅ 已实现 (`app/memory/summarizer.py`) | `app/memory/summarizer.py` |
| **输入过滤 Middleware** | ✅ 已实现 (`app/security/input_guard.py`) | `app/security/input_guard.py` |
| **Token 限流** | ✅ 已实现 (`app/core/rate_limiter.py`) | `app/core/rate_limiter.py` |
| **熔断器模式** | ✅ 已实现 (`app/core/resilience.py`) | `app/core/circuit_breaker.py` |
| **语义向量记忆 (RAG)** | 🔲 待实现 | `app/memory/vector_store.py` |

### P2 —— 高级特性

| 功能 | 价值 |
|------|------|
| 工具并行执行 | LLM 返回多个 function_call 时串行等待 |
| 多 Agent 协作协议 | 单 Agent 无法处理复杂任务分解 |
| 记忆分层 (Working/Episodic/Semantic) | 统一存储无法区分访问频率 |
| Prompt Injection 检测 | 被动过滤无法主动防御 |
| PII 脱敏 | 敏感信息泄露风险 |
| 慢工具报警 | 无性能监控 |

---

## 重点功能实现思路

### 1. 工具沙箱（安全 P0）

用 AST 静态分析替代 `eval()`：

```python
# app/tools/sandbox.py
class SafeEvaluator(ast.NodeVisitor):
    SAFE_FUNCTIONS = {"abs", "round", "min", "max", "pow", "floor", "ceil"}
    ALLOWED_OPS = {ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod}

    def visit_BinOp(self, node):
        # 只允许数学运算
        if type(node.op) not in self.ALLOWED_OPS:
            raise ValueError(f"Unsupported: {type(node.op)}")
        return super().visit_BinOp(node)
```

### 2. OpenTelemetry Tracing

在 `AgentRunner.run()` 中埋入 Span：

```python
with tracer.start_as_current_span("agent_run") as span:
    span.set_attribute("agent.name", agent.name)
    for step in range(1, max_steps + 1):
        with tracer.start_as_current_span(f"step_{step}"):
            # llm span → tool spans 父子关系
```

### 3. 熔断器（Resilience P1）

```python
class CircuitBreaker:
    states = {"closed", "open", "half_open"}
    # 失败 N 次 → open → 超时后 half_open → 成功则 closed
```

### 4. 记忆摘要压缩

```python
# 当 history 超过阈值，用 LLM 生成摘要，替换旧消息块
class MemorySummarizer:
    async def summarize(self, messages) -> str:
        # 调用 LLM 将 10 条消息压缩为 1 条摘要
```

---

## 面试核心亮点

| 维度 | 设计模式 | 可引申话题 |
|------|---------|-----------|
| 工具生态 | 装饰器、Strategy、ThreadPoolExecutor | GIL 规避、Python 并发模型 |
| 记忆系统 | RAG、Embedding、分层架构 | Mem0、向量数据库选型 |
| 多 Agent | Pub/Sub、拓扑排序、Supervisor | LangGraph、斯坦福 ChatDev |
| 可观测性 | OpenTelemetry、Prometheus | SLO/SLA、CNCF 全家桶 |
| 安全性 | AST 沙箱、Chain of Responsibility | OWASP、零信任 |
| 生产特性 | Token Bucket、Circuit Breaker | 微服务韧性、Hystrix |

---

## 验证方案

1. **安全修复**：验证 `calculator("1+1")` 正常返回，`calculator("os.system('rm')")` 被拦截
2. **Tracing**：用 Jaeger 验证一次请求的 Trace ID 贯穿 LLM 调用 → 工具执行 → 响应
3. **熔断**：连续触发工具失败 N 次后，后续调用直接被熔断拦截
4. **限流**：快速发送超过阈值的请求，验证返回 429 或优雅拒绝
5. **记忆摘要**：发送 20 条消息后，验证历史被压缩为摘要 + 最近消息

---

## 关键文件参考

- [runner.py](app/core/runner.py) — 执行引擎核心，所有扩展的集成点
- [tool_registry.py](app/core/tool_registry.py) — 工具注册与调用链路
- [middleware.py](app/core/middleware.py) — Middleware 鉴权链插入点
- [hooks.py](app/core/hooks.py) — 生命周期钩子，可观测性和记忆系统的旁路监听点
- [builtin_tools.py](app/tools/builtin_tools.py) — 内置工具实现
- [sandbox.py](app/tools/sandbox.py) — 工具参数沙箱校验（已替代 eval）
- [resilience.py](app/core/resilience.py) — 超时、重试、熔断器
- [tracing.py](app/core/tracing.py) — OpenTelemetry 链路追踪
- [rate_limiter.py](app/core/rate_limiter.py) — TokenBucket 限流
- [summarizer.py](app/memory/summarizer.py) — 记忆摘要压缩
- [input_guard.py](app/security/input_guard.py) — 输入安全过滤

*最后更新：2026/04/26*
