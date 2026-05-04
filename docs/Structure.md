# Minimal Agent - 系统架构文档

## 1. 系统上下游

```text
用户 / 客户端应用
        │
        ├── /chat, /chat/stream
        ├── A2A HTTP+JSON / SSE
        └── Checkpoint API
        ▼
┌──────────────────────────────────────┐
│          Minimal Agent API            │
│          FastAPI + Python             │
└──────────────────────────────────────┘
        │
        ├── OpenAI-compatible LLM API
        ├── MCP Server（stdio/SSE，可选）
        └── Remote A2A Agent（HTTP+JSON，可选）
```

| 方向 | 组件 | 说明 |
|------|------|------|
| 上游 | 用户 / 客户端 | 通过 `/chat`、`/chat/stream` 或 A2A API 接入 |
| 上游/下游 | Remote A2A Agent | 本系统既可作为 A2A Server，也可作为 A2A Client |
| 下游 | DashScope/OpenAI-compatible API | LLM 推理服务 |
| 下游 | MCP Server | 可选远程工具生态 |

---

## 2. 核心模块

| 模块 | 路径 | 职责 |
|------|------|------|
| API | `app/api.py` | FastAPI 入口，注册 chat、checkpoint、A2A 路由 |
| A2A | `app/a2a/` | A2A schema、server、client、task store、event broker、tool bridge |
| Agents | `app/agents/` | BaseAgent、ChatAgent、ToolAwareAgent |
| Runner | `app/core/runner.py` | 协议无关执行循环，多步推理 + 工具调用 |
| Tool Registry | `app/core/tool_registry.py` | 本地工具注册与调用 |
| MCP | `app/mcp/` | MCP 配置、Client、ToolRegistry、stdio/SSE transport |
| Session | `app/core/session_manager.py` | 会话存储抽象，支持内存/SQLite |
| Context State | `app/core/context_state.py`, `app/core/context_builder.py`, `app/core/token_budget.py` | 应用会话、Provider 上下文、token 预算和 LLM 输入 envelope |
| Checkpoint | `app/core/checkpoint.py` | 执行快照与恢复 |
| Event/SSE | `app/core/event_channel.py`, `app/core/sse.py` | SSE 事件通道与兼容响应 |
| Hooks | `app/core/hooks.py`, `app/hooks/` | 生命周期观察者 |
| Middleware | `app/core/middleware.py`, `app/middleware/` | LLM/tool 前置拦截 |
| Resilience | `app/core/resilience.py`, `app/core/rate_limiter.py` | 超时、重试、熔断、限流 |
| Tracing | `app/core/tracing.py` | OpenTelemetry tracing |
| Memory | `app/memory/` | 文档型记忆与摘要 |
| Security | `app/security/` | 输入安全过滤 |
| Skills | `app/skills/` | slash-style skill |
| Tools | `app/tools/` | 内置工具、沙箱、Pydantic 参数校验 |

---

## 3. 普通 Chat 数据流

```text
POST /chat 或 /chat/stream
    │
    ▼
ChatRequest { message, session_id? }
    │
    ▼
SessionManager 创建/加载 history
    │
    ▼
注入只读 memory context
    │
    ▼
按 token 预算裁剪旧历史
    │
    ▼
ToolAwareAgent + AgentRunner.run()
    │
    ├── Middleware.before_llm()
    ├── OpenAI-compatible Responses API
    ├── 解析 function_call
    └── ToolRegistry / MCPToolRegistry 执行工具
    │
    ▼
AgentRunResult
    │
    ├── /chat 返回 ChatResponse
    └── /chat/stream 通过 SSEHooks 推送事件
```

---

## 4. A2A Server 数据流

```text
POST /a2a/v1/message:send 或 message:stream
    │
    ▼
A2A Message
    │
    ▼
A2AService
    │
    ├── A2ATaskStore 创建 Task（默认内存，可配置 SQLite）
    ├── contextId 映射为内部 session_id
    ├── A2AProtocolAdapter 转为 ChatMessage
    ├── 调用现有 AgentRunner 链路
    └── A2AEventBroker 记录/广播 StreamResponse
    │
    ▼
A2A Task / SSE StreamResponse
```

状态映射：

```text
TASK_STATE_SUBMITTED
  -> TASK_STATE_WORKING
  -> TASK_STATE_COMPLETED | TASK_STATE_FAILED | TASK_STATE_CANCELED
```

---

## 5. A2A Client 数据流

```text
AgentRunner 触发远端 Agent 工具（可选）
    │
    ▼
register_remote_a2a_agent_tool 注册的 ToolSpec
    │
    ▼
A2AClient
    │
    ├── GET /.well-known/agent-card.json
    ├── POST /a2a/v1/message:send
    └── 解析 Task/Artifact 文本
    │
    ▼
远端 A2A Agent 响应回灌为本地工具结果
```

