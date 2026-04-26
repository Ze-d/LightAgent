# Loop Skill 功能完善计划

## 概述

当前 `loop_skill.py` 是一个示例实现，只验证参数并返回确认信息。要实现真正的循环执行功能，需要进一步完善。

---

## 当前状态

| 项目 | 状态 |
|------|------|
| Slash command 解析 | ✅ 完成 |
| 参数验证 | ✅ 完成 |
| 循环调度执行 | ❌ 未实现 |
| 取消循环 | ❌ 未实现 |
| 持久化 | ❌ 未实现 |

---

## 待实现功能

### 1. 循环调度器 (Loop Scheduler)

需要一个后台调度器来管理循环任务：

```python
# app/core/loop_scheduler.py
import asyncio
from typing import Callable

class LoopScheduler:
    def schedule(self, skill_name: str, interval: str, command: str, max_rounds: int | None) -> str:
        """Schedule a recurring task and return a loop_id"""

    def cancel(self, loop_id: str) -> bool:
        """Cancel a scheduled loop"""

    def list_active(self) -> list[dict]:
        """List all active loops"""
```

### 2. 持久化 Loop 状态

Loops 需要持久化到 checkpoint 或数据库：

```python
@dataclass
class LoopState:
    loop_id: str
    skill_name: str
    interval: str
    command: str
    max_rounds: int | None
    current_round: int
    next_run: datetime
    status: Literal["active", "paused", "completed", "cancelled"]
```

### 3. 取消 Loop Skill

需要添加 `/stop` 或 `/cancel` skill：

```python
# app/skills/stop_skill.py
async def stop(loop_id: str) -> str:
    """Cancel a running loop by its ID"""
```

### 4. 查询 Loop 状态

添加 `/loops` 或 `/list-loops` skill：

```python
# app/skills/list_loops_skill.py
async def list_loops() -> str:
    """List all active loops"""
```

---

## 实现步骤

- [ ] 创建 `app/core/loop_scheduler.py`
- [ ] 实现基于 asyncio 的后台调度
- [ ] 添加 LoopState 数据结构
- [ ] 将 loop 状态持久化到 CheckpointManager
- [ ] 实现 `/stop` skill
- [ ] 实现 `/loops` skill (查看活动中的循环)
- [ ] 添加钩子支持 (on_loop_start, on_loop_end, on_loop_iteration)
- [ ] 编写测试

---

## API 扩展

可选：添加 REST API 端点

```
GET  /loops              # 列出所有活动中的循环
POST /loops/{loop_id}/cancel  # 取消指定循环
```

---

## 使用示例

```
# 创建循环
/loop interval=5m command=/health-check max_rounds=100

# 查看活动循环
/loops

# 取消循环
/stop loop_id=xxx123
```

---

## 依赖

- `asyncio` (标准库)
- 可选：`APScheduler` 用于更强大的调度
