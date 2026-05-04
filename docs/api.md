# API 文档

## 1. 通用约定

默认服务地址：

```text
http://localhost:8000
```

通用请求头：

```http
Content-Type: application/json
Accept: application/json
```

SSE 流式接口使用：

```http
Accept: text/event-stream
```

当前 API 分为四类：

| 类别 | 说明 |
|------|------|
| Health | 服务健康检查 |
| Chat | MyAgent 原生对话接口 |
| Checkpoint | Agent 执行断点查询、恢复、删除 |
| A2A | Agent-to-Agent 协议接口 |

---

## 2. Health API

### GET `/`

检查服务是否启动。

**响应示例**

```json
{
  "message": "Minimal Agent API is running"
}
```

---

## 3. Chat API

### 数据模型

#### ChatRequest

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `message` | string | 是 | 当前用户输入 |
| `session_id` | string/null | 否 | 会话 ID；不传则创建新会话 |

#### ChatResponse

| 字段 | 类型 | 说明 |
|------|------|------|
| `session_id` | string | 当前会话 ID |
| `answer` | string | Agent 最终回答 |
| `history_length` | integer | 当前会话历史消息数 |

### POST `/chat`

执行一次普通同步对话。

**请求示例：新会话**

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "你好"}'
```

**响应示例**

```json
{
  "session_id": "c8d2b41a-2cb1-4d4d-92a4-2f89f0d18d78",
  "answer": "你好！有什么可以帮你？",
  "history_length": 3
}
```

**请求示例：继续会话**

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "c8d2b41a-2cb1-4d4d-92a4-2f89f0d18d78",
    "message": "继续刚才的话题"
  }'
```

**常见错误**

| HTTP 状态 | 场景 |
|------|------|
| `404` | `session_id` 不存在 |
| `500` | Agent 执行异常 |

### POST `/chat/stream`

执行一次对话并通过 SSE 推送执行事件。

**请求示例**

```bash
curl -N -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "北京现在几点了"}'
```

**SSE 事件**

| event | data |
|------|------|
| `session_created` | `{"session_id": "..."}` |
| `tool_start` | ToolCallEvent |
| `tool_success` | ToolCallEvent |
| `tool_error` | ToolCallEvent |
| `run_end` | RunEndEvent |
| `final_answer` | `{"session_id": "...", "answer": "...", "history_length": 3}` |
| `error` | `{"message": "..."}` |

**ToolCallEvent 示例**

```json
{
  "agent_name": "chat-agent",
  "step": 1,
  "call_id": "call_1",
  "tool_name": "get_current_time",
  "arguments": {"city": "beijing"},
  "status": "success",
  "result": "Beijing current time: ..."
}
```

---

## 4. Checkpoint API

Checkpoint 用于恢复中断的 Agent 执行。它记录 step、phase、tool call、function output 和 agent state。

### POST `/checkpoint/{session_id}/resume`

恢复指定 session 的最近 checkpoint。

**请求示例**

```bash
curl -X POST http://localhost:8000/checkpoint/c8d2b41a-2cb1-4d4d-92a4-2f89f0d18d78/resume
```

**响应**

返回 `ChatResponse`。

```json
{
  "session_id": "c8d2b41a-2cb1-4d4d-92a4-2f89f0d18d78",
  "answer": "恢复后的最终回答",
  "history_length": 5
}
```

**常见错误**

| HTTP 状态 | 场景 |
|------|------|
| `404` | 不存在 checkpoint 或 session |
| `500` | checkpoint 恢复失败 |

### GET `/checkpoint/{session_id}`

查询指定 session 的最近 checkpoint。

**请求示例**

```bash
curl http://localhost:8000/checkpoint/c8d2b41a-2cb1-4d4d-92a4-2f89f0d18d78
```

**响应示例**

```json
{
  "session_id": "c8d2b41a-2cb1-4d4d-92a4-2f89f0d18d78",
  "run_id": "run-1",
  "step": 1,
  "phase": "tool_requested",
  "history_length": 3,
  "function_outputs_count": 0,
  "tool_calls": [
    {
      "call_id": "call_1",
      "tool_name": "memory_append_session_summary",
      "status": "running",
      "arguments_hash": "sha256...",
      "side_effect_policy": "non_idempotent"
    }
  ],
  "resumable": true,
  "requires_manual_action": true,
  "timestamp": "2026-05-03T12:00:00"
}
```

