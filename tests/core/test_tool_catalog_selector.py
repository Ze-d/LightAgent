import pytest

from app.core.tool_registry import ToolRegistry
from app.core.tool_selection import (
    HeuristicToolSelector,
    ScopedToolRegistryView,
    ToolCatalog,
    ToolMetadata,
    ToolSelectionRequest,
)


def _tool(
    name: str,
    description: str,
    *,
    namespace: str = "local",
    source_type: str = "local",
    tags: tuple[str, ...] = (),
    enabled: bool = True,
    health_state: str = "healthy",
):
    return ToolMetadata(
        name=name,
        description=description,
        parameters={"type": "object", "properties": {}},
        side_effect_policy="read_only",
        namespace=namespace,
        source_type=source_type,
        tags=frozenset(tags),
        enabled=enabled,
        health_state=health_state,
    )


def test_tool_catalog_can_be_built_from_registry():
    registry = ToolRegistry()
    registry.register({
        "name": "calculator",
        "description": "Evaluate arithmetic expressions.",
        "parameters": {"type": "object", "properties": {}},
        "handler": lambda: "ok",
    })

    catalog = ToolCatalog.from_registry(registry)

    assert catalog.count == 1
    assert catalog.get("calculator").description == "Evaluate arithmetic expressions."
    assert catalog.get("calculator").namespace == "local"
    assert catalog.get("calculator").source_type == "local"


def test_selector_filters_unhealthy_disabled_and_side_effect_tools():
    catalog = ToolCatalog()
    catalog.register(_tool("calculator", "Evaluate arithmetic expressions.", tags=("math",)))
    catalog.register(_tool("disabled_math", "Evaluate math but disabled.", enabled=False))
    catalog.register(_tool("broken_math", "Evaluate math but unavailable.", health_state="circuit_open"))
    catalog.register(ToolMetadata(
        name="write_memory",
        description="Write memory facts.",
        parameters={"type": "object", "properties": {}},
        side_effect_policy="non_idempotent",
        namespace="local",
        source_type="local",
        tags=frozenset({"memory"}),
    ))
    selector = HeuristicToolSelector(max_tools=5, allow_side_effects=False)

    result = selector.select(
        catalog,
        ToolSelectionRequest(query="calculate a math expression"),
    )

    assert result.selected_names == ["calculator"]
    assert "disabled_math" in result.filtered_names
    assert "broken_math" in result.filtered_names
    assert "write_memory" in result.filtered_names


def test_selector_respects_namespace_cap_and_always_include():
    catalog = ToolCatalog()
    catalog.register(_tool("memory_search", "Search memory.", tags=("memory",)))
    catalog.register(_tool("mcp:github:search_issues", "Search GitHub issues.", namespace="mcp:github", source_type="mcp"))
    catalog.register(_tool("mcp:github:create_issue", "Create GitHub issue.", namespace="mcp:github", source_type="mcp"))
    catalog.register(_tool("mcp:github:list_pull_requests", "List GitHub pull requests.", namespace="mcp:github", source_type="mcp"))
    selector = HeuristicToolSelector(
        max_tools=4,
        namespace_cap=2,
        always_include=("memory_search",),
    )

    result = selector.select(
        catalog,
        ToolSelectionRequest(query="github issue pull request"),
    )

    assert result.selected_names[0] == "memory_search"
    github_tools = [
        name for name in result.selected_names if name.startswith("mcp:github:")
    ]
    assert "mcp:github:list_pull_requests" in github_tools
    assert len(github_tools) <= 2
    assert result.namespace_counts["mcp:github"] <= 2


def test_selector_caps_remote_namespaces_without_capping_local_tools():
    catalog = ToolCatalog()
    for name, description in [
        ("extract_keywords", "Extract keywords from text."),
        ("dedupe_lines", "Remove duplicate lines."),
        ("sort_items", "Sort items."),
        ("render_markdown_table", "Render a Markdown table."),
    ]:
        catalog.register(_tool(name, description))
    for name in [
        "mcp:github:search_issues",
        "mcp:github:create_issue",
        "mcp:github:list_pull_requests",
    ]:
        catalog.register(_tool(
            name,
            "GitHub issue pull request tool.",
            namespace="mcp:github",
            source_type="mcp",
        ))
    selector = HeuristicToolSelector(max_tools=10, namespace_cap=2)

    result = selector.select(
        catalog,
        ToolSelectionRequest(
            query=(
                "extract keywords, remove duplicate lines, sort items, "
                "render a Markdown table, and use GitHub issue tools"
            ),
        ),
    )

    assert {
        "extract_keywords",
        "dedupe_lines",
        "sort_items",
        "render_markdown_table",
    } <= set(result.selected_names)
    assert result.namespace_counts["local"] == 4
    assert result.namespace_counts["mcp:github"] == 2


def test_scoped_registry_view_exposes_and_executes_only_selected_tools():
    registry = ToolRegistry()
    registry.register({
        "name": "calculator",
        "description": "Evaluate arithmetic expressions.",
        "parameters": {"type": "object", "properties": {}},
        "handler": lambda: "4",
    })
    registry.register({
        "name": "delete_file",
        "description": "Delete a file.",
        "parameters": {"type": "object", "properties": {}},
        "handler": lambda: "deleted",
    })
    view = ScopedToolRegistryView(registry, ["calculator"])

    assert [tool["name"] for tool in view.get_openai_tools()] == ["calculator"]
    assert view.list_names() == ["calculator"]
    assert view.call("calculator") == "4"
    with pytest.raises(ValueError, match="not selected"):
        view.call("delete_file")
