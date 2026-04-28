"""Unit tests for tool call success rate."""
import json

import pytest

from app.tools.register import build_default_registry
from app.obj.types import AgentRunResult


class TestCalculatorToolSuccessRate:
    """Test calculator tool success rate."""

    @pytest.fixture
    def registry(self):
        return build_default_registry()

    def test_calculator_valid_expressions(self, registry):
        """Test calculator with valid expressions should succeed 100%."""
        test_cases = [
            ("2 + 3", "5"),
            ("10 * 10", "100"),
            ("100 - 1", "99"),
            ("20 / 4", "5"),
            ("2 ** 8", "256"),
            ("(5 + 3) * 2", "16"),
        ]

        success_count = 0
        total = len(test_cases)

        for expression, expected in test_cases:
            result = registry.call("calculator", expression=expression)
            if result == expected:
                success_count += 1

        success_rate = success_count / total
        assert success_rate == 1.0, f"Expected 100% success rate, got {success_rate}"
        print(f"Calculator valid expressions success rate: {success_count}/{total} = {success_rate:.1%}")

    def test_calculator_invalid_expressions_return_errors(self, registry):
        """Test calculator with invalid expressions returns error, not exception."""
        invalid_cases = [
            "abc",
            "os.system('ls')",
            "import os",
            "print(1)",
        ]

        error_handled_count = 0
        total = len(invalid_cases)

        for expression in invalid_cases:
            result = registry.call("calculator", expression=expression)
            if "error" in result.lower() or "Calculation error" in result:
                error_handled_count += 1

        error_handling_rate = error_handled_count / total
        assert error_handling_rate == 1.0, f"Expected 100% error handling, got {error_handling_rate}"
        print(f"Calculator invalid expressions error handling rate: {error_handled_count}/{total} = {error_handling_rate:.1%}")

    def test_calculator_mixed_expressions(self, registry):
        """Test calculator overall success rate with mixed inputs."""
        mixed_cases = [
            ("2 + 3", True, "5"),
            ("10 * 10", True, "100"),
            ("abc", False, None),
            ("(5 + 3) * 2", True, "16"),
            ("os.system('ls')", False, None),
        ]

        total = len(mixed_cases)
        expected_success = sum(1 for _, should_succeed, _ in mixed_cases if should_succeed)

        actual_success = 0
        for expression, should_succeed, expected in mixed_cases:
            result = registry.call("calculator", expression=expression)
            if should_succeed and result == expected:
                actual_success += 1
            elif not should_succeed and ("error" in result.lower() or "Calculation error" in result):
                actual_success += 1

        success_rate = actual_success / total
        print(f"Calculator mixed expressions: {actual_success}/{total} = {success_rate:.1%} (expected success: {expected_success}/{total})")
        assert success_rate == 1.0


class TestGetCurrentTimeToolSuccessRate:
    """Test get_current_time tool success rate."""

    @pytest.fixture
    def registry(self):
        return build_default_registry()

    def test_get_current_time_known_cities(self, registry):
        """Test get_current_time with known cities should succeed 100%."""
        known_cities = ["beijing", "shanghai", "tokyo", "london", "new york"]

        success_count = 0
        total = len(known_cities)

        for city in known_cities:
            result = registry.call("get_current_time", city=city)
            if "Unknown city" not in result and "error" not in result.lower():
                success_count += 1

        success_rate = success_count / total
        assert success_rate == 1.0, f"Expected 100% success rate, got {success_rate}"
        print(f"Get current time known cities success rate: {success_count}/{total} = {success_rate:.1%}")

    def test_get_current_time_unknown_city(self, registry):
        """Test get_current_time with unknown city returns proper error."""
        result = registry.call("get_current_time", city="invalid_city_xyz_123")
        assert "Unknown city" in result
        print(f"Unknown city returns proper error: '{result}'")

    def test_get_current_time_case_insensitive(self, registry):
        """Test get_current_time handles case-insensitive city names."""
        variations = ["Beijing", "BEIJING", "Beijing", "beijing"]

        success_count = 0
        for city in variations:
            result = registry.call("get_current_time", city=city)
            if "Unknown city" not in result:
                success_count += 1

        success_rate = success_count / len(variations)
        print(f"Case insensitive city lookup: {success_count}/{len(variations)} = {success_rate:.1%}")
        assert success_rate == 1.0


