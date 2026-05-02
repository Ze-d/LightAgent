# A2A P0 Boundary Design

## Goal

Add an A2A-facing boundary without changing `AgentRunner` or the existing
`/chat` API behavior.

## Implemented Shape

| Area | File | Responsibility |
|------|------|----------------|
| Protocol schemas | `app/a2a/schemas.py` | A2A-facing Pydantic models and constants |
| Agent Card | `app/a2a/agent_card.py` | Builds discovery metadata from local registries |
| Runtime adapter | `app/a2a/adapter.py` | Converts A2A messages/results to internal objects |
| HTTP routes | `app/a2a/routes.py` | Registers A2A discovery routes |
| API integration | `app/api.py` | Includes the A2A router |

## Current Endpoint

`GET /.well-known/agent-card.json`

Returns an A2A Agent Card advertising:
- `protocolVersion`: `1.0`
- `supportedInterfaces`: `HTTP+JSON`
- `capabilities.streaming`: `true`
- local slash skills and registered tool-use capability

The advertised public URL is controlled by:

```env
A2A_PUBLIC_URL=http://localhost:8000
A2A_AGENT_VERSION=0.1.0
```

## Boundary Rule

`app/core/runner.py` remains protocol-agnostic. Future A2A message/task
endpoints should call the existing app-level runner helpers through an adapter,
then store and emit A2A `Task` objects from `app/a2a/`.

## P1 Status

Implemented in P1:
- `POST /a2a/v1/message:send`
- `POST /a2a/v1/message:stream`
- `GET /a2a/v1/tasks/{id}`
- `GET /a2a/v1/tasks`

See `docs/a2a-p1-server-mvp.md`.
