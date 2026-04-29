# Minimal Agent API — 项目数值指标

> 统计日期：2026-04-28 | 基线提交：16 commits on main

---

## 1. 代码规模

| 指标 | 数值 |
|------|------|
| Python 源文件 (`app/`) | **56** 个 |
| 源代码行数 (`app/`) | **3,572** 行 |
| 测试文件 (`tests/`) | **18** 个 |
| 测试代码行数 | **1,872** 行 |
| 测试用例数 | **109** 个 |
| 总类数量 | **53** 个 |
| 测试/源码行数比 | **0.52 : 1** |

---

## 2. 模块构成

| 目录 | 文件数 | 职责 |
|------|--------|------|
| `app/core/` | 13 | Runner、ToolRegistry、Session、Hooks、Middleware、Resilience、Tracing、RateLimiter、Checkpoint、Skill |
| `app/tools/` | 5 | 内置工具、记忆工具、沙箱校验、注册工厂 |
| `app/mcp/` | 5 | MCP Client、Config、Errors、ToolRegistry、Transport (stdio + SSE) |
| `app/agents/` | 3 | BaseAgent、ChatAgent、ToolAwareAgent |
| `app/hooks/` | 2 | LoggingHooks、SSEHooks |
| `app/middleware/` | 2 | HistoryTrim、ToolPermission |
| `app/memory/` | 2 | Summarizer、DocumentStore |
| `app/skills/` | 3 | simplify、loop、注册工厂 |
| `app/security/` | 1 | InputGuard |
| `app/obj/` | 2 | Pydantic Schemas、TypedDict Types |
| `app/configs/` | 2 | 配置、日志 |
| `app/prompts/` | 1 | System Prompt |
| `app/exceptions/` | 1 | Agent 异常定义 |

---

## 3. API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/chat` | POST | 普通对话接口 |
| `/chat/stream` | POST | SSE 流式对话接口 |

---

## 4. 内置工具

| 工具名 | 参数 | 类型 |
|--------|------|------|
| `calculator` | `expression: str` | 计算 |
| `get_current_time` | `city: str` | 时间 |
| `convert_units` | `value, from_unit, to_unit` | 单位转换 |
| `analyze_text` | `text: str` | 文本分析 |
| `get_weather` | `city: str` | 天气 |
| `search_knowledge` | `query, top_k` | 知识检索 |
| `memory_read` | — | 记忆读取 |
| `memory_append_session_summary` | — | 记忆写入 |

**总计：8 个工具**

---

## 5. 内置 Skills

| Skill | 参数 |
|-------|------|
| `simplify` | `code`, `target` (readability/performance/safety) |
| `loop` | `interval`, `command`, `max_rounds` |

**总计：2 个 Skill**

---

## 6. 类型体系

| 类型 | 数量 | 位置 |
|------|------|------|
| TypedDict | **11** 个 | `app/obj/types.py` |
| Pydantic BaseModel | **4** 个 | `app/obj/schemas.py` |
| 异常类 | **3+** 个 | `resilience.py` + `agent.py` |

---

## 7. 运行时配置参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `LLM_TIMEOUT` | **30 s** | LLM API 调用超时 |
| `MAX_STEPS` | **5** | Agent 最大推理步数 |
| `DEFAULT_MAX_RETRIES` | **3** | LLM/工具调用最大重试 |
| 重试退避（min） | **1 s** | 指数退避起始等待 |
| 重试退避（max） | **10 s** | 指数退避上限 |
| 熔断 failure_threshold | **5** | 连续失败触发 OPEN |
| 熔断 timeout_seconds | **60 s** | OPEN→HALF_OPEN 等待 |
| Token Bucket rate | **10 req/s** | 示例配置 |
| Token Bucket capacity | = rate | 默认等于 rate |
| 消息压缩 target_messages | **10** | 超过后触发裁剪 |
| 压缩摘要字数上限 | **≤100 字** | LLM 模式 |

---

## 8. 知识库规模

| 类型 | 数量 |
|------|------|
| 支持城市（时间查询） | **5** 个 (tokyo, beijing, shanghai, london, new york) |
| 支持天气城市 | **5** 个 (beijing, shanghai, tokyo, london, new york) |
| 长度单位 | **8** 种 (m, km, cm, mm, inch, foot, yard, mile) |
| 质量单位 | **4** 种 (g, kg, ounce, pound) |
| 温度单位 | **3** 种 (celsius, fahrenheit, kelvin) |
| 单位别名总数 | **42** 个 |
| 知识库条目 | **4** 条 |

---

## 9. MCP 传输层

| 传输方式 | 说明 |
|----------|------|
| `stdio` | 标准输入输出进程通信 |
| `SSE` | Server-Sent Events HTTP 通信 |

---

## 10. 中间件 & Hooks

| 组件 | 数量 |
|------|------|
| Before LLM 拦截点 | **3** (RateLimiter, InputGuard, HistoryTrim) |
| Before Tool 拦截点 | **1** (ToolPermission) |
| Runner Hooks 生命周期节点 | **6** (run_start/end, llm_start/end, tool_end, error) |
| Hook 实现 | **2** (LoggingHooks, SSEHooks) |

---

## 11. 外部依赖

| 依赖 | 数量 | 关键项 |
|------|------|--------|
| Python 库 | **12** 个 | fastapi, uvicorn, openai, pydantic, tenacity, opentelemetry(×4), pytest, python-dotenv |
| 外部 LLM 服务 | **1** 个 | DashScope (阿里云 qwen3.5-flash) |
| 可选可观测导出 | **1** 个 | OpenTelemetry OTLP |

---

## 12. Git 历史

| 指标 | 数值 |
|------|------|
| 总提交数 | **16** |
| 最近提交 | 2026-04-28 |
| 功能提交占比 | ~100%（纯 feature 仓库） |

---

## 13. 测试覆盖分布

| 测试模块 | 文件数 | 覆盖内容 |
|----------|--------|----------|
| `tests/agents/` | 2 | ChatAgent, ToolAwareAgent |
| `tests/core/` | 6 | Runner, EventEmission, Session, Checkpoint, ToolSuccessRate, ToolSelectionAccuracy |
| `tests/mcp/` | 4 | Config, Errors, ToolRegistry, Transport |
| `tests/tools/` | 3 | Registry, Validator, ToolSuccessRate |
| `tests/` root | 2 | 新功能, 工具集成 |

---

*统计脚本：`find app/ -name "*.py" | wc -l` · `grep -rn "def test_" tests/ | wc -l` · `git rev-list --count HEAD`*