class TestExtendedToolSuccessRate:
    """Test deterministic built-in tools across several domains."""

    @pytest.fixture
    def registry(self):
        return build_default_registry()

    def test_convert_units_success_cases(self, registry):
        test_cases = [
            ({"value": 2.5, "from_unit": "kilometer", "to_unit": "meter"}, "2500"),
            ({"value": 100, "from_unit": "centimeter", "to_unit": "meter"}, "1"),
            ({"value": 32, "from_unit": "fahrenheit", "to_unit": "celsius"}, "0"),
            ({"value": 1, "from_unit": "kilogram", "to_unit": "gram"}, "1000"),
        ]

        success_count = 0
        for args, expected in test_cases:
            result = registry.call("convert_units", **args)
            if result == expected:
                success_count += 1

        success_rate = success_count / len(test_cases)
        assert success_rate == 1.0

    def test_analyze_text_counts(self, registry):
        result = registry.call("analyze_text", text="hello world\nsecond line")
        parsed = json.loads(result)

        assert parsed["words"] == 4
        assert parsed["lines"] == 2
        assert parsed["characters"] == len("hello world\nsecond line")

    def test_get_weather_supported_city(self, registry):
        result = registry.call("get_weather", city="beijing")
        parsed = json.loads(result)

        assert parsed["city"] == "beijing"
        assert "condition" in parsed
        assert "temperature_c" in parsed

    def test_search_knowledge_finds_relevant_record(self, registry):
        result = registry.call("search_knowledge", query="checkpoint middleware tool calls")
        parsed = json.loads(result)

        assert parsed
        assert any(item["title"] == "AgentRunner" for item in parsed)

    def test_extended_tools_error_handling(self, registry):
        test_cases = [
            ("convert_units", {"value": 1, "from_unit": "meter", "to_unit": "second"}, "Unsupported"),
            ("get_weather", {"city": "unknown_city"}, "Unknown city"),
            ("search_knowledge", {"query": ""}, "[]"),
        ]

        success_count = 0
        for tool_name, args, expected_fragment in test_cases:
            result = registry.call(tool_name, **args)
            if expected_fragment in result:
                success_count += 1

        success_rate = success_count / len(test_cases)
        assert success_rate == 1.0


class TestToolSuccessRateSummary:
    """Summary of tool call success rate metrics."""

    @pytest.fixture
    def registry(self):
        return build_default_registry()

    def test_overall_tool_success_rate(self, registry):
        """Calculate overall tool success rate across all tools and scenarios."""
        test_scenarios = [
            ("calculator", {"expression": "2 + 3"}, True),
            ("calculator", {"expression": "10 * 10"}, True),
            ("calculator", {"expression": "100 - 1"}, True),
            ("calculator", {"expression": "abc"}, False),
            ("get_current_time", {"city": "beijing"}, True),
            ("get_current_time", {"city": "shanghai"}, True),
            ("get_current_time", {"city": "tokyo"}, True),
            ("get_current_time", {"city": "invalid_city"}, False),
            ("convert_units", {"value": 2, "from_unit": "km", "to_unit": "m"}, True),
            ("convert_units", {"value": 2, "from_unit": "km", "to_unit": "second"}, False),
            ("analyze_text", {"text": "hello world"}, True),
            ("get_weather", {"city": "beijing"}, True),
            ("get_weather", {"city": "invalid_city"}, False),
            ("search_knowledge", {"query": "ToolRegistry schema"}, True),
        ]

        total_calls = len(test_scenarios)
        successful_calls = 0

        for tool_name, args, should_succeed in test_scenarios:
            result = registry.call(tool_name, **args)
            if should_succeed:
                if "error" not in result.lower() and "Unknown city" not in result:
                    successful_calls += 1
            else:
                if (
                    "error" in result.lower()
                    or "Unknown city" in result
                    or "Unsupported" in result
                ):
                    successful_calls += 1

        success_rate = successful_calls / total_calls
        print(f"\n=== Tool Call Success Rate Summary ===")
        print(f"Total calls: {total_calls}")
        print(f"Successful: {successful_calls}")
        print(f"Success rate: {success_rate:.1%}")
        print(f"======================================")

        assert success_rate >= 0.85, f"Expected at least 85% success rate, got {success_rate:.1%}"


def calculate_success_rate(result: AgentRunResult) -> float:
    """Calculate tool call success rate from AgentRunResult.

    This utility function extracts tool_events from the result and calculates
    the ratio of successful calls to total calls.
    """
    events = result.get("tool_events", [])
    if not events:
        return 1.0 if result.get("success") else 0.0

    success_count = sum(1 for e in events if e.get("status") == "success")
    return success_count / len(events)
