import os
from typing import NamedTuple


class MCPServerConfig(NamedTuple):
    name: str
    command: list[str] | None
    env: dict[str, str] | None
    transport: str
    server_url: str | None
    extra_env: dict[str, str] | None


def load_mcp_config() -> list[MCPServerConfig]:
    configs = []
    servers_env = os.getenv("MCP_SERVERS", "")
    if not servers_env:
        return configs

    for server_id in servers_env.split(","):
        server_id = server_id.strip()
        if not server_id:
            continue

        prefix = f"MCP_{server_id.upper()}_"
        name = os.getenv(f"{prefix}NAME", server_id)
        transport = os.getenv(f"{prefix}TRANSPORT", "stdio")

        if transport == "sse":
            server_url = os.getenv(f"{prefix}URL")
            if not server_url:
                continue
            extra_env = {}
            for k, v in os.environ.items():
                if k.startswith(prefix) and k not in (f"{prefix}NAME", f"{prefix}TRANSPORT", f"{prefix}URL"):
                    extra_env[k[len(prefix):]] = v
            configs.append(MCPServerConfig(
                name=name,
                command=None,
                env=None,
                transport=transport,
                server_url=server_url,
                extra_env=extra_env if extra_env else None,
            ))
        else:
            command_str = os.getenv(f"{prefix}COMMAND", "")
            if not command_str:
                continue
            command = command_str.split(",")
            configs.append(MCPServerConfig(
                name=name,
                command=command,
                env=None,
                transport=transport,
                server_url=None,
                extra_env=None,
            ))

    return configs
