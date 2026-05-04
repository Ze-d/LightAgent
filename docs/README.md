# Minimal Agent API

基于 FastAPI 的轻量级 Agent 运行时框架，支持多轮对话、工具调用、SSE 流式响应、Hooks/Middleware、MCP 工具接入、A2A Agent 协作协议、记忆、限流、熔断、Tracing 和断点恢复。

---

## 项目做什么

MyAgent 实现了一套可扩展的 LLM Agent 后端运行时：

- **对话接口**：`/chat` 和 `/chat/stream` 支持普通对话与 SSE 流式响应。
- **工具调用**：`ToolRegistry` 支持 OpenAI tools schema、Pydantic 参数校验、同步/异步工具调用。
- **A2A 协议**：作为 A2A Server 暴露 Agent Card、message/task API、任务订阅；作为 A2A Client 调用远端 Agent，并可把远端 Agent 注册为本地工具。
- **MCP 接入**：支持 stdio/SSE MCP Server 注册、远程工具发现与调用。
- **运行时扩展**：Hooks 和 Middleware 可插入日志、SSE、安全过滤、历史裁剪、权限控制等逻辑。
- **工程治理**：支持超时、重试、Token Bucket 限流、Circuit Breaker 熔断、OpenTelemetry tracing。
- **状态管理**：支持 session、多轮上下文、文件型记忆、checkpoint 断点恢复。

---

## 核心能力

| 能力 | 说明 |
|------|------|
| Agent Runner | 基于 OpenAI Responses API 的多步推理 + 工具调用循环 |
| Tool Registry | 管理本地工具、远程 A2A Agent 工具、MCP 工具 |
| A2A Server | `/.well-known/agent-card.json`、`/a2a/v1/message:*`、`/a2a/v1/tasks*` |
| A2A Client | 发现远端 Agent Card、发送消息、消费 SSE、订阅/取消远端 Task |
| SSE Streaming | `/chat/stream` 与 A2A streaming/subscription 都基于 SSE |
| Hooks/Middleware | 生命周期观察和执行前拦截 |
| Checkpoint | 工具调用阶段保存快照，支持恢复并避免非幂等工具重复执行 |
| Memory | 文档型记忆和会话摘要注入 |
| Observability | OpenTelemetry span 覆盖 run/step/LLM/tool |
| Resilience | 超时、重试、限流、熔断 |

---

## 快速启动

```bash
pip install -r requirements.txt
uvicorn app.api:app --reload --host 0.0.0.0 --port 8000
```

`.env` 示例：

```env
LLM_API_KEY=your_api_key_here
LLM_MODEL_ID=qwen3.5-flash
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_TIMEOUT=30
MAX_STEPS=5

CONTEXT_MAX_INPUT_TOKENS=8000
CONTEXT_MEMORY_MAX_TOKENS=1200

STATE_BACKEND=memory
STATE_DB_PATH=.runtime/myagent.sqlite3

A2A_PUBLIC_URL=http://localhost:8000
A2A_AGENT_VERSION=0.1.0
A2A_DOCUMENTATION_URL=
A2A_ICON_URL=
A2A_EXTENDED_CARD_TOKEN=
```

访问：

- API 文档：http://localhost:8000/docs
- 健康检查：http://localhost:8000/
- A2A Agent Card：http://localhost:8000/.well-known/agent-card.json

---

## 主要端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/` | 健康检查 |
| `POST` | `/chat` | 普通对话 |
| `POST` | `/chat/stream` | SSE 流式对话 |
| `GET` | `/.well-known/agent-card.json` | A2A Agent Card |
| `GET` | `/a2a/v1/extendedAgentCard` | 认证扩展 Agent Card |
| `POST` | `/a2a/v1/message:send` | A2A 消息发送 |
| `POST` | `/a2a/v1/message:stream` | A2A 消息流式执行 |
| `GET` | `/a2a/v1/tasks/{task_id}` | 查询 A2A Task |
| `GET` | `/a2a/v1/tasks` | 查询 A2A Task 列表 |
| `POST` | `/a2a/v1/tasks/{task_id}:cancel` | 取消 A2A Task |
| `POST` | `/a2a/v1/tasks/{task_id}:subscribe` | 订阅 A2A Task 事件 |
| `POST` | `/checkpoint/{session_id}/resume` | 恢复 checkpoint |
| `GET` | `/checkpoint/{session_id}` | 查询 checkpoint |
| `DELETE` | `/checkpoint/{session_id}` | 删除 checkpoint |

---

## 目录结构

```text
app/
├── a2a/          # A2A schemas, server, client, task store, event broker, tool bridge
├── agents/       # BaseAgent, ChatAgent, ToolAwareAgent
├── configs/      # 环境变量与日志
├── core/         # Runner, hooks, middleware, session, checkpoint, resilience, tracing
├── hooks/        # LoggingHooks, SSEHooks
├── mcp/          # MCP client, config, transport, tool registry
├── memory/       # Document memory and summarizer
├── middleware/   # History trim, tool permission
├── obj/          # API schemas and runtime TypedDicts
├── security/     # Input guard
├── skills/       # Slash skills
└── tools/        # Built-in tools, sandbox, validator, registry factory
```

---

## 文档入口

| 文档 | 说明 |
|------|------|
| [QuickStart](QuickStart.md) | 本地启动、调用示例、端点一览 |
| [API 文档](api.md) | Chat、Checkpoint、A2A、SSE 和错误格式 |
| [Structure](Structure.md) | 系统架构与核心链路 |
| [A2A 协议支持](a2a.md) | A2A Server/Client/Task/Streaming/Agent Card 完整说明 |
| [项目指标](project-metrics.md) | 代码规模、端点、工具、测试指标 |
| [ADR](adr/README.md) | 架构决策记录 |

---

## 常用命令

| 命令 | 说明 |
|------|------|
| `uvicorn app.api:app --reload --host 0.0.0.0 --port 8000` | 启动开发服务 |
| `pytest` | 运行全部测试 |
| `pytest tests/a2a -q` | 运行 A2A 测试 |
| `pytest tests/core/test_runner.py -q` | 运行 Runner 核心测试 |

---

*最后更新：2026/05/03*
