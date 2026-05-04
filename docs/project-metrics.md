# Minimal Agent API - 项目数值指标

> 统计日期：2026-05-03

---

## 1. 代码规模

| 指标 | 数值 |
|------|------|
| Python 源文件 (`app/`) | **67** 个 |
| 源代码行数 (`app/`) | **5,705** 行 |
| 测试文件 (`tests/`) | **26** 个 |
| 测试代码行数 | **2,509** 行 |
| Pytest 收集用例数 | **149** 个 |
| 最近全量测试结果 | **148 passed, 1 skipped** |
| 总类数量 | **113** 个 |
| 测试/源码行数比 | **0.44 : 1** |

---

## 2. 模块构成

| 目录 | 文件数 | 职责 |
|------|------|------|
| `app/a2a/` | 10 | A2A schema、server、client、task store、event broker、tool bridge |
| `app/core/` | 14 | Runner、ToolRegistry、Session、Hooks、Middleware、Resilience、Tracing、RateLimiter、Checkpoint、Skill、SSE |
| `app/mcp/` | 9 | MCP Client、Config、Errors、ToolRegistry、Transport |
| `app/tools/` | 6 | 内置工具、记忆工具、沙箱校验、注册工厂、参数校验 |
| `app/agents/` | 4 | BaseAgent、ChatAgent、ToolAwareAgent |
| `app/skills/` | 4 | simplify、loop、注册工厂 |
| `app/configs/` | 3 | 配置、日志 |
| `app/memory/` | 3 | Summarizer、DocumentStore |
| `app/obj/` | 3 | Pydantic Schemas、TypedDict Types |
| `app/hooks/` | 2 | LoggingHooks、SSEHooks |
| `app/middleware/` | 2 | HistoryTrim、ToolPermission |
| `app/security/` | 2 | InputGuard |
| `app/prompts/` | 2 | System Prompt |
| `app/exceptions/` | 1 | 异常定义 |

---

## 3. API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 健康检查 |
| `/chat` | POST | 普通对话接口 |
| `/chat/stream` | POST | SSE 流式对话接口 |
| `/.well-known/agent-card.json` | GET | A2A Agent Card |
| `/a2a/v1/rpc` | POST | A2A 1.0 JSON-RPC |
| `/a2a/v1/extendedAgentCard` | GET | 兼容旧 HTTP+JSON 的 A2A 扩展 Agent Card |
| `/a2a/v1/message:send` | POST | 兼容旧 HTTP+JSON 的 A2A 消息发送 |
| `/a2a/v1/message:stream` | POST | 兼容旧 HTTP+JSON 的 A2A 消息流 |
| `/a2a/v1/tasks/{task_id}` | GET | 查询 A2A Task |
| `/a2a/v1/tasks` | GET | 查询 A2A Task 列表 |
| `/a2a/v1/tasks/{task_id}:cancel` | POST | 取消 A2A Task |
| `/a2a/v1/tasks/{task_id}:subscribe` | POST | 订阅 A2A Task |
| `/checkpoint/{session_id}/resume` | POST | 恢复 checkpoint |
| `/checkpoint/{session_id}` | GET | 查询 checkpoint |
| `/checkpoint/{session_id}` | DELETE | 删除 checkpoint |

---

## 4. A2A 能力

| 能力 | 状态 |
|------|------|
| Agent Card | 已实现 |
| Extended Agent Card + Bearer Auth | 已实现 |
| JSON-RPC transport | 已实现 |
| HTTP+JSON compatibility endpoints | 已实现 |
| SSE streaming/subscription | 已实现 |
| Task query/list/cancel/subscribe | 已实现 |
| Task lifecycle protection | 已实现 |
| Event broker fan-out | 已实现 |
| A2A Client | 已实现 |
| Remote Agent Tool Bridge | 已实现 |
| Push notification | 未实现 |
| Persistent Task Store | 未实现 |

---

## 5. 内置工具