### DELETE `/checkpoint/{session_id}`

删除指定 session 的 checkpoint。

**请求示例**

```bash
curl -X DELETE http://localhost:8000/checkpoint/c8d2b41a-2cb1-4d4d-92a4-2f89f0d18d78
```

**响应示例**

```json
{
  "message": "Checkpoint cleared for session: c8d2b41a-2cb1-4d4d-92a4-2f89f0d18d78"
}
```

---

## 5. A2A API

A2A API 基础路径：

```text
/a2a/v1
```

当前实现只支持 text part。`data`、`raw`、`url` 等非文本 part 会被拒绝。

### 5.1 核心数据模型

#### Part

| 字段 | 类型 | 说明 |
|------|------|------|
| `text` | string/null | 文本内容 |
| `data` | any/null | 结构化数据，当前服务端不支持执行 |
| `raw` | string/null | 原始内容，当前服务端不支持执行 |
| `url` | string/null | 外部资源 URL，当前服务端不支持执行 |
| `mediaType` | string/null | MIME type |
| `filename` | string/null | 文件名 |
| `metadata` | object | 元数据 |

一个 `Part` 必须且只能包含一个 payload 字段：`text`、`data`、`raw`、`url` 之一。

#### Message

| 字段 | 类型 | 说明 |
|------|------|------|
| `role` | `ROLE_USER` / `ROLE_AGENT` | 消息角色 |
| `parts` | Part[] | 消息内容 |
| `messageId` | string/null | 消息 ID |
| `taskId` | string/null | 关联 Task ID |
| `contextId` | string/null | 上下文 ID；映射为内部 session_id |
| `metadata` | object | 元数据 |
| `extensions` | string[] | 扩展 URI |
| `referenceTaskIds` | string[] | 引用 Task |

#### Task

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | Task ID |
| `contextId` | string | 上下文 ID |
| `status` | TaskStatus | 当前状态 |
| `artifacts` | Artifact[] | 输出 artifact |
| `history` | Message[] | Task 消息历史 |
| `metadata` | object | 元数据，例如 steps、error、tool_events |

#### TaskState

| 状态 | 说明 |
|------|------|
| `TASK_STATE_SUBMITTED` | 已提交 |
| `TASK_STATE_WORKING` | 执行中 |
| `TASK_STATE_INPUT_REQUIRED` | 需要输入，当前未主动产生 |
| `TASK_STATE_COMPLETED` | 完成 |
| `TASK_STATE_FAILED` | 失败 |
| `TASK_STATE_CANCELED` | 已取消 |
| `TASK_STATE_REJECTED` | 已拒绝 |
| `TASK_STATE_AUTH_REQUIRED` | 需要鉴权 |

### 5.2 Agent Card

### GET `/.well-known/agent-card.json`

返回公开 Agent Card。

**请求示例**

```bash
curl http://localhost:8000/.well-known/agent-card.json
```

**响应示例**

```json
{
  "name": "chat-agent",
  "description": "MyAgent is a tool-aware conversational agent with session memory, checkpoint recovery, and streaming execution events.",
  "version": "0.1.0",
  "url": "http://localhost:8000/a2a/v1",
  "protocolVersion": "1.0",
  "supportedInterfaces": [
    {
      "url": "http://localhost:8000/a2a/v1",
      "protocolBinding": "HTTP+JSON",
      "protocolVersion": "1.0"
    }
  ],
  "capabilities": {
    "streaming": true,
    "pushNotifications": false,
    "extendedAgentCard": false
  },
  "defaultInputModes": ["text/plain"],
  "defaultOutputModes": ["text/plain"],
  "skills": []
}
```

### GET `/a2a/v1/extendedAgentCard`

返回认证扩展 Agent Card。仅当设置 `A2A_EXTENDED_CARD_TOKEN` 时可用。

**请求示例**

```bash
curl http://localhost:8000/a2a/v1/extendedAgentCard \
  -H "Authorization: Bearer <A2A_EXTENDED_CARD_TOKEN>"
```

**错误**

| HTTP 状态 | code | 场景 |
|------|------|------|
| `401` | `unauthorized` | 缺少或错误 bearer token |
| `404` | `extended_agent_card_not_available` | 未启用扩展 Agent Card |

### GET `/a2a/v1`

接口根路径说明。该端点不进入 OpenAPI schema。

**响应示例**

