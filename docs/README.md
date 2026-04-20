# Minimal Agent API

基于 FastAPI 的轻量级 Agent 对话框架，支持工具调用、会话管理、SSE 流式响应、Hooks 与 Middleware 扩展机制。

---

## 项目做什么

本项目实现了一个 **LLM Agent 运行时框架**，核心能力包括：

- **对话管理**：支持多轮会话，基于 session_id 维护上下文历史
- **工具调用**：内置工具注册中心，支持 Agent 动态调用外部工具（如计算器、时间查询）
- **SSE 流式响应**：`/chat/stream` 接口支持 Server-Sent Events，实时推送执行事件
- **可扩展架构**：提供 Hooks（钩子）和 Middleware（中间件）机制，支持在 Agent 运行生命周期中注入自定义逻辑

---

## 面向谁

- 希望快速搭建 LLM Agent 对话服务的开发者
- 需要在 Agent 流程中嵌入自定义逻辑（鉴权、日志、裁剪等）的二次开发者
- 学习 Agent 运行时设计模式（工具调用、Hooks、Middleware）的实践者

---

## 核心能力

| 能力 | 说明 |
|------|------|
| **Agent 运行时** | 基于 OpenAI Responses API 的 Agent 执行循环，支持多步推理和工具调用 |
| **工具注册中心** | `ToolRegistry` 管理工具定义与执行，内置 `calculator`、`get_current_time` |
| **会话管理** | `SessionManager` 抽象会话存储，默认提供 `InMemorySessionManager` |
| **Hooks 机制** | 在 `run_start`、`llm_start`、`llm_end`、`tool_end` 等生命周期节点插入逻辑 |
| **Middleware 机制** | 在 LLM 调用前/工具调用前拦截和修改上下文，支持 `before_llm`、`before_tool` |
| **SSE 流式** | `/chat/stream` 通过 `EventChannel` 实现实时事件推送 |

---

## 本地启动方式

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

创建 `.env` 文件（参考 `.env`）：

```env
LLM_MODEL_ID=qwen3.5-flash
LLM_API_KEY=your_api_key_here
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_TIMEOUT=60
MAX_STEPS=5
```

### 3. 启动服务

```bash
uvicorn app.api:app --reload --host 0.0.0.0 --port 8000
```

访问 http://localhost:8000/docs 查看 FastAPI 自动生成的交互文档。

---

## 目录结构

```
MyAgent/
├── app/
│   ├── api.py                 # FastAPI 入口，定义 /chat 和 /chat/stream 接口
│   ├── agents/
│   │   ├── agent_base.py      # BaseAgent 抽象类
│   │   ├── chat_agent.py      # ChatAgent 实现
│   │   └── tool_aware_agent.py# 工具感知 Agent，收集工具调用事件
│   ├── configs/
│   │   ├── config.py          # 环境变量配置（LLM_API_KEY, LLM_MODEL_ID 等）
│   │   └── logger.py          # 日志配置
│   ├── core/
│   │   ├── runner.py          # AgentRunner，核心运行循环
│   │   ├── tool_registry.py   # ToolRegistry，工具注册与调用
│   │   ├── session_manager.py # BaseSessionManager / InMemorySessionManager
│   │   ├── event_channel.py   # EventChannel，SSE 事件通道
│   │   ├── hooks.py           # BaseRunnerHooks / CompositeRunnerHooks
│   │   └── middleware.py      # BaseRunnerMiddleware / CompositeRunnerMiddleware
│   ├── hooks/
│   │   ├── logging_hooks.py    # LoggingHooks，日志记录实现
│   │   └── sse_hooks.py       # SSEHooks，SSE 事件发布
│   ├── middleware/
│   │   ├── history_trim_middleware.py    # 历史裁剪中间件
│   │   └── tool_permission_middleware.py  # 工具权限控制中间件
│   ├── tools/
│   │   ├── builtin_tools.py    # 内置工具：calculator, get_current_time
│   │   └── register.py        # build_default_registry 工厂函数
│   ├── listener/
│   │   ├── log_listener.py     # 日志监听器
│   │   └── sse_listener.py     # SSE 监听器
│   ├── obj/
│   │   ├── schemas.py          # Pydantic 请求/响应模型
│   │   └── types.py            # 类型定义（Event、Message 等）
│   ├── prompts/
│   │   └── prompt.py           # SYSTEM_PROMPT 系统提示词
│   ├── storage/
│   │   └── session_store.py    # Session 存储接口
│   ├── exceptions/
│   │   └── agent.py            # Agent 相关异常定义
│   └── middleware/            # Middleware 模块（别名）
├── docs/                       # 项目文档
├── requirements.txt           # Python 依赖
└── .env                        # 环境变量（本地）
```

---

## 常见命令

| 命令 | 说明 |
|------|------|
| `uvicorn app.api:app --reload` | 启动开发服务器（热重载） |
| `uvicorn app.api:app --host 0.0.0.0 --port 8000` | 生产环境启动 |
| `pytest` | 运行单元测试 |
| `pytest -v` | 详细模式运行测试 |

---

## 相关文档入口

| 文档 | 说明 |
|------|------|
| [FastAPI 文档](https://fastapi.tiangolo.com/) | Web 框架 |
| [OpenAI Responses API](https://platform.openai.com/docs/api-reference/responses) | LLM 接口 |
| [阿里云 DashScope](https://dashscope.console.aliyun.com/) | 通义千问 API 服务 |

---

## 负责人 / 维护人

| 角色 | 职责 |
|------|------|
| **Maintainer** | 项目整体架构设计与核心实现 |

---

> 如有使用问题或贡献想法，欢迎提交 Issue 或 Pull Request。
