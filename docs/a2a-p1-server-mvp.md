# A2A P1 Server MVP

## Scope

P1 turns the P0 protocol boundary into a minimal A2A HTTP+JSON server while
keeping `AgentRunner` protocol-agnostic.

## Implemented Endpoints

| Method | Path | Behavior |
|------|------|------|
| `GET` | `/.well-known/agent-card.json` | Discovery metadata |
| `POST` | `/a2a/v1/message:send` | Run one A2A message and return a Task |
| `POST` | `/a2a/v1/message:stream` | SSE stream with task, status, artifact, final status |
| `GET` | `/a2a/v1/tasks/{task_id}` | Fetch one Task |
| `GET` | `/a2a/v1/tasks` | List Tasks with context/status pagination filters |

## Runtime Mapping

- A2A `contextId` maps to the existing internal `session_id`.
- A2A `taskId` maps to an in-memory `Task` in `InMemoryA2ATaskStore`.
- A2A text `Message` maps to internal `ChatMessage`.
- `AgentRunResult.success=true` maps to `TASK_STATE_COMPLETED`.
- `AgentRunResult.success=false` maps to `TASK_STATE_FAILED`.

## Supported Request Shape

Only text parts are supported in P1:

```json
{
  "message": {
    "role": "ROLE_USER",
    "parts": [{"text": "hello"}],
    "contextId": "optional-existing-context"
  }
}
```

Set `configuration.returnImmediately=true` to receive a working task while the
runner continues in FastAPI background tasks.

## Limitations

- No push notifications.
- No task cancellation.
- No `tasks/{id}:subscribe` replay stream.
- Stream events are coarse grained: submitted/working/final artifact/final
  status. Tool-level A2A event mapping is left for the next phase.
- Task store is in-memory and process-local.
