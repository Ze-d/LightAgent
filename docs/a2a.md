# A2A 协议支持说明

## 概览

MyAgent 已支持 A2A（Agent-to-Agent）协议的核心 Server 与 Client 能力。A2A 相关实现集中在 `app/a2a/`，`app/core/runner.py` 保持协议无关；A2A 层只负责协议模型、任务状态、HTTP 路由、事件流、Agent Card 和远端 Agent 调用适配。

## 改动汇总

| 阶段 | 内容 | 关键文件 |
|------|------|------|
| P0 | 建立协议边界，不侵入 Runner | `schemas.py`, `adapter.py`, `routes.py` |
| P1 | A2A Server MVP | `service.py`, `task_store.py` |
| P2 | Task 生命周期与取消 | `task_store.py`, `service.py` |
| P3 | 统一流式事件与订阅 | `event_broker.py` |
| P4 | Agent Card 与扩展卡 | `agent_card.py`, `routes.py` |
| P5 | A2A Client 与远端 Agent 工具桥 | `client.py`, `tool_bridge.py` |

## 模块边界

| 模块 | 职责 |
|------|------|
| `app/a2a/schemas.py` | A2A Pydantic 模型：Agent Card、Message、Task、Artifact、StreamResponse 等 |
| `app/a2a/adapter.py` | A2A Message/Task 与内部 `ChatMessage`、`AgentRunResult` 的转换 |
| `app/a2a/task_store.py` | 进程内 Task 存储、状态转移、终态保护、取消保护 |
| `app/a2a/event_broker.py` | 每个 Task 的事件日志和多订阅者 fan-out |
| `app/a2a/service.py` | A2A Server 编排层，调用现有 Agent 运行链路 |
| `app/a2a/routes.py` | FastAPI 路由注册 |
| `app/a2a/agent_card.py` | 公开 Agent Card 和认证扩展 Agent Card 构建 |
| `app/a2a/client.py` | 同步 A2A HTTP+JSON Client |
| `app/a2a/tool_bridge.py` | 将远端 A2A Agent 注册为本地 Tool |

## A2A Server

### 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/.well-known/agent-card.json` | 公开 Agent Card |
| `GET` | `/a2a/v1/extendedAgentCard` | 认证扩展 Agent Card |
| `POST` | `/a2a/v1/message:send` | 发送消息并返回 Task |
| `POST` | `/a2a/v1/message:stream` | 创建 Task 并通过 SSE 返回事件 |
| `GET` | `/a2a/v1/tasks/{task_id}` | 查询单个 Task |
| `GET` | `/a2a/v1/tasks` | 按 context/status 分页查询 Task |
| `POST` | `/a2a/v1/tasks/{task_id}:cancel` | 请求取消 Task |
| `POST` | `/a2a/v1/tasks/{task_id}:subscribe` | 订阅非终态 Task 的后续事件 |

### 请求示例

```bash
curl -X POST http://localhost:8000/a2a/v1/message:send \
  -H "Content-Type: application/json" \
  -d '{
    "message": {
      "role": "ROLE_USER",
      "parts": [{"text": "你好，介绍一下你的能力"}],
      "contextId": "demo-context"
    }
  }'
```

### 流式请求示例

```bash
curl -N -X POST http://localhost:8000/a2a/v1/message:stream \
  -H "Content-Type: application/json" \
  -d '{
    "message": {
      "role": "ROLE_USER",
      "parts": [{"text": "北京现在几点？"}]
    }
  }'
```

## Runtime 映射

| A2A 概念 | MyAgent 内部概念 |
|------|------|
| `contextId` | `session_id` |
| `taskId` | `A2ATaskStore` 中的 Task ID（默认内存，可配置 SQLite） |
| text `Message` | `ChatMessage` |
| `Task` artifact | `AgentRunResult.answer` |
| `TASK_STATE_COMPLETED` | `AgentRunResult.success == true` |
| `TASK_STATE_FAILED` | `AgentRunResult.success == false` |

只支持 text part。非 text part 会返回 `400 invalid_request`。

## Task 生命周期

```
TASK_STATE_SUBMITTED
  -> TASK_STATE_WORKING
  -> TASK_STATE_COMPLETED | TASK_STATE_FAILED | TASK_STATE_CANCELED
```

