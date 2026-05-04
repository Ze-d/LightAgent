# ADR-006: 支持 A2A 协议作为 Agent 间协作边界

## 状态

Accepted

## 背景

MyAgent 原本只提供 `/chat` 和 `/chat/stream`，适合作为单 Agent 对话服务。随着多 Agent 协作需求增加，需要一个标准协议让其他 Agent 或平台发现本系统能力、提交任务、订阅任务状态，并让本系统调用远端 Agent。

同时项目已支持 MCP。MCP 更适合工具/资源接入，A2A 更适合 Agent 间任务协作，两者职责不同。

## 备选方案

### 方案 A：自定义多 Agent HTTP API

- 实现简单，完全按项目需要设计。
- 缺点是互操作性弱，客户端和远端 Agent 都需要定制适配。

### 方案 B：只使用 MCP

- 复用已有 MCP 工具接入。
- 缺点是 MCP 语义偏工具/资源，不表达 Agent Card、Task 生命周期、Task 订阅等 Agent 间协作概念。

### 方案 C：支持 A2A 协议

- 标准 Agent Card 发现。
- 标准 message/task API。
- 支持 SSE 流式事件和 Task 订阅。
- 可作为 Server 被外部 Agent 调用，也可作为 Client 调用远端 Agent。

## 决策

采用 **方案 C：支持 A2A 协议**。

实现约束：

- `app/core/runner.py` 保持协议无关。
- 所有 A2A 模型、Task Store、Event Broker、Server routes、Client 和 Tool Bridge 都放在 `app/a2a/`。
- A2A `contextId` 映射到内部 `session_id`。
- A2A cancel 当前只取消 Task 状态，不强制中断已进入 Runner 的同步线程。

## 原因

1. **互操作性**：Agent Card、message/task API 可被标准 A2A Client 发现和调用。
2. **边界清晰**：A2A 层只做协议适配，Runner 不被协议细节污染。
3. **与 MCP 互补**：MCP 管工具，A2A 管 Agent 协作。
4. **渐进落地**：可以先内存 Task Store 和 SSE broker，未来再换持久化实现。
5. **双向能力**：本系统既可暴露为 A2A Server，也可用 `A2AClient` 调用远端 Agent。

## 影响

### 收益

- 支持跨 Agent 协作和远端 Agent 工具桥。
- 支持 Task 状态查询、取消、订阅。
- 公开 Agent Card 和认证扩展 Agent Card。
- 保持旧 `/chat` API 兼容。

### 代价

- 增加 `app/a2a/` 协议层复杂度。
- Task Store/Event Broker 当前是内存实现，不适合多实例共享。
- 需要维护 A2A schema 与官方协议演进的兼容。

### 技术债

| 场景 | 当前状态 | 未来升级路径 |
|------|------|------|
| Task 持久化 | SQLite 可配置 | Redis/Postgres Task Store |
| 事件 replay | SQLite 可配置 | replay API |
| Runner 取消 | 协作式 cancellation token | 客户端断开连接联动取消 |
| A2A Client | 同步 httpx | 增加 async client |
| 远端 Agent 注册 | 手动注册 | 配置化 Remote Agent Registry |

## 相关链接

- A2A 实现：`app/a2a/`
- A2A 文档：`docs/a2a.md`
- 系统架构：`docs/Structure.md`
