# A2A P3 Streaming Events

## Scope

P3 adds a shared A2A task event broker so streaming message requests and task
subscriptions observe the same ordered lifecycle events.

## Implemented

| Capability | Behavior |
|------|------|
| Event broker | `A2AEventBroker` stores ordered `StreamResponse` events per task |
| Live fan-out | Multiple subscribers to the same task receive the same events |
| Message stream reuse | `/a2a/v1/message:stream` creates a task, subscribes, then runs it |
| Task subscribe | `POST /a2a/v1/tasks/{task_id}:subscribe` streams an existing non-terminal task |
| Terminal close | completed, failed, canceled, or rejected status closes subscribers |
| Error mapping | subscribing to a terminal task returns `400 unsupported_operation` |

## Event Order

For a normal text request:

```
Task snapshot
  -> statusUpdate TASK_STATE_WORKING
  -> artifactUpdate final-answer
  -> statusUpdate TASK_STATE_COMPLETED final=true
```

If a task is canceled while subscribed:

```
Task snapshot
  -> statusUpdate TASK_STATE_CANCELED final=true
```

## Notes

- Event storage is in-memory and process-local.
- The broker logs task events even when there are no active subscribers.
- `tasks/{id}:subscribe` starts with the current task snapshot, then only live
  events after subscription. Event replay APIs are kept internal for now.
- Tool-level events are still not mapped into A2A streaming events.

Agent Card discovery was expanded in P4. See `docs/a2a-p4-agent-card.md`.
