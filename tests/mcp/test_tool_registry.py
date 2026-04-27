import pytest
from unittest.mock import MagicMock, patch
from app.mcp.tool_registry import MCPToolRegistry
from app.core.tool_registry import ToolRegistry
from app.mcp.errors import MCPError


class TestMCPToolRegistryBasics:
    def test_delegates_to_inner_registry(self):
        inner = ToolRegistry()
        registry = MCPToolRegistry(inner)

        assert registry.get_openai_tools() == []
        assert registry.list_names() == []

    def test_call_non_existent_tool_raises(self):
        inner = ToolRegistry()
        registry = MCPToolRegistry(inner)

        with pytest.raises(ValueError, match="Unknown tool"):
            registry.call("nonexistent")

    def test_is_async_for_namespaced_tool(self):
        inner = ToolRegistry()
        registry = MCPToolRegistry(inner)

        assert registry.is_async("some:tool") is True


class TestMCPToolRegistryWithMockClient:
    @patch("app.mcp.tool_registry.MCPClient")
    def test_register_mcp_server(self, mock_client_class):
        mock_client = MagicMock()
        mock_client.name = "zotero"
        mock_client.list_tools.return_value = [
            {
                "name": "search_library",
                "description": "Search Zotero library",
                "inputSchema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                },
            }
        ]
        mock_client_class.return_value = mock_client

        inner = ToolRegistry()
        registry = MCPToolRegistry(inner)

        registry.register_mcp_server(
            name="zotero",
            command=["npx", "mcp-zotero"],
            transport="stdio",
        )

        mock_client.start.assert_called_once()
        mock_client.list_tools.assert_called_once()
        assert "zotero:search_library" in registry.list_names()

    @patch("app.mcp.tool_registry.MCPClient")
    def test_call_mcp_tool(self, mock_client_class):
        mock_client = MagicMock()
        mock_client.name = "zotero"
        mock_client.list_tools.return_value = [
            {
                "name": "search_library",
                "description": "Search",
                "inputSchema": {"type": "object", "properties": {}},
            }
        ]
        mock_client.call_tool.return_value = "Found 5 items"
        mock_client_class.return_value = mock_client

        inner = ToolRegistry()
        registry = MCPToolRegistry(inner)

        registry.register_mcp_server(name="zotero", transport="stdio")

        result = registry.call("zotero:search_library", query="test")
        assert result == "Found 5 items"
        mock_client.call_tool.assert_called_once_with("search_library", {"query": "test"})

    @patch("app.mcp.tool_registry.MCPClient")
    def test_call_inner_tool(self, mock_client_class):
        from app.tools.register import build_default_registry

        inner = build_default_registry()
        registry = MCPToolRegistry(inner)

        # Inner tools should work directly
        assert "calculator" in registry.list_names()
        result = registry.call("calculator", expression="2+2")
        assert result == "4"
