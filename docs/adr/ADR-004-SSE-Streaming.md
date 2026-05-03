# ADR-004: 采用 SSE 实现流式响应而非 WebSocket

## 状态
Accepted

## 背景

Agent 执行过程中需要向客户端实时推送事件（工具调用开始/结束、最终答案）。A2A Task 也需要向客户端持续推送状态和 artifact 更新。客户端需要持续接收服务端推送，而不是轮询。

**需求场景**：
- `/chat/stream` 接口需在 Agent 执行过程中实时推送 `tool_start`、`tool_success`、`final_answer` 等事件
- `/a2a/v1/message:stream` 和 `/a2a/v1/tasks/{task_id}:subscribe` 需推送 A2A `StreamResponse`
- 客户端为标准 HTTP 客户端，需简单接入

## 备选方案

### 方案 A：Server-Sent Events（SSE）
- 服务端单工推送，客户端用 `EventSource` 接收
- 基于 HTTP/1.1，长连接实现简单
- 轻量，适合"服务端→客户端"单向推送场景

### 方案 B：WebSocket
- 全双工通信，可双向读写
- 更复杂，需要心跳维持连接，支持客户端→服务端消息
- 适合实时聊天、协作、游戏等场景

### 方案 C：轮询（Short/Long Polling）
- 客户端定期请求更新
- 实现最简单，但实时性差，开销大

## 决策

采用 **方案 A：Server-Sent Events（SSE）**

通过 `EventChannel`（内部基于 `asyncio.Queue`）实现 `/chat/stream` 事件发布；通过 `A2AEventBroker` 实现 A2A Task 事件日志和多订阅者 fan-out。两类流式接口都返回 `EventSourceResponse`。

## 原因

1. **单向推送足够**：Agent 执行流和 A2A Task 更新不需要客户端在同一连接中反向发送消息，SSE 语义匹配
2. **实现简单**：`EventChannel.publish()` 推送到队列，`stream()` yield 事件即可，无协议握手
3. **HTTP 原生**：SSE 是 HTTP 协议的一部分，可复用现有 HTTP 中间件（认证、日志等）
4. **自动重连**：`EventSource` 客户端自动支持断线重连，开发体验好
5. **避免 WebSocket 复杂度**：无心跳、无双向通信、无协议升级（Upgrade）需求

## 影响

### 收益
- 实现简洁，代码量少
- 可复用 FastAPI 的 `StreamingResponse` 机制
- 浏览器原生支持 `EventSource`，无需前端 SDK

### 代价
- **HTTP/2 限制**：某些浏览器对单域名 SSE 连接数有限制
- **单向通信局限**：若未来需要客户端在同一连接中实时发送消息，需引入 WebSocket 或其他机制
- **不支持跨域**：`EventSource` 默认不支持 CORS，需额外处理

### 技术债
- 尚未实现客户端断开连接时的 Runner 协作式取消机制
- A2A Task cancel 当前是状态层取消，不会强制中断已进入 Runner 的同步线程
- SSE 连接超时需客户端配合处理，当前连接关闭依赖服务端主动结束或终态事件

## 相关链接

- 事件通道实现：[app/core/event_channel.py](app/core/event_channel.py)
- SSE 响应兼容层：[app/core/sse.py](app/core/sse.py)
- SSE Hooks：[app/hooks/sse_hooks.py](app/hooks/sse_hooks.py)
- A2A 事件 broker：[app/a2a/event_broker.py](app/a2a/event_broker.py)
- API 端点：[app/api.py](app/api.py)
