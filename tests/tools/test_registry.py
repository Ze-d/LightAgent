from app.tools.register import build_default_registry


def test_registry_contains_default_tools():
    registry = build_default_registry()
    names = registry.list_names()

    assert "calculator" in names
    assert "get_current_time" in names
    assert "convert_units" in names
    assert "analyze_text" in names
    assert "get_weather" in names
    assert "search_knowledge" in names
    assert "memory_read" in names
    assert "memory_append_session_summary" in names


def test_registry_generates_openai_tools():
    registry = build_default_registry()
    tools = registry.get_openai_tools()

    names = [tool["name"] for tool in tools]
    assert "calculator" in names
    assert "get_current_time" in names
    assert "convert_units" in names
    assert "analyze_text" in names
    assert "get_weather" in names
    assert "search_knowledge" in names
    assert "memory_read" in names
    assert "memory_append_session_summary" in names

    for tool in tools:
        assert tool["type"] == "function"


def test_registry_call_calculator():
    registry = build_default_registry()
    result = registry.call("calculator", expression="2 + 3")
    assert result == "5"
