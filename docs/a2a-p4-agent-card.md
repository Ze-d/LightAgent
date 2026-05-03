# A2A P4 Agent Card

## Scope

P4 upgrades Agent Card discovery from a minimal card to a richer public card
plus an optional authenticated extended card.

## Implemented

| Capability | Behavior |
|------|------|
| Public card | `GET /.well-known/agent-card.json` |
| Extended card | `GET /a2a/v1/extendedAgentCard` when `A2A_EXTENDED_CARD_TOKEN` is set |
| Auth | Extended card requires `Authorization: Bearer <token>` |
| Dynamic URL | If `A2A_PUBLIC_URL` is unset, card URLs use the request base URL |
| Security metadata | `securitySchemes` and `securityRequirements` are modeled |
| Rich metadata | `iconUrl`, `documentationUrl`, interfaces, extensions, and skill security fields |
| Tool detail split | Public card advertises generic tool use; extended card exposes tool-level skills |

## Environment

```env
A2A_PUBLIC_URL=http://localhost:8000
A2A_AGENT_VERSION=0.1.0
A2A_DOCUMENTATION_URL=
A2A_ICON_URL=
A2A_EXTENDED_CARD_TOKEN=
```

Leave `A2A_PUBLIC_URL` empty to derive URLs from the incoming request origin.
Set `A2A_EXTENDED_CARD_TOKEN` to enable the extended card endpoint.

## Public Card

The public card intentionally avoids sensitive implementation detail. It
advertises high-level chat, slash-skill, and registered-tool capabilities.

## Extended Card

The extended card uses bearer auth and includes tool-level skill entries. It is
intended for trusted clients that need a more precise capability inventory.

## Still Out Of Scope

- Signed Agent Cards
- Multi-tenant Agent Interfaces
- Per-skill auth requirements beyond inherited card-level bearer auth

Outbound A2A client support was added in P5. See `docs/a2a-p5-client.md`.