终态保护规则：

- completed、failed、canceled、rejected 不会被后续 working/complete/fail 覆盖。
- 对 completed/failed/rejected 再 cancel 会返回 `400 task_not_cancelable`。
- 对终态 Task 继续追加 `taskId` 消息会被拒绝。
- 当前 `AgentRunner` 是同步执行，cancel 是 A2A Task 状态层取消；已经进入 Runner 的线程不会被强制中断，晚返回结果会被 Task Store 忽略。

## Streaming 事件

`message:stream` 和 `tasks/{id}:subscribe` 共用 `A2AEventBroker`。
设置 `STATE_BACKEND=sqlite` 后，事件 replay log 会写入 SQLite；
实时订阅 fan-out 仍在当前进程内完成。

普通完成事件顺序：

```text
Task snapshot
-> statusUpdate TASK_STATE_WORKING
-> artifactUpdate final-answer
-> statusUpdate TASK_STATE_COMPLETED final=true
```

取消事件顺序：

```text
Task snapshot
-> statusUpdate TASK_STATE_CANCELED final=true
```

说明：

- 同一 Task 可被多个客户端订阅。
- broker 会在内存中记录事件。
- `tasks/{id}:subscribe` 当前从 Task 快照开始，再接收订阅后的 live events；公开 API 暂不提供历史事件 replay。
- 终态 Task 订阅返回 `400 unsupported_operation`。

## Agent Card

公开卡：

```bash
curl http://localhost:8000/.well-known/agent-card.json
```

扩展卡：

```bash
curl http://localhost:8000/a2a/v1/extendedAgentCard \
  -H "Authorization: Bearer <A2A_EXTENDED_CARD_TOKEN>"
```

公开卡只暴露高层能力，避免泄露过多内部工具细节。扩展卡启用后会使用 bearer auth，并暴露 tool-level skills。

### A2A 环境变量

| 变量 | 默认值 | 说明 |
|------|------|------|
| `A2A_PUBLIC_URL` | 空 | 为空时从请求 base URL 推导 Agent Card URL |
| `A2A_AGENT_VERSION` | `0.1.0` | Agent Card 版本 |
| `A2A_DOCUMENTATION_URL` | 空 | Agent Card 文档链接 |
| `A2A_ICON_URL` | 空 | Agent Card 图标链接 |
| `A2A_EXTENDED_CARD_TOKEN` | 空 | 设置后启用认证扩展卡 |

## A2A Client

`A2AClient` 是同步 HTTP+JSON Client，支持：

- `get_agent_card()`
- `get_extended_agent_card()`
- `send_message()` / `send_text()`
- `stream_message()` / `stream_text()`
- `get_task()` / `list_tasks()` / `cancel_task()` / `subscribe_task()`

示例：

```python
from app.a2a.client import A2AClient, extract_text_from_send_response

client = A2AClient("https://remote-agent.example")
response = client.send_text("Summarize this issue", context_id="case-123")
answer = extract_text_from_send_response(response)
```

## 远端 Agent 工具桥

可以把远端 A2A Agent 注册为本地工具，供当前 Agent 通过 tool calling 调用：

```python
from app.a2a.tool_bridge import register_remote_a2a_agent_tool

register_remote_a2a_agent_tool(
    tool_registry,
    name="remote_research_agent",
    description="Delegate research questions to a remote A2A research agent.",
    base_url="https://remote-agent.example",
    bearer_token="optional-token",
)
```

注册后的工具参数：

```json
{
  "message": "Question or task for the remote agent",
  "context_id": "optional-remote-context"
}
```

## 当前限制

- Task Store 和事件 broker 都是进程内内存实现。
- 暂无 push notification callbacks。
- 暂无 `AgentRunner` 内部协作式取消。
- 暂无 async A2A Client API。
- 暂无远端 Agent 自动发现和持久化 remote context 映射。
- 暂无签名 Agent Card、多租户 Agent Interface 和细粒度 skill auth。

## 验证

当前 A2A 测试覆盖：

- Agent Card / extended Agent Card
- A2A Adapter
- Task Store 生命周期和取消
- A2A Service 与 HTTP routes
- Streaming Event Broker
- A2A Client
- Remote Agent Tool Bridge

运行：

```bash
pytest tests/a2a -q
pytest -q
```
