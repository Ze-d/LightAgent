import asyncio
import json
from typing import Any

from app.mcp.errors import (
    MCPConnectionError,
    MCPTimeoutError,
    MCPToolNotFoundError,
)
from app.mcp.transport.base import BaseTransport
from app.mcp.transport.stdio import StdioTransport
from app.mcp.transport.sse import SSETransport


class MCPClient:
    def __init__(
        self,
        name: str,
        command: list[str] | None = None,
        env: dict[str, str] | None = None,
        transport: str = "stdio",
        server_url: str | None = None,
        timeout: float = 30.0,
    ):
        self.name = name
        self.command = command or []
        self.env = env or {}
        self.timeout = timeout
        self._transport: BaseTransport | None = None
        self._initialized = False
        self._protocol_version = "2024-11-05"

        if transport == "stdio":
            if not command:
                raise ValueError("command required for stdio transport")
            self._transport = StdioTransport(command, env)
        elif transport == "sse":
            if not server_url:
                raise ValueError("server_url required for SSE transport")
            self._transport = SSETransport(server_url)
        else:
            raise ValueError(f"Unknown transport: {transport}")

    def start(self) -> None:
        if self._transport is None:
            raise MCPConnectionError("Transport not initialized")
        self._transport.connect()
        self._send_initialize()
        self._initialized = True

    def _send_initialize(self) -> dict[str, Any]:
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": self._protocol_version,
                "capabilities": {},
                "clientInfo": {
                    "name": "minimal-agent",
                    "version": "1.0.0",
                },
            },
        }
        return self._send_request(request)

    def list_tools(self) -> list[dict[str, Any]]:
        if not self._initialized:
            self.start()

        request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {},
        }
        response = self._send_request(request)
        return response.get("result", {}).get("tools", [])

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        if not self._initialized:
            self.start()

        request = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        }

        try:
            response = self._send_request(request, timeout=self.timeout)
            result = response.get("result", {})

            content = result.get("content", [])
            if isinstance(content, list):
                return "\n".join(
                    item.get("text", str(item)) for item in content
                )
            return str(result)
        except asyncio.TimeoutError:
            raise MCPTimeoutError(f"Tool '{tool_name}' timed out after {self.timeout}s")

    def _send_request(self, request: dict[str, Any], timeout: float | None = None) -> dict[str, Any]:
        if self._transport is None:
            raise MCPConnectionError("Transport not initialized")

        timeout = timeout or self.timeout

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(
            self._transport.send_request(request, timeout)
        )

    def stop(self) -> None:
        if self._transport:
            self._transport.close()
            self._initialized = False
