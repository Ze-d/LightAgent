# ADR-005: 采用单体架构，暂不分库分表和微服务拆分

## 状态
Accepted

## 背景

随着 Agent 对话场景扩展，系统面临扩展性选择：
- **会话存储**：当前是 InMemory，未来是否需要 Redis 持久化？
- **A2A Task/Event 存储**：当前是 InMemory，未来是否需要跨实例共享？
- **服务拆分**：是否需要拆成 API 层、Agent 运行时层、LLM 网关层？
- **多实例部署**：是否需要支持 uvicorn 多进程？

当前系统定位为**轻量级 Agent 运行时框架**，面向快速启动和二次开发。

## 备选方案

### 方案 A：单体架构（当前选择）
- 所有模块运行在单一 Python 进程中
- InMemory 会话，InMemory 工具注册中心
- InMemory A2A Task Store 与 Event Broker
- 简单部署：`uvicorn app.api:app`

### 方案 B：引入 Redis + 多进程 uvicorn
- 会话存储在 Redis，多实例共享
- 引入 Redis 运维依赖
- 需要处理分布式 session 过期同步

### 方案 C：微服务拆分
- 拆分为 API 服务、Agent 运行服务、LLM 网关服务
- 各服务独立部署和扩展
- 引入服务间通信（HTTP/gRPC）和分布式事务复杂度

## 决策

采用 **方案 A：单体架构**，暂不引入 Redis 和微服务拆分。

## 原因

1. **最小化复杂度**：当前阶段系统的核心价值是 Agent 运行逻辑，而非基础设施
2. **快速迭代**：引入 Redis/微服务会显著增加开发、测试、部署的复杂度
3. **规模尚未达到**：单实例 InMemory 完全可支撑中小规模场景，过早优化是万恶之源
4. **接口已抽象**：核心接口（`BaseSessionManager`、`BaseRunnerHooks`）已预留扩展点，未来需要时可在不破坏接口的情况下替换实现

## 影响

### 收益
- 零额外运维依赖（只需 Python + FastAPI）
- 开发、测试、部署流程极简
- 调试简单，跨模块调用无网络开销

### 代价
- **水平扩展受限**：无法通过多实例部署提升并发处理能力
- **单点故障**：进程崩溃后所有会话丢失
- **资源竞争**：单进程内 LLM API 调用和工具执行共享 CPU/内存

### 技术债

| 场景 | 当前状态 | 未来升级路径 |
|------|----------|--------------|
| 多实例部署 | 不可行 | 实现 `RedisSessionManager`、持久化 A2A Task Store 与 Event Log |
| 会话持久化 | 进程重启丢失 | 会话写入 Redis，进程重启后可恢复 |
| A2A Task 持久化 | 进程重启丢失 | Task/Event 写入 Redis、SQLite 或 Postgres |
| 服务拆分 | 不可行 | 按模块边界拆分为独立服务，通过 HTTP/gRPC 通信 |
| 高可用 | 无保障 | 引入多实例 + Redis + 负载均衡 |

## 相关链接

- 会话管理抽象：[app/core/session_manager.py](app/core/session_manager.py)
- 当前 InMemory 实现：同上
- 系统架构文档：[docs/Structure.md](docs/Structure.md)
