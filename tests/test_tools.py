from app.tools import calculator, get_current_time, TOOLS, TOOL_MAP


def test_calculator_basic():
    assert calculator("2 + 3") == "5"


def test_calculator_multiply():
    assert calculator("23 * 47") == "1081"


def test_calculator_invalid_expression():
    result = calculator("2 +")
    assert "Calculation error" in result

def test_get_current_time_known_city():
    result = get_current_time("Tokyo")
    assert isinstance(result, str)
    assert len(result) >= 8
    assert "Unknown city" not in result


def test_get_current_time_unknown_city():
    result = get_current_time("Mars")
    assert result == "Unknown city: Mars"

def test_tool_map_contains_expected_tools():
    assert "calculator" in TOOL_MAP
    assert "get_current_time" in TOOL_MAP


def test_tools_schema_contains_expected_names():
    names = [tool["name"] for tool in TOOLS]
    assert "calculator" in names
    assert "get_current_time" in names


def test_tools_schema_type_is_function():
    for tool in TOOLS:
        assert tool["type"] == "function"