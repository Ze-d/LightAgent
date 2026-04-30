import pytest
import sys
from app.mcp.transport.base import BaseTransport
from app.mcp.transport.stdio import StdioTransport
from app.mcp.transport.sse import SSETransport


class TestStdioTransport:
    def test_connect_with_invalid_command_raises(self):
        transport = StdioTransport(command=["nonexistent-command-xyz"], env=None)
        with pytest.raises(FileNotFoundError):
            transport.connect()
        transport.close()

    def test_connect_creates_process(self):
        transport = StdioTransport(
            command=[sys.executable, "-c", "import time; time.sleep(60)"],
            env=None,
        )
        transport.connect()
        assert transport._process is not None
        assert transport._process.poll() is None
        transport.close()

    def test_close_terminates_process(self):
        transport = StdioTransport(
            command=[sys.executable, "-c", "import time; time.sleep(60)"],
            env=None,
        )
        transport.connect()
        transport.close()
        assert transport._process is None


class TestSSETransport:
    def test_default_headers_empty(self):
        transport = SSETransport(server_url="http://localhost:8080")
        assert transport.headers == {}
        transport.close()

    def test_connect_creates_client(self):
        transport = SSETransport(server_url="http://localhost:8080", headers=None)
        transport.connect()
        assert transport._client is not None
        transport.close()
