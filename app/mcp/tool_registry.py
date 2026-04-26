from typing import Any

from app.core.tool_registry import ToolRegistry
from app.core.resilience import CircuitBreaker, CircuitBreakerOpenError
from app.mcp.client import MCPClient
from app.mcp.errors import MCPError
from app.obj.types import ToolSpec


class MCPToolRegistry:
    def __init__(self, inner_registry: ToolRegistry):
        self._inner = inner_registry
        self._mcp_clients: dict[str, MCPClient] = {}
        self._circuit_breakers: dict[str, CircuitBreaker] = {}

    def register_mcp_server(
        self,
        name: str,
        command: list[str] | None = None,
        env: dict[str, str] | None = None,
        transport: str = "stdio",
        server_url: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        client = MCPClient(
            name=name,
            command=command,
            env=env,
            transport=transport,
            server_url=server_url,
            timeout=timeout,
        )
        client.start()

        mcp_tools = client.list_tools()
        for mcp_tool in mcp_tools:
            spec = self._mcp_tool_to_spec(client, mcp_tool)
            self._inner.register(spec)

        self._mcp_clients[name] = client

    def _mcp_tool_to_spec(self, client: MCPClient, mcp_tool: dict[str, Any]) -> ToolSpec:
        namespaced_name = f"{client.name}:{mcp_tool['name']}"
        description = mcp_tool.get("description", "")
        parameters = mcp_tool.get("inputSchema", {})

        def handler(**kwargs: Any) -> str:
            return client.call_tool(mcp_tool["name"], kwargs)

        return ToolSpec(
            name=namespaced_name,
            description=description,
            parameters=parameters,
            handler=handler,
        )

    def _get_cb(self, client_name: str) -> CircuitBreaker:
        if client_name not in self._circuit_breakers:
            self._circuit_breakers[client_name] = CircuitBreaker(
                name=f"mcp_{client_name}",
                failure_threshold=5,
                timeout_seconds=60.0,
            )
        return self._circuit_breakers[client_name]

    def get_openai_tools(self) -> list[dict[str, Any]]:
        return self._inner.get_openai_tools()

    def call(self, name: str, **kwargs: Any) -> str:
        if ":" in name:
            client_name, tool_name = name.split(":", 1)
            client = self._mcp_clients.get(client_name)
            if client is None:
                raise ValueError(f"Unknown MCP client: {client_name}")
            cb = self._get_cb(client_name)

            def do_call() -> str:
                return client.call_tool(tool_name, kwargs)

            try:
                return cb.call(do_call)
            except CircuitBreakerOpenError:
                raise MCPError(f"MCP server '{client_name}' is temporarily unavailable")
        return self._inner.call(name, **kwargs)

    async def call_async(self, name: str, **kwargs: Any) -> str:
        if ":" in name:
            client_name, tool_name = name.split(":", 1)
            client = self._mcp_clients.get(client_name)
            if client is None:
                raise ValueError(f"Unknown MCP client: {client_name}")
            return client.call_tool(tool_name, kwargs)
        return await self._inner.call_async(name, **kwargs)

    def is_async(self, name: str) -> bool:
        if ":" in name:
            return True
        return self._inner.is_async(name)

    def list_names(self) -> list[str]:
        return self._inner.list_names()
