# ADR - Architecture Decision Records

架构决策记录，记录项目中重要、难以回滚、影响系统结构或质量属性的决策。

---

## 决策索引

| ADR | 标题 | 状态 | 日期 |
|-----|------|------|------|
| [ADR-001](ADR-001-InMemory-Session-Storage.md) | 采用内存存储作为会话管理方案 | Accepted | 2026/04/14 |
| [ADR-002](ADR-002-Hooks-Middleware-Mechanism.md) | 采用 Hooks + Middleware 双层拦截机制 | Accepted | 2026/04/14 |
| [ADR-003](ADR-003-DashScope-API.md) | 采用 DashScope API（阿里云）作为 LLM 后端 | Accepted | 2026/04/14 |
| [ADR-004](ADR-004-SSE-Streaming.md) | 采用 SSE 实现流式响应而非 WebSocket | Accepted | 2026/04/14 |
| [ADR-005](ADR-005-Single-Process-Architecture.md) | 采用单体架构，暂不分库分表和微服务拆分 | Accepted | 2026/04/14 |

---

## 撰写原则

1. **只记录重要的**：架构决策应是难以回滚的、影响系统质量属性的
2. **追加而非覆盖**：决策变更时新建 ADR 并 `Superseded by` 指向新作，而非修改原文档
3. **格式统一**：包含状态、背景、备选方案、决策、原因、影响、相关链接
4. **聚焦原因**：重点写清楚"为什么这样选"和"代价是什么"

---

## 新增 ADR

新增时使用下一可用编号（当前最大为 005）：
- 文件名：`ADR-00X-Title.md`
- 编号连续递增，不复用旧编号