| 工具名 | 参数 | 类型 |
|--------|------|------|
| `calculator` | `expression` | 计算 |
| `get_current_time` | `city` | 时间 |
| `convert_units` | `value`, `from_unit`, `to_unit` | 单位转换 |
| `analyze_text` | `text` | 文本分析 |
| `get_weather` | `city` | 天气 |
| `search_knowledge` | `query`, `top_k` | 知识检索 |
| `memory_read` | `scope`, `session_id` | 记忆读取 |
| `memory_append_session_summary` | `session_id`, `summary` | 记忆写入 |

**本地内置工具：8 个**。远端 A2A Agent 可通过 `register_remote_a2a_agent_tool()` 动态注册为工具。

---

## 6. 内置 Skills

| Skill | 参数 |
|------|------|
| `simplify` | `code`, `target` |
| `loop` | `interval`, `command`, `max_rounds` |

**总计：2 个 Skill**。

---

## 7. 类型体系

| 类型 | 数量 | 位置 |
|------|------|------|
| TypedDict | **14** 个 | `app/obj/types.py` 等 |
| Pydantic BaseModel / A2ABaseModel | **34** 个 | `app/obj/schemas.py`, `app/a2a/schemas.py`, tool input models |
| 异常类 | **10+** 个 | `resilience.py`, `mcp/errors.py`, `a2a/service.py`, `a2a/client.py` |

---

## 8. 运行时配置参数

| 参数 | 默认值 | 说明 |
|------|------|------|
| `LLM_TIMEOUT` | `30` | LLM API 调用超时 |
| `MAX_STEPS` | `5` | Agent 最大推理步数 |
| `DEFAULT_MAX_RETRIES` | `3` | LLM 最大重试 |
| 工具超时 | `10s` | 单次工具执行超时 |
| 熔断 failure_threshold | `5` | 连续失败触发 OPEN |
| 熔断 timeout_seconds | `60` | OPEN -> HALF_OPEN 等待 |
| `A2A_AGENT_VERSION` | `0.1.0` | Agent Card 版本 |
| `A2A_PUBLIC_URL` | 空 | Agent Card 对外 URL |
| `A2A_EXTENDED_CARD_TOKEN` | 空 | 扩展 Agent Card 鉴权 token |

---

## 9. 测试覆盖分布

| 测试模块 | 文件数 | 覆盖内容 |
|------|------|------|
| `tests/a2a/` | 7 | Adapter、Agent Card、Client、Event Broker、Routes、Task Store、Tool Bridge |
| `tests/agents/` | 2 | ChatAgent、ToolAwareAgent |
| `tests/core/` | 6 | Runner、Session、Checkpoint、Tool 事件、成功率、选择准确率 |
| `tests/mcp/` | 5 | Config、Errors、ToolRegistry、stdio/SSE Transport |
| `tests/tools/` | 3 | Registry、Validator、Tool 成功率 |
| `tests/` root | 3 | 内置工具、新功能、集成测试 |

---

## 10. 外部依赖

| 依赖 | 数量 | 关键项 |
|------|------|------|
| Python 库 | **13** 个 | fastapi, uvicorn, openai, pydantic, httpx, tenacity, opentelemetry, pytest, python-dotenv |
| 外部 LLM 服务 | **1** 个 | OpenAI-compatible API，默认配置指向 DashScope |
| 可选远程工具/Agent | **2 类** | MCP Server、A2A Agent |
| 可选可观测导出 | **1** 个 | OpenTelemetry OTLP |

---

## 11. 当前限制

| 方向 | 限制 |
|------|------|
| 持久化 | Session、A2A Task、A2A Event Broker 默认内存实现 |
| A2A | 暂无 push notification、持久事件 replay、async client |
| 执行取消 | A2A cancel 不会强制中断已进入 Runner 的同步线程 |
| 多实例 | 单进程内存状态不支持跨实例共享 |

---

*统计方式：PowerShell `Get-ChildItem`、`Select-String`、`pytest --collect-only -q`。*
