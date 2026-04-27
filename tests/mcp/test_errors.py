import pytest

from app.mcp.errors import (
    MCPError,
    MCPConnectionError,
    MCPTimeoutError,
    MCPProtocolError,
    MCPToolNotFoundError,
)


class TestMCPErrorHierarchy:
    def test_error_base_class(self):
        assert issubclass(MCPError, Exception)

    def test_connection_error(self):
        assert issubclass(MCPConnectionError, MCPError)

    def test_timeout_error(self):
        assert issubclass(MCPTimeoutError, MCPError)

    def test_protocol_error(self):
        assert issubclass(MCPProtocolError, MCPError)

    def test_tool_not_found_error(self):
        assert issubclass(MCPToolNotFoundError, MCPError)

    def test_can_raise_and_catch(self):
        with pytest.raises(MCPError):
            raise MCPConnectionError("Connection failed")