```json
{
  "message": "A2A interface reserved for message and task endpoints.",
  "protocolVersion": "1.0"
}
```

### 5.3 Send Message

### POST `/a2a/v1/message:send`

发送一条 A2A 消息并返回 `SendMessageResponse`。默认阻塞到 Task 终态；如果设置 `configuration.returnImmediately=true`，会立即返回 `TASK_STATE_WORKING` 的 Task，并在后台继续执行。

**请求模型：SendMessageRequest**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `tenant` | string/null | 否 | 租户信息，当前不参与路由 |
| `message` | Message | 是 | 用户消息，必须是 `ROLE_USER` |
| `configuration` | SendMessageConfiguration | 否 | 执行配置 |
| `metadata` | object | 否 | Task 元数据 |

**configuration 字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| `acceptedOutputModes` | string[] | 接受的输出类型，建议 `["text/plain"]` |
| `taskPushNotificationConfig` | object/null | 当前未实现 |
| `historyLength` | integer/null | 返回 Task 时保留的 history 条数 |
| `returnImmediately` | boolean | 是否立即返回 working Task |

**请求示例**

```bash
curl -X POST http://localhost:8000/a2a/v1/message:send \
  -H "Content-Type: application/json" \
  -d '{
    "message": {
      "role": "ROLE_USER",
      "parts": [{"text": "帮我计算 2 + 3"}],
      "contextId": "demo-context"
    },
    "configuration": {
      "acceptedOutputModes": ["text/plain"],
      "historyLength": 2,
      "returnImmediately": false
    }
  }'
```

**响应示例**

```json
{
  "task": {
    "id": "task-1",
    "contextId": "demo-context",
    "status": {
      "state": "TASK_STATE_COMPLETED",
      "message": {
        "role": "ROLE_AGENT",
        "parts": [{"text": "2 + 3 = 5"}],
        "taskId": "task-1",
        "contextId": "demo-context"
      }
    },
    "artifacts": [
      {
        "artifactId": "final-answer",
        "name": "Final answer",
        "parts": [{"text": "2 + 3 = 5"}]
      }
    ],
    "history": [],
    "metadata": {
      "steps": 2,
      "error": null,
      "tool_events": []
    }
  }
}
```

**常见错误**

| HTTP 状态 | code | 场景 |
|------|------|------|
| `400` | `invalid_request` | 非 `ROLE_USER` 消息、非 text part、终态 Task 追加消息 |
| `404` | `task_not_found` | 请求引用的 `taskId` 不存在 |
| `422` | FastAPI validation error | 请求 JSON 不符合 schema |

### 5.4 Stream Message

### POST `/a2a/v1/message:stream`

创建 Task，并通过 SSE 返回 `StreamResponse`。

**请求示例**

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

**SSE data 类型：StreamResponse**

`StreamResponse` 四选一：

| 字段 | 说明 |
|------|------|
| `task` | Task 快照 |
| `message` | 独立消息，当前服务端一般不返回 |
| `statusUpdate` | Task 状态更新 |
| `artifactUpdate` | Artifact 更新 |

**正常事件顺序**

```text
event: message
data: {"task": {...}}

event: message
data: {"statusUpdate": {"taskId": "...", "contextId": "...", "status": {"state": "TASK_STATE_WORKING"}}}

event: message
data: {"artifactUpdate": {"taskId": "...", "contextId": "...", "artifact": {...}}}

event: message
data: {"statusUpdate": {"taskId": "...", "contextId": "...", "status": {"state": "TASK_STATE_COMPLETED"}, "final": true}}
```

### 5.5 Task API

### GET `/a2a/v1/tasks/{task_id}`

查询单个 Task。

**Query 参数**

| 参数 | 类型 | 说明 |
|------|------|------|
| `historyLength` | integer | 返回 Task history 的最后 N 条 |

**请求示例**

```bash
curl "http://localhost:8000/a2a/v1/tasks/task-1?historyLength=2"
```

### GET `/a2a/v1/tasks`

查询 Task 列表。

**Query 参数**

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `contextId` | string | 空 | 只查询指定上下文 |
| `state` | TaskState | 空 | 只查询指定状态 |
| `pageSize` | integer | `50` | 每页数量，范围 1-100 |
| `pageToken` | string | `""` | 分页 token，当前实现为 offset 字符串 |
| `historyLength` | integer | 空 | 每个 Task 返回的 history 条数 |

