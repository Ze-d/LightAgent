# Checkpoint 恢复机制增强计划

## 背景

当前 Checkpoint 机制已实现基础的保存和恢复功能（见 `app/core/checkpoint.py`），但在实现断点续算增强时存在恢复不完整的问题。

## 当前实现

- [CheckpointManager](../app/core/checkpoint.py): 内存存储 `session_id → Checkpoint[]`
- [Checkpoint 数据结构](../app/core/checkpoint.py): 包含 `step`, `history`, `agent_state`, `timestamp`
- [Agent 状态管理](../app/agents/tool_aware_agent.py): `get_state()` / `restore_state()` 保存 `tool_event_history`

> **注意**: 基础 Checkpoint 保存/恢复功能已实现，以下增强计划用于解决断点续算时的重复执行问题。

## 问题分析

### 问题 1: Runner 没有跳过已完成的 Steps

```python
# app/core/runner.py:83
for step in range(1, self.max_steps + 1):  # ← 始终从 1 开始！
```

**现状**: 恢复时 `checkpoint.step = 3`，但 runner **仍然从 step 1 开始循环**

**影响**: 已完成的 steps 会被重复执行

### 问题 2: Checkpoint 保存时机不完整

```python
# 保存时机只有两处:
# 1. 无 function_call 返回时 (正常完成)
if not function_calls:
    checkpoint_manager.save(...)

# 2. for 循环结束时 (max_steps 到达)
current_input = next_input
checkpoint_manager.save(...)
```

**缺失场景**:
- Tool 执行**过程中**中断 → checkpoint 未保存
- LLM 调用超时 → `with_timeout` 抛出异常 → checkpoint 未保存

### 问题 3: 重复执行风险

```
Step 1: LLM → need tool: "send_email"
        checkpoint 保存 (step=1, history 包含 tool call)
        ⚠️ 中断

恢复后:
- history 恢复到 step 1 之前
- agent_state 恢复
- runner 从 step 1 开始
  → LLM 再次返回 need tool: "send_email"
  → tool 再次执行 → 重复发送邮件！
```

### 问题 4: 缺少跳过逻辑

理论上应该是:
```python
start_step = checkpoint.step + 1  # 从下一个 step 继续
```

但当前代码没有这个逻辑。

---

## 修复方案

### 方案 A: 增强 Runner 支持断点续算 (推荐)

#### Step 1: 修改 Checkpoint 数据结构

```python
# app/core/checkpoint.py
@dataclass
class Checkpoint:
    step: int
    history: list[ChatMessage]
    agent_state: dict[str, Any]
    pending_function_calls: list[FunctionCallOutput] = []  # 新增: 待处理的函数调用结果
    timestamp: datetime = field(default_factory=datetime.now)
```

#### Step 2: 修改 Runner 签名

```python
# app/core/runner.py
def run(
    self,
    agent: BaseAgent,
    history: list[ChatMessage],
    tool_registry: ToolRegistry | None = None,
    hooks: BaseRunnerHooks | None = None,
    session_id: str | None = None,
    checkpoint_manager: CheckpointManager | None = None,
    resume_from_step: int = 1,  # 新增: 从哪个 step 开始
    pending_function_outputs: list[FunctionCallOutput] = None,  # 新增: 待处理的函数输出
) -> AgentRunResult:
```

#### Step 3: 修改 Runner 跳过逻辑

```python
# app/core/runner.py
for step in range(resume_from_step, self.max_steps + 1):
    # 如果有 pending_function_outputs，跳过 LLM 调用，直接处理这些输出
    if pending_function_outputs is not None and pending_function_outputs:
        current_input = pending_function_outputs
        pending_function_outputs = None  # 清空，防止下次循环误用
        # 跳过 LLM 调用，继续处理 tool 执行
        goto_process_function_calls = True
    else:
        # 正常 LLM 调用流程
        ...
```

#### Step 4: 修改 Checkpoint 保存时机

在更多位置保存 checkpoint:
- `with_timeout` 异常捕获中
- 每个 tool 执行完成后
- middleware 抛出 `MiddlewareAbort` 时

#### Step 5: 修改 API 恢复逻辑

```python
# app/api.py
checkpoint = checkpoint_manager.load(session_id)
if checkpoint:
    resume_from_step = checkpoint.step + 1
    pending_function_outputs = checkpoint.pending_function_calls
```

### 方案 B: 简化方案 - Tool 调用去重

在 `ToolAwareAgent` 或 middleware 层实现基于 `call_id` 的去重:

```python
class ToolAwareAgent(ChatAgent):
    def __init__(self, ...):
        self._executed_calls: set[str] = set()

    def on_tool_event(self, event: ToolCallEvent) -> None:
        call_id = event.get("call_id")
        if call_id and call_id in self._executed_calls:
            return  # 跳过重复调用
        self._executed_calls.add(call_id)
        self.tool_event_history.append(event)
```

---

## 待办事项

- [ ] **P0** 修改 Checkpoint 数据结构，增加 `pending_function_calls` 字段
- [ ] **P0** 修改 Runner.run() 签名，增加 `resume_from_step` 和 `pending_function_outputs` 参数
- [ ] **P0** 修改 Runner 循环逻辑，支持跳过已执行的 steps
- [ ] **P1** 在 API 层正确传递 `resume_from_step` 和 `pending_function_outputs`
- [ ] **P1** 增强 Checkpoint 保存时机，Tool 执行异常时也保存
- [ ] **P2** 添加 Tool 去重机制（方案 B），作为备份保护
- [ ] **P2** 编写集成测试，验证断点续算场景
- [ ] **P2** 更新文档，说明 Checkpoint 限制和恢复语义

---

## 验收标准

1. 模拟 LLM 超时场景，第二次请求能从断点恢复
2. 验证恢复后已执行的 Tool 不会被重复调用
3. `pending_function_calls` 能正确传递已执行但未完成处理的函数输出
4. 现有 59 个单元测试全部通过
5. 新增集成测试覆盖断点续算场景

---

## 相关文件

- `app/core/checkpoint.py` - CheckpointManager
- `app/core/runner.py` - AgentRunner
- `app/agents/agent_base.py` - BaseAgent 状态接口
- `app/agents/tool_aware_agent.py` - ToolAwareAgent 状态实现
- `app/api.py` - HTTP 端点
- `tests/core/test_checkpoint.py` - 现有单元测试
