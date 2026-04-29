# Minimal Agent API 简历项目描述

## 项目名称

Minimal Agent API：基于 FastAPI 的 LLM Agent 后端运行时框架

## 项目描述

设计并实现一套轻量级 LLM Agent 后端框架，基于 FastAPI 对外提供 `/chat` 与 `/chat/stream` 接口，支持多轮会话、工具调用、SSE 流式事件、MCP 工具接入、Hooks/Middleware 扩展、记忆管理、限流、超时、重试、熔断与断点恢复等能力，可用于快速构建具备工具调用能力的 Agent 服务。

## 技术栈

Python、FastAPI、OpenAI Compatible API、DashScope/Qwen、SSE、Pydantic、MCP、OpenTelemetry、Tenacity、Pytest

## 简历要点

- 设计并实现 Agent 执行循环 `AgentRunner`，支持多步推理、Function Calling、工具结果回灌、最大步数控制和统一错误处理，完成从用户请求到 LLM 推理、工具执行、最终回答的完整链路。
- 基于 FastAPI 构建 Agent 对话服务，提供普通对话接口 `/chat` 与 SSE 流式接口 `/chat/stream`，通过异步事件通道实时推送 session 创建、工具调用、最终回答和错误事件。
- 实现工具注册中心 `ToolRegistry`，支持工具 schema 注册、Pydantic 参数校验、同步/异步工具调用和 OpenAI tools 格式转换，内置计算、时间、单位转换、知识检索、记忆读写等工具。
- 接入 MCP 工具生态，封装 `MCPToolRegistry`，支持 stdio/SSE MCP Server 注册、工具命名空间隔离、远程工具动态发现与调用，并为 MCP 服务增加熔断保护。
- 设计 Hooks 与 Middleware 扩展机制，在 LLM 调用、工具调用、运行生命周期中注入日志、SSE 事件、安全过滤、历史裁剪、工具权限控制等逻辑，提升框架可扩展性。
- 引入可靠性治理能力，包括 LLM/工具调用超时、指数退避重试、Token Bucket 限流、Circuit Breaker 熔断，降低外部模型服务和工具异常对主流程的影响。
- 实现会话管理、文件型长期记忆与 checkpoint 机制，支持基于 `session_id` 的上下文维护、历史压缩、会话记忆注入以及异常中断后的状态快照管理。
- 使用 OpenTelemetry 对 Agent 运行链路进行 tracing，覆盖 LLM 调用、工具执行、step 级执行过程，便于定位慢调用和异常链路。
- 编写 Pytest 单元测试，覆盖工具注册、MCP transport、Agent Runner、会话管理、checkpoint、工具调用成功率和工具选择准确率等核心模块。

## 简历压缩版

**Minimal Agent API | LLM Agent 后端运行时框架**

基于 FastAPI、OpenAI Compatible API 和 DashScope/Qwen 实现轻量级 Agent 后端框架，支持多轮会话、Function Calling、SSE 流式响应、MCP 工具接入、Hooks/Middleware 扩展、记忆管理、限流、超时、重试、熔断与 checkpoint。负责设计 AgentRunner 执行循环、ToolRegistry 工具注册中心、MCPToolRegistry 远程工具适配层和 EventChannel 流式事件通道，并使用 Pytest 覆盖 Runner、工具调用、MCP、会话和断点恢复等核心链路。

## 面试讲法

这个项目的核心不是简单调 LLM API，而是实现一个 Agent Runtime。请求进入 FastAPI 后，会按 `session_id` 加载历史，把消息交给 `AgentRunner`。Runner 每一步调用模型，如果模型返回 function call，就通过工具注册中心执行工具，再把工具结果作为 `function_call_output` 回灌给模型继续推理，直到得到最终回答或达到最大步数。

我还做了 SSE 事件流、Middleware 拦截、Hooks 生命周期扩展、MCP 工具接入和熔断重试等工程化能力，目标是让 Agent 服务具备可扩展、可观测、可治理的后端架构。
