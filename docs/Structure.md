# Minimal Agent - 系统架构文档

## 1. 系统上下游

```
上游：用户 / 客户端应用
        │
        ▼
┌─────────────────────────────────┐
│        Minimal Agent API        │  ← 本系统
│        (FastAPI + Python)        │
└─────────────────────────────────┘
        │
        ▼
下游：DashScope API（阿里云 LLM）
```

| 方向 | 组件 | 说明 |
|------|------|------|
| **上游** | 用户 / 客户端 | HTTP POST 请求，通过 `/chat` 或 `/chat/stream` 接入 |
| **下游** | DashScope API | 阿里云 LLM 服务（OpenAI 兼容接口），实际模型为 qwen3.5-flash |

---

## 2. 核心模块

| 模块 | 路径 | 职责 |
|------|------|------|
| **api** | `app/api.py` | FastAPI 入口，定义 `/chat` 和 `/chat/stream` 端点 |
| **agents** | `app/agents/` | Agent 核心抽象：BaseAgent, ChatAgent, ToolAwareAgent |
| **core/runner** | `app/core/runner.py` | AgentRunner，核心运行循环，多步推理 + 工具调用 |
| **core/tool_registry** | `app/core/tool_registry.py` | 工具注册与调用管理 |
| **core/session_manager** | `app/core/session_manager.py` | 会话存储抽象（InMemory 实现） |
| **core/event_channel** | `app/core/event_channel.py` | SSE 事件通道，异步队列 |
| **core/hooks** | `app/core/hooks.py` | 生命周期钩子机制 |
| **core/middleware** | `app/core/middleware.py` | 中间件机制，拦截 LLM/工具调用 |
| **hooks** | `app/hooks/` | 钩子实现：LoggingHooks, SSEHooks |
| **middleware** | `app/middleware/` | 中间件实现：HistoryTrimMiddleware, ToolPermissionMiddleware |
| **tools** | `app/tools/` | 内置工具：calculator, get_current_time |

---

## 3. 数据流

### 对话请求处理流程

```
HTTP POST /chat 或 /chat/stream
    │
    ▼
ChatRequest { message, session_id? }
    │
    ▼
会话管理（创建/加载）→ InMemorySessionManager
    │
    ▼
追加用户消息到 history
    │
    ▼
ToolAwareAgent + AgentRunner.run()
    │
    ├── middleware.before_llm()      # 可拦截
    ├── client.responses.create()    # 调用 LLM
    ├── 解析 function_call
    │
    └── 如有工具调用:
         ├── middleware.before_tool()  # 可拦截
         └── tool_registry.call()      # 执行工具
    │
    ▼
返回 AgentRunResult { answer, success, steps, tool_events }
    │
    ▼
保存会话 + 返回响应
```

---

## 4. 外部依赖

| 依赖 | 类型 | 说明 |
|------|------|------|
| **DashScope API** | 外部服务 | 阿里云 LLM（gpt-5.4-mini 接口，实际 qwen3.5-flash） |
| **openai** | Python 库 | OpenAI 兼容客户端 |
| **python-dotenv** | Python 库 | .env 环境变量加载 |
| **InMemorySessionManager** | 内存存储 | 会话存储（无持久化） |

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LLM_API_KEY` | 必填 | DashScope API 密钥 |
| `LLM_MODEL_ID` | `gpt-5.4-mini` | 模型名称 |
| `LLM_BASE_URL` | 阿里云地址 | API 服务地址 |
| `MAX_STEPS` | `5` | Agent 最大执行步数 |

---

## 5. 部署拓扑

```
┌─────────────────────────────┐
│      客户端 / 用户           │
└──────────┬──────────────────┘
           │ HTTP
           ▼
┌─────────────────────────────┐
│   FastAPI (uvicorn)        │
│   Host: 0.0.0.0:8000        │
│                             │
│  ┌───────────────────────┐  │
│  │  Minimal Agent API    │  │
│  │  - /chat              │  │
│  │  - /chat/stream (SSE) │  │
│  └───────────────────────┘  │
└──────────┬──────────────────┘
           │ HTTPS
           ▼
┌─────────────────────────────┐
│    DashScope API            │
│    (阿里云 LLM)              │
└─────────────────────────────┘
```

**部署形态**：传统 Python 进程（无容器化）

**启动命令**：
```bash
uvicorn app.api:app --reload --host 0.0.0.0 --port 8000
```

---

## 6. 核心链路

### 请求 → 响应完整链路

```
1. 客户端 POST /chat { message, session_id? }
         │
         ▼
2. 会话管理
   - session_id 为空 → 创建新会话
   - session_id 有值 → 加载历史消息
         │
         ▼
3. AgentRunner.run() 执行循环（最多 MAX_STEPS=5 步）
   - 每步：LLM 推理 → 工具调用（如有）→ 结果收集
         │
         ▼
4. SSEHooks 发布事件（流式模式）
   - tool_start / tool_success / tool_error
   - final_answer / error
         │
         ▼
5. 保存会话到内存，返回 ChatResponse
```

### 工具调用链路

```
AgentRunner 发现 function_call
         │
         ▼
middleware.before_tool() 拦截检查
         │
         ▼
ToolRegistry.call(tool_name, arguments)
         │
         ▼
内置工具执行 (calculator / get_current_time)
         │
         ▼
ToolCallEvent 收集 → 返回给 LLM 继续推理
```

---

## 7. 内置工具清单

| 工具名 | 参数 | 说明 |
|--------|------|------|
| `calculator` | `expression: str` | 数学表达式计算 |
| `get_current_time` | `city: str` | 获取城市当前时间 |

---

*最后更新：2026/04/14*
