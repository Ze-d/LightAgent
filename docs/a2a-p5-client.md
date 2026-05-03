# A2A P5 Client

## Scope

P5 adds outbound A2A support so MyAgent can call other A2A agents and expose
those remote agents as local tools.

## Implemented

| Capability | Behavior |
|------|------|
| Discovery | `A2AClient.get_agent_card()` reads `/.well-known/agent-card.json` |
| Extended card | `A2AClient.get_extended_agent_card()` uses bearer auth when configured |
| Send message | `send_message()` / `send_text()` call remote `/message:send` |
| Streaming | `stream_message()` / `stream_text()` parse SSE `StreamResponse` events |
| Task operations | `get_task()`, `list_tasks()`, `cancel_task()`, `subscribe_task()` |
| Text extraction | Helpers extract final text from messages, tasks, and send responses |
| Tool bridge | `register_remote_a2a_agent_tool()` registers a remote A2A agent as a local tool |

## Example

```python
from app.a2a.client import A2AClient, extract_text_from_send_response

client = A2AClient("https://remote-agent.example")
response = client.send_text("Summarize this issue", context_id="case-123")
answer = extract_text_from_send_response(response)
```

## Tool Bridge Example

```python
from app.a2a.tool_bridge import register_remote_a2a_agent_tool

register_remote_a2a_agent_tool(
    tool_registry,
    name="remote_research_agent",
    description="Delegate research questions to the remote A2A research agent.",
    base_url="https://remote-agent.example",
    bearer_token="optional-token",
)
```

The registered tool accepts:

```json
{
  "message": "Question or task for the remote agent",
  "context_id": "optional-remote-context"
}
```

## Notes

- Client methods are synchronous and use `httpx`.
- Remote agent registration is explicit; no remote URL is auto-loaded at startup.
- The client chooses the first `HTTP+JSON` interface advertised by the Agent Card.
- Streaming helpers parse SSE `data:` payloads into local `StreamResponse` models.

## Still Out Of Scope

- Async A2A client API
- Automatic remote agent discovery
- Persistent remote context mapping
- Authentication flows beyond bearer token forwarding