**响应模型：ListTasksResponse**

```json
{
  "tasks": [],
  "totalSize": 0,
  "pageSize": 50,
  "nextPageToken": ""
}
```

### POST `/a2a/v1/tasks/{task_id}:cancel`

请求取消 Task。

**请求示例**

```bash
curl -X POST http://localhost:8000/a2a/v1/tasks/task-1:cancel \
  -H "Content-Type: application/json" \
  -d '{}'
```

**请求体：CancelTaskRequest**

| 字段 | 类型 | 说明 |
|------|------|------|
| `tenant` | string/null | 当前不参与路由 |
| `metadata` | object | 附加元数据 |

**响应**

返回取消后的 `Task`，状态为 `TASK_STATE_CANCELED`。

**常见错误**

| HTTP 状态 | code | 场景 |
|------|------|------|
| `404` | `task_not_found` | Task 不存在 |
| `400` | `task_not_cancelable` | Task 已 completed/failed/rejected |

取消说明：当前 cancel 是 A2A Task 状态层取消，不会强制中断已经进入 `AgentRunner` 的同步线程；晚返回结果不会覆盖 canceled 状态。

### POST `/a2a/v1/tasks/{task_id}:subscribe`

订阅已有非终态 Task 的后续事件。

**请求示例**

```bash
curl -N -X POST http://localhost:8000/a2a/v1/tasks/task-1:subscribe
```

**响应**

SSE `event: message`，`data` 为 `StreamResponse` JSON。

**常见错误**

| HTTP 状态 | code | 场景 |
|------|------|------|
| `404` | `task_not_found` | Task 不存在 |
| `400` | `unsupported_operation` | Task 已经是终态 |

---

## 6. 错误格式

### Chat API 错误

Chat API 使用 FastAPI `HTTPException` 默认格式：

```json
{
  "detail": "Session not found: <session_id>"
}
```

或：

```json
{
  "detail": "Agent execution failed: <error>"
}
```

### A2A Service 错误

A2A 业务错误使用统一对象：

```json
{
  "detail": {
    "code": "task_not_found",
    "message": "Task not found: task-1"
  }
}
```

当前 code：

| code | HTTP 状态 | 说明 |
|------|------|------|
| `invalid_request` | `400` | 请求语义不支持 |
| `task_not_found` | `404` | Task 不存在 |
| `task_not_cancelable` | `400` | Task 不可取消 |
| `unsupported_operation` | `400` | 当前状态不支持该操作 |
| `unauthorized` | `401` | 扩展 Agent Card 鉴权失败 |
| `extended_agent_card_not_available` | `404` | 扩展 Agent Card 未启用 |

### 参数校验错误

FastAPI/Pydantic schema 校验失败时返回 `422`：

```json
{
  "detail": [
    {
      "type": "missing",
      "loc": ["body", "message"],
      "msg": "Field required",
      "input": {}
    }
  ]
}
```

---

## 7. 认证

当前只有扩展 Agent Card 使用 bearer token：

```http
Authorization: Bearer <A2A_EXTENDED_CARD_TOKEN>
```

其它端点暂未启用认证。生产环境应在 FastAPI 中间件、网关或反向代理层增加认证、限流和审计。

---

## 8. 状态存储

默认实现仍是进程内内存；设置 `STATE_BACKEND=sqlite` 后会使用
`STATE_DB_PATH` 指定的 SQLite 文件：

| 状态 | 默认实现 | SQLite 实现 |
|------|----------|-------------|
| Chat session | `InMemorySessionManager` | `SQLiteSessionManager` |
| Context state | `InMemoryContextStore` | `SQLiteContextStore` |
| Checkpoint | `CheckpointManager` | `SQLiteCheckpointManager` |
| A2A Task | `InMemoryA2ATaskStore` | `SQLiteA2ATaskStore` |
| A2A Event replay log | `A2AEventBroker` | `SQLiteA2AEventBroker` |

SQLite 模式可支持服务重启后恢复 session、provider context、checkpoint
和 A2A task 查询；实时 SSE 订阅 fan-out 仍是进程内行为。

---

## 9. 相关文档

- [QuickStart](QuickStart.md)
- [系统架构](Structure.md)
- [A2A 协议支持说明](a2a.md)
- [ADR-006 A2A Protocol Support](adr/ADR-006-A2A-Protocol-Support.md)

---

*最后更新：2026/05/03*
