import asyncio
import json
import subprocess
from typing import Any

from app.mcp.errors import MCPConnectionError, MCPTimeoutError
from app.mcp.transport.base import BaseTransport


class StdioTransport(BaseTransport):
    def __init__(self, command: list[str], env: dict[str, str] | None = None):
        self.command = command
        self.env = env
        self._process: subprocess.Popen | None = None
        self._lock: asyncio.Lock | None = None

    def connect(self) -> None:
        self._lock = asyncio.Lock()
        self._process = subprocess.Popen(
            self.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=self.env,
            text=True,
            bufsize=1,
        )

    async def send_request(self, request: dict[str, Any], timeout: float) -> dict[str, Any]:
        if self._lock is None:
            raise MCPConnectionError("Transport not connected")
        if self._process is None or self._process.poll() is not None:
            raise MCPConnectionError("Process not running")

        async with self._lock:
            line = json.dumps(request) + "\n"
            self._process.stdin.write(line)
            self._process.stdin.flush()

            try:
                loop = asyncio.get_event_loop()
                result = await asyncio.wait_for(
                    loop.run_in_executor(None, self._process.stdout.readline),
                    timeout=timeout,
                )
                if not result:
                    raise MCPConnectionError("Empty response from MCP server")
                return json.loads(result)
            except asyncio.TimeoutError:
                raise MCPTimeoutError(f"Request timed out after {timeout}s")

    def close(self) -> None:
        if self._process:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait()
            self._process = None
        self._lock = None
