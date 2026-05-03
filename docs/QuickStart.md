# Minimal Agent API - QuickStart

## 1. 安装依赖

```bash
pip install -r requirements.txt
```

主要依赖：

| 依赖 | 说明 |
|------|------|
| `fastapi`, `uvicorn` | HTTP API 与 ASGI 服务 |
| `openai` | OpenAI-compatible LLM Client |
| `httpx` | A2A/MCP HTTP Client |
| `pydantic` | API、工具参数、A2A schema |
| `pytest` | 测试 |
| `opentelemetry-*` | 链路追踪 |

## 2. 配置环境变量

在项目根目录创建 `.env`：

```env
LLM_API_KEY=your_api_key_here
LLM_MODEL_ID=qwen3.5-flash
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_TIMEOUT=30
MAX_STEPS=5

# A2A discovery
A2A_PUBLIC_URL=http://localhost:8000
A2A_AGENT_VERSION=0.1.0
A2A_DOCUMENTATION_URL=
A2A_ICON_URL=
A2A_EXTENDED_CARD_TOKEN=
```

`LLM_API_KEY` 必须替换为有效的模型服务 API Key。`A2A_EXTENDED_CARD_TOKEN` 为空时，扩展 Agent Card 端点不可用。

## 3. 启动服务

```bash
uvicorn app.api:app --reload --host 0.0.0.0 --port 8000
```

启动后访问：

- API 文档：http://localhost:8000/docs
- 健康检查：http://localhost:8000/
- A2A Agent Card：http://localhost:8000/.well-known/agent-card.json

## 4. 调用普通 Chat API

### 普通对话

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "你好"}'
```

### 流式对话

```bash
curl -N -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "北京现在几点了"}'
```

### 恢复 checkpoint

```bash
curl -X POST http://localhost:8000/checkpoint/<session_id>/resume
```

## 5. 调用 A2A Server

### 发现 Agent Card

```bash
curl http://localhost:8000/.well-known/agent-card.json
```

### 发送 A2A 消息

```bash
curl -X POST http://localhost:8000/a2a/v1/message:send \
  -H "Content-Type: application/json" \
  -d '{
    "message": {
      "role": "ROLE_USER",
      "parts": [{"text": "介绍一下你的能力"}],
      "contextId": "demo-context"
    }
  }'
```

### A2A 流式执行

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

### 查询、取消、订阅 Task

```bash
curl http://localhost:8000/a2a/v1/tasks/<task_id>

curl -X POST http://localhost:8000/a2a/v1/tasks/<task_id>:cancel \
  -H "Content-Type: application/json" \
  -d '{}'

curl -N -X POST http://localhost:8000/a2a/v1/tasks/<task_id>:subscribe
```

### 扩展 Agent Card

```bash
curl http://localhost:8000/a2a/v1/extendedAgentCard \
  -H "Authorization: Bearer <A2A_EXTENDED_CARD_TOKEN>"
```

## 6. 使用 A2A Client

```python
from app.a2a.client import A2AClient, extract_text_from_send_response

client = A2AClient("http://localhost:8000")
response = client.send_text("你好", context_id="demo-context")
answer = extract_text_from_send_response(response)
```

把远端 A2A Agent 注册为本地工具：

```python
from app.a2a.tool_bridge import register_remote_a2a_agent_tool

register_remote_a2a_agent_tool(
    tool_registry,
    name="remote_research_agent",
    description="Delegate research tasks to a remote A2A agent.",
    base_url="https://remote-agent.example",
)
```

## 7. 内置工具

| 工具 | 参数 | 说明 |
|------|------|------|
| `calculator` | `expression` | 数学表达式计算 |
| `get_current_time` | `city` | 获取城市当前时间 |
| `convert_units` | `value`, `from_unit`, `to_unit` | 单位转换 |
| `analyze_text` | `text` | 文本统计 |
| `get_weather` | `city` | 演示天气 |
| `search_knowledge` | `query`, `top_k` | 本地知识检索 |
| `memory_read` | `scope`, `session_id` | 读取记忆 |
| `memory_append_session_summary` | `session_id`, `summary` | 写入会话记忆 |

## 8. 运行测试

```bash
pytest
pytest tests/a2a -q
pytest tests/core/test_runner.py -q
```

## 9. API 端点一览

更完整的请求/响应模型、SSE 事件和错误格式见：[API 文档](api.md)。

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

*最后更新：2026/05/03*
