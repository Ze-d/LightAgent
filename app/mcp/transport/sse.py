import asyncio
import httpx
from typing import Any

from app.mcp.transport.base import BaseTransport


class SSETransport(BaseTransport):
    def __init__(
        self,
        server_url: str,
        headers: dict[str, str] | None = None,
    ):
        self.server_url = server_url
        self.headers = headers or {}
        self._client: httpx.AsyncClient | None = None

    def connect(self) -> None:
        self._client = httpx.AsyncClient(base_url=self.server_url, headers=self.headers)

    async def send_request(self, request: dict[str, Any], timeout: float) -> dict[str, Any]:
        if self._client is None:
            raise RuntimeError("Transport not connected")

        response = await self._client.post(
            "/mcp",
            json=request,
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()

    def close(self) -> None:
        if self._client:
            asyncio.run(self._client.aclose())
            self._client = None
