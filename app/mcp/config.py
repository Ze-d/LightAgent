import os
from typing import NamedTuple


class MCPServerConfig(NamedTuple):
    name: str
    command: list[str] | None
    env: dict[str, str] | None
    transport: str
    server_url: str | None


def load_mcp_config() -> list[MCPServerConfig]:
    configs = []
    servers_env = os.getenv("MCP_SERVERS", "")
    if not servers_env:
        return configs

    for server_id in servers_env.split(","):
        server_id = server_id.strip()
        if not server_id:
            continue

        name = os.getenv(f"MCP_{server_id.upper()}_NAME", server_id)
        transport = os.getenv(f"MCP_{server_id.upper()}_TRANSPORT", "stdio")

        if transport == "sse":
            server_url = os.getenv(f"MCP_{server_id.upper()}_URL")
            if not server_url:
                continue
            configs.append(MCPServerConfig(
                name=name,
                command=None,
                env=None,
                transport=transport,
                server_url=server_url,
            ))
        else:
            command_str = os.getenv(f"MCP_{server_id.upper()}_COMMAND", "")
            if not command_str:
                continue
            command = command_str.split(",")
            configs.append(MCPServerConfig(
                name=name,
                command=command,
                env=None,
                transport=transport,
                server_url=None,
            ))

    return configs