---

## 6. 外部依赖

| 依赖 | 类型 | 说明 |
|------|------|------|
| DashScope/OpenAI-compatible API | 外部服务 | LLM 推理服务 |
| MCP Server | 外部服务/进程 | 可选工具服务 |
| Remote A2A Agent | 外部服务 | 可选 Agent 协作对象 |
| `openai` | Python 库 | LLM Client |
| `httpx` | Python 库 | A2A/MCP HTTP Client |
| `fastapi`, `uvicorn` | Python 库 | Web API |
| `pydantic` | Python 库 | Schema 与参数校验 |
| `tenacity` | Python 库 | 重试 |
| `opentelemetry-*` | Python 库 | Tracing |

### 环境变量

| 变量 | 默认值 | 说明 |
|------|------|------|
| `LLM_API_KEY` | 必填 | LLM API Key |
| `LLM_MODEL_ID` | `gpt-5.4-mini` | 模型名称，`.env.example` 中示例为 `qwen3.5-flash` |
| `LLM_BASE_URL` | DashScope compatible URL | OpenAI-compatible API 地址 |
| `LLM_TIMEOUT` | `30` | LLM 调用超时秒数 |
| `MAX_STEPS` | `5` | Agent 最大执行步数 |
| `CONTEXT_MAX_INPUT_TOKENS` | `8000` | 估算输入上下文 token 预算；设为 `0` 可关闭 |
| `CONTEXT_MEMORY_MAX_TOKENS` | `1200` | memory 注入前的独立 token 预算；设为 `0` 可关闭 |
| `STATE_BACKEND` | `memory` | 状态后端，支持 `memory` 或 `sqlite` |
| `STATE_DB_PATH` | `.runtime/myagent.sqlite3` | SQLite 状态库路径 |
| `A2A_PUBLIC_URL` | 空 | Agent Card 对外 URL；为空时用请求 base URL |
| `A2A_AGENT_VERSION` | `0.1.0` | Agent Card 版本 |
| `A2A_EXTENDED_CARD_TOKEN` | 空 | 扩展 Agent Card bearer token |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | 可选 | OpenTelemetry OTLP endpoint |

---

## 7. API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/` | 健康检查 |
| `POST` | `/chat` | 普通对话 |
| `POST` | `/chat/stream` | SSE 流式对话 |
| `GET` | `/.well-known/agent-card.json` | A2A Agent Card |
| `GET` | `/a2a/v1/extendedAgentCard` | A2A 扩展 Agent Card |
| `POST` | `/a2a/v1/message:send` | A2A 消息发送 |
| `POST` | `/a2a/v1/message:stream` | A2A 消息流 |
| `GET` | `/a2a/v1/tasks/{task_id}` | 查询 A2A Task |
| `GET` | `/a2a/v1/tasks` | 查询 A2A Task 列表 |
| `POST` | `/a2a/v1/tasks/{task_id}:cancel` | 取消 A2A Task |
| `POST` | `/a2a/v1/tasks/{task_id}:subscribe` | 订阅 A2A Task |
| `POST` | `/checkpoint/{session_id}/resume` | 恢复 checkpoint |
| `GET` | `/checkpoint/{session_id}` | 查询 checkpoint |
| `DELETE` | `/checkpoint/{session_id}` | 删除 checkpoint |

---

## 8. 部署拓扑

```text
┌─────────────────────────────┐
│ 客户端 / A2A Client          │
└──────────┬──────────────────┘
           │ HTTP/SSE
           ▼
┌─────────────────────────────┐
│ FastAPI / uvicorn           │
│ - Chat API                  │
│ - A2A Server                │
│ - Checkpoint API            │
└──────────┬──────────────────┘
           │
           ├── LLM API
           ├── MCP Server
           └── Remote A2A Agent
```

默认部署形态仍是单 Python 进程和内存状态。设置 `STATE_BACKEND=sqlite`
后，Chat session、context state、checkpoint、A2A task 和 A2A event replay
log 会写入 `STATE_DB_PATH`，服务重启后可恢复最近状态。实时 SSE fan-out 仍是进程内行为。

上下文构建会先按 `CONTEXT_MEMORY_MAX_TOKENS` 压缩 memory context，再按
`CONTEXT_MAX_INPUT_TOKENS` 裁剪最终 LLM 输入。历史摘要使用结构化 system
summary，避免把旧摘要当普通系统提示重复保留。

---

## 9. 相关文档

- [A2A 协议支持说明](a2a.md)
- [QuickStart](QuickStart.md)
- [API 文档](api.md)
- [项目指标](project-metrics.md)
- [ADR](adr/README.md)

---

*最后更新：2026/05/03*
