# Minimal Agent API 简历项目描述

## 项目名称

Minimal Agent API：支持工具调用、MCP 与 A2A 的 LLM Agent 后端运行时框架

## 项目描述

设计并实现一套轻量级 LLM Agent 后端框架，基于 FastAPI 对外提供 `/chat`、`/chat/stream` 与 A2A HTTP+JSON/SSE 接口，支持多轮会话、Function Calling、工具调用、MCP 工具接入、A2A Agent 间协作、Hooks/Middleware 扩展、记忆管理、限流、超时、重试、熔断、Tracing 与 checkpoint 断点恢复，可用于快速构建具备工具生态和跨 Agent 协作能力的 Agent 服务。

## 技术栈

Python、FastAPI、OpenAI Compatible API、DashScope/Qwen、SSE、Pydantic、httpx、MCP、A2A、OpenTelemetry、Tenacity、Pytest

## 简历要点

- 设计并实现协议无关的 `AgentRunner` 执行循环，支持多步推理、Function Calling、工具结果回灌、最大步数控制、统一错误处理和 checkpoint 快照恢复。
- 基于 FastAPI 构建 Agent 对话服务，提供 `/chat` 与 `/chat/stream`，通过 SSE 实时推送 session 创建、工具调用、最终回答和错误事件。
- 实现 `ToolRegistry`，支持工具 schema 注册、Pydantic 参数校验、同步/异步工具调用和 OpenAI tools 格式转换，内置计算、时间、单位转换、知识检索、记忆读写等工具。
- 接入 MCP 工具生态，封装 `MCPToolRegistry`，支持 stdio/SSE MCP Server 注册、工具命名空间隔离、远程工具动态发现与调用。
- 实现 A2A 协议支持：Agent Card、认证扩展卡、`message:send`、`message:stream`、Task 查询/取消/订阅、事件 broker、Task 生命周期保护。
- 实现 A2A Client 与远端 Agent 工具桥，可读取远端 Agent Card、调用远端 `message:send`/SSE stream，并把远端 A2A Agent 注册为本地工具供 Runner 调用。
- 设计 Hooks 与 Middleware 扩展机制，在 LLM 调用、工具调用、运行生命周期中注入日志、SSE 事件、安全过滤、历史裁剪、工具权限控制等逻辑。
- 引入可靠性治理能力，包括 LLM/工具调用超时、指数退避重试、Token Bucket 限流、Circuit Breaker 熔断，降低外部模型服务和工具异常对主流程的影响。
- 实现会话管理、文件型长期记忆与 checkpoint 机制，支持基于 `session_id` 的上下文维护、历史压缩、会话记忆注入以及异常中断后的状态快照管理。
- 使用 OpenTelemetry 对 Agent 运行链路进行 tracing，覆盖 run、step、LLM、tool 等关键 span。
- 编写 Pytest 单元测试，覆盖 Runner、工具注册、MCP transport、A2A server/client、事件流、会话、checkpoint 和安全校验等核心模块。

## 简历压缩版

**Minimal Agent API | LLM Agent 后端运行时框架**

基于 FastAPI、OpenAI Compatible API 和 DashScope/Qwen 实现轻量级 Agent 后端框架，支持多轮会话、Function Calling、SSE 流式响应、MCP 工具接入、A2A Agent 间协作、Hooks/Middleware、记忆管理、限流、超时、重试、熔断与 checkpoint。负责设计协议无关的 `AgentRunner`、`ToolRegistry`、`MCPToolRegistry`、A2A Server/Client、Task Event Broker 和远端 Agent 工具桥，并使用 Pytest 覆盖 Runner、工具调用、MCP、A2A、会话和断点恢复等核心链路。

## 面试讲法

这个项目的核心不是简单调 LLM API，而是实现一个 Agent Runtime。请求进入 FastAPI 后，会按 `session_id` 或 A2A `contextId` 加载历史，把消息交给 `AgentRunner`。Runner 每一步调用模型，如果模型返回 function call，就通过工具注册中心执行本地工具、MCP 工具或远端 A2A Agent 工具，再把工具结果作为 `function_call_output` 回灌给模型继续推理，直到得到最终回答或达到最大步数。

A2A 层没有侵入 Runner，而是在外层负责 Agent Card、Task Store、Task 生命周期、SSE 事件 broker 和 Client 适配。这样同一套 Runner 可以同时服务传统 `/chat` 客户端和 A2A 客户端，也可以把远端 A2A Agent 当作工具纳入本地推理流程。

---

*最后更新：2026/05/03*
