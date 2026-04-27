import os
import pytest
from app.mcp.config import MCPServerConfig, load_mcp_config


class TestMCPServerConfig:
    def test_config_creation(self):
        config = MCPServerConfig(
            name="test",
            command=["npx", "mcp-server"],
            env=None,
            transport="stdio",
            server_url=None,
            extra_env=None,
        )
        assert config.name == "test"
        assert config.command == ["npx", "mcp-server"]
        assert config.transport == "stdio"

    def test_sse_config_with_extra_env(self):
        config = MCPServerConfig(
            name="zotero",
            command=None,
            env=None,
            transport="sse",
            server_url="http://localhost:23120/mcp",
            extra_env={"API_KEY": "test123"},
        )
        assert config.transport == "sse"
        assert config.extra_env == {"API_KEY": "test123"}


class TestLoadMCPConfig:
    def test_no_servers_returns_empty(self, monkeypatch):
        monkeypatch.delenv("MCP_SERVERS", raising=False)
        configs = load_mcp_config()
        assert configs == []

    def test_single_stdio_server(self, monkeypatch):
        monkeypatch.setenv("MCP_SERVERS", "test")
        monkeypatch.setenv("MCP_TEST_NAME", "my-test")
        monkeypatch.setenv("MCP_TEST_COMMAND", "npx,mcp-server")
        monkeypatch.setenv("MCP_TEST_TRANSPORT", "stdio")

        configs = load_mcp_config()
        assert len(configs) == 1
        assert configs[0].name == "my-test"
        assert configs[0].command == ["npx", "mcp-server"]
        assert configs[0].transport == "stdio"

    def test_sse_server_with_extra_env(self, monkeypatch):
        monkeypatch.setenv("MCP_SERVERS", "zotero")
        monkeypatch.setenv("MCP_ZOTERO_TRANSPORT", "sse")
        monkeypatch.setenv("MCP_ZOTERO_URL", "http://localhost:23120/mcp")
        monkeypatch.setenv("MCP_ZOTERO_API_KEY", "secret123")

        configs = load_mcp_config()
        assert len(configs) == 1
        assert configs[0].transport == "sse"
        assert configs[0].server_url == "http://localhost:23120/mcp"
        assert configs[0].extra_env == {"API_KEY": "secret123"}

    def test_multiple_servers(self, monkeypatch):
        monkeypatch.setenv("MCP_SERVERS", "server1,server2")
        monkeypatch.setenv("MCP_SERVER1_COMMAND", "npx,server1")
        monkeypatch.setenv("MCP_SERVER1_TRANSPORT", "stdio")
        monkeypatch.setenv("MCP_SERVER2_TRANSPORT", "sse")
        monkeypatch.setenv("MCP_SERVER2_URL", "http://localhost:8080")

        configs = load_mcp_config()
        assert len(configs) == 2

    def test_sse_without_url_skipped(self, monkeypatch):
        monkeypatch.setenv("MCP_SERVERS", "bad")
        monkeypatch.setenv("MCP_BAD_TRANSPORT", "sse")
        # No URL set

        configs = load_mcp_config()
        assert configs == []
