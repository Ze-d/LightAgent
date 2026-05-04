# MyAgent 框架功能扩展计划

## Context

MyAgent 是一个 Python Agent 运行时框架，已实现：

- Agent 体系：`BaseAgent` → `ChatAgent` → `ToolAwareAgent`
- 协议无关执行引擎：`AgentRunner`
- 本地工具注册、Pydantic 参数校验、异步工具支持
- MCP 工具接入
- A2A Server/Client/Task/Streaming/Agent Card/Tool Bridge
- Session、Memory、Checkpoint
- Hooks、Middleware、SSE
- OpenTelemetry、限流、超时、重试、熔断
- 输入安全过滤和工具沙箱

---

## 已完成能力

| 能力 | 状态 | 关键文件 |
|------|------|------|
| 工具沙箱 | 已实现 | `app/tools/sandbox.py` |
| Pydantic 工具参数校验 | 已实现 | `app/tools/validator.py` |
| 异步工具支持 | 已实现 | `app/core/tool_registry.py`, `app/core/runner.py` |
| 请求超时 + 重试 | 已实现 | `app/core/resilience.py`, `app/core/runner.py` |
| OpenTelemetry Tracing | 已实现 | `app/core/tracing.py` |
| Token 限流 | 已实现 | `app/core/rate_limiter.py` |
| 熔断器 | 已实现 | `app/core/resilience.py` |
| 输入过滤 Middleware | 已实现 | `app/security/input_guard.py` |
| 记忆摘要与文档记忆 | 已实现 | `app/memory/` |
| Checkpoint 恢复 | 已实现 | `app/core/checkpoint.py`, `app/core/runner.py` |
| MCP 工具接入 | 已实现 | `app/mcp/` |
| A2A 协议支持 | 已实现 | `app/a2a/` |

---

## A2A 实现结果

| 阶段 | 结果 |
|------|------|
| P0 | A2A 协议边界独立于 `AgentRunner` |
| P1 | A2A Server message/task MVP |
| P2 | Task 生命周期、取消、终态保护 |
| P3 | 统一事件 broker、`message:stream`、`tasks/{id}:subscribe` |
| P4 | 公开 Agent Card、认证扩展 Agent Card |
| P5 | A2A Client、远端 Agent 工具桥 |

详见：[A2A 协议支持说明](a2a.md)。

---

## 后续优先级

### P0 - 持久化与多实例基础

| 功能 | 状态 | 价值 |
|------|------|------|
| SQLite Session/Context/Checkpoint | 已实现 | 支持服务重启后恢复 chat session、provider context 和 checkpoint |
| 持久化 A2A Task Store | 已实现 | 支持 A2A Task 查询跨进程/重启 |
| 持久化 Event Log | 已实现 | 支持 A2A 事件 replay |
| 配置化远端 A2A Agent Registry | 待实现 | 启动时自动注册远端 Agent 工具 |

### P1 - 执行效率与协作能力

| 功能 | 状态 | 价值 |
|------|------|------|
| 上下文 token 预算 | 已实现 | 按估算 token 裁剪旧历史，避免仅按消息条数截断 |
| 摘要和记忆升级 | 已实现 | 结构化摘要、摘要合并、session memory 剪枝和独立 memory token 预算 |
| 工具并行执行 | 待实现 | LLM 一次返回多个 function_call 时减少等待 |
| Runner 协作式取消 | 待实现 | A2A cancel 可尝试中断运行中的 LLM/tool |
| Async A2A Client | 待实现 | 支持高并发远端 Agent 调用 |
| Agent Router/Supervisor | 待实现 | 在多个本地/远端 Agent 间路由任务 |

### P2 - 安全与治理

| 功能 | 价值 |
|------|------|
| Prompt Injection 检测 | 提升工具和记忆使用安全性 |
| PII 脱敏 | 降低敏感信息泄露风险 |
| A2A 细粒度鉴权 | 按 skill/tool/context 控制访问 |
| Agent Card 签名 | 提升远端 Agent 发现可信度 |
| 慢工具报警 | 发现高延迟工具和退化链路 |

### P3 - 记忆和检索

| 功能 | 价值 |
|------|------|
| 语义向量记忆 | 支持更强的长期知识检索 |
| 分层记忆 | 区分 Working/Episodic/Semantic Memory |
| 记忆写入审计 | 降低错误记忆污染 |

---

## 当前面试亮点

| 维度 | 亮点 |
|------|------|
| Agent Runtime | 多步推理、工具回灌、checkpoint、非幂等工具恢复保护 |
| 协议集成 | MCP 管工具/资源，A2A 管 Agent 间协作 |
| 扩展机制 | Hooks + Middleware 低侵入扩展 |
| 可观测性 | OpenTelemetry run/step/LLM/tool span |
| 韧性治理 | timeout/retry/rate limit/circuit breaker |
| 安全 | 输入过滤、工具沙箱、参数校验、A2A 扩展卡 bearer auth |
| 流式能力 | `/chat/stream` + A2A task event broker |
| 测试 | 覆盖 runner、tool、mcp、a2a、checkpoint、session |

---

## 验证建议

```bash
pytest
pytest tests/a2a -q
pytest tests/core/test_runner.py -q
pytest tests/mcp -q
pytest tests/tools -q
```

---

## 关键文件参考

- `app/core/runner.py` - 执行引擎核心
- `app/core/tool_registry.py` - 本地工具注册
- `app/mcp/` - MCP 工具接入
- `app/a2a/` - A2A 协议支持
- `app/core/checkpoint.py` - 断点恢复
- `app/core/resilience.py` - 超时、重试、熔断
- `app/core/tracing.py` - OpenTelemetry
- `app/security/input_guard.py` - 输入安全过滤
- `docs/a2a.md` - A2A 详细说明

---

*最后更新：2026/05/03*
