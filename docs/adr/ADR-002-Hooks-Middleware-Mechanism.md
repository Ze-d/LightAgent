# ADR-002: 采用 Hooks + Middleware 双层拦截机制

## 状态
Accepted

## 背景

Agent 执行过程中需要支持用户注入自定义逻辑，例如：
- 日志记录（每次 LLM 调用、工具调用写入日志）
- SSE 事件推送（实时通知客户端工具执行状态）
- 历史消息裁剪（防止上下文超长）
- 工具调用权限控制（黑白名单）

这些需求本质上是"在特定生命周期节点插入逻辑"，但逻辑分为两类：
- **观察型**：只读取状态，不干预执行（如日志、SSE 发布）
- **拦截型**：可以修改输入或中断执行（如裁剪、权限校验）

## 备选方案

### 方案 A：仅用 Hooks 机制
- 所有生命周期节点统一钩子，Hooks 可以修改上下文或抛出异常
- 简单，但语义不清晰

### 方案 B：仅用 Middleware 机制
- Middleware 负责拦截和修改，Hooks 负责观察
- 但 Middleware 无法注册多个

### 方案 C：Hooks + Middleware 双层机制
- **Middleware**：在 `before_llm`、`before_tool` 节点拦截，可修改上下文或抛出 `MiddlewareAbort` 异常中断执行
- **Hooks**：`on_llm_start`、`on_llm_end`、`on_tool_start`、`on_tool_end` 等节点观察，不干预主流程

## 决策

采用 **方案 C：Hooks + Middleware 双层机制**

## 原因

1. **职责分离清晰**：
   - Middleware 负责"修改/拦截"，是执行流程的一部分
   - Hooks 负责"观察/通知"，是执行流程的旁观者
2. **扩展方式明确**：用户想干预执行 → 实现 Middleware；想记录日志 → 实现 Hooks
3. **两条扩展路径互不干扰**：Middlewares 链式调用返回修改后的上下文，Hooks 无返回值不影响主流程
4. **支持异常中断**：通过 `MiddlewareAbort` 异常可以安全地终止执行链

## 影响

### 收益
- 开发者可按需选择扩展点，无需继承核心类
- Hooks 可并行注册多个（如 LoggingHooks + SSEHooks），互不感知
- Middleware 链可中途终止（如权限校验失败），提供短路能力

### 代价
- 学习成本：需要理解两条扩展路径的适用场景
- 轻微性能开销：每次 LLM/工具调用均触发 Middleware 和 Hooks 调用

### 技术债
- 当前 Hooks 和 Middleware 接口均在 `app/core/` 中，是内部接口，未来可能随需求变化调整
- 尚未提供配置化注册机制（目前是代码中硬编码）

## 相关链接

- Hooks 定义：[app/core/hooks.py](app/core/hooks.py)
- Middleware 定义：[app/core/middleware.py](app/core/middleware.py)
- 具体实现：[app/hooks/](app/hooks/) / [app/middleware/](app/middleware/)
