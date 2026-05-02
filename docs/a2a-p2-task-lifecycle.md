# A2A P2 Task Lifecycle

## Scope

P2 completes the server-side lifecycle mapping for the current synchronous
runner architecture.

## Implemented

| Capability | Behavior |
|------|------|
| Cancel task | `POST /a2a/v1/tasks/{task_id}:cancel` |
| Terminal protection | Completed, failed, canceled, and rejected tasks cannot be overwritten |
| Late background completion guard | A canceled task remains canceled even if a background runner returns later |
| Terminal append guard | New messages cannot be appended to terminal tasks by `taskId` |
| Not cancelable error | Completed, failed, or rejected tasks return `400 task_not_cancelable` |

## Lifecycle Mapping

```
message accepted
  -> TASK_STATE_SUBMITTED
  -> TASK_STATE_WORKING
  -> TASK_STATE_COMPLETED | TASK_STATE_FAILED | TASK_STATE_CANCELED
```

## Notes

`AgentRunner` is still synchronous and does not expose cooperative cancellation.
Canceling a task therefore means the A2A task state is canceled immediately, and
any late runner result is ignored by the task store.

## Still Out Of Scope

- `tasks/{id}:subscribe`
- push notification callbacks
- cooperative cancellation inside `AgentRunner`
- persistent task storage
