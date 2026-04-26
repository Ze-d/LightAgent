"""Integration tests for tool call success rate in agent runs."""
from types import SimpleNamespace

import pytest

from app.agents.tool_aware_agent import ToolAwareAgent
from app.core.runner import AgentRunner
from app.tools.register import build_default_registry
from app.obj.types import AgentRunResult


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


class TestNormalToolCallSuccessRate:
    """Test tool call success rate in normal scenarios."""

    def test_single_tool_call_success_rate_100_percent(self, monkeypatch):
        """Test that a single valid tool call achieves 100% success rate."""
        events = []

        def listener(event):
            events.append(event)

        agent = ToolAwareAgent(
            name="tool-aware-agent",
            model="test-model",
            system_prompt="You are a test agent.",
            tool_call_listener=listener,
        )

        fake_client = SimpleNamespace()
        fake_client.responses = SimpleNamespace()
        fake_client.responses.create = SimpleNamespace()

        function_call_item = SimpleNamespace(
            type="function_call",
            name="calculator",
            arguments='{"expression": "2 + 3"}',
            call_id="call_1"
        )

        first_response = SimpleNamespace(
            output=[function_call_item],
            output_text=""
        )

        second_response = SimpleNamespace(
            output=[],
            output_text="结果是 5"
        )

        responses = [first_response, second_response]

        def fake_create(*args, **kwargs):
            return responses.pop(0)

        monkeypatch.setattr(fake_client.responses, "create", fake_create)

        runner = AgentRunner(client=fake_client, max_steps=5)
        registry = build_default_registry()

        result = runner.run(
            agent=agent,
            history=[{"role": "user", "content": "帮我算 2 + 3"}],
            tool_registry=registry,
        )

        success_rate = calculate_success_rate(result)
        print(f"\n=== Single Tool Call Test ===")
        print(f"Tool events: {len(result['tool_events'])}")
        print(f"Success rate: {success_rate:.1%}")
        print(f"===========================")

        assert success_rate == 1.0, f"Expected 100% success rate, got {success_rate}"

    def test_multiple_tool_calls_all_succeed(self, monkeypatch):
        """Test that multiple tool calls in sequence all succeed."""
        events = []

        def listener(event):
            events.append(event)

        agent = ToolAwareAgent(
            name="tool-aware-agent",
            model="test-model",
            system_prompt="You are a test agent.",
            tool_call_listener=listener,
        )

        fake_client = SimpleNamespace()
        fake_client.responses = SimpleNamespace()
        fake_client.responses.create = SimpleNamespace()

        calc_call = SimpleNamespace(
            type="function_call",
            name="calculator",
            arguments='{"expression": "10 * 5"}',
            call_id="call_1"
        )

        time_call = SimpleNamespace(
            type="function_call",
            name="get_current_time",
            arguments='{"city": "beijing"}',
            call_id="call_2"
        )

        first_response = SimpleNamespace(
            output=[calc_call, time_call],
            output_text=""
        )

        second_response = SimpleNamespace(
            output=[],
            output_text="计算结果是 50，当前北京时间已获取。"
        )

        responses = [first_response, second_response]

        def fake_create(*args, **kwargs):
            return responses.pop(0)

        monkeypatch.setattr(fake_client.responses, "create", fake_create)

        runner = AgentRunner(client=fake_client, max_steps=5)
        registry = build_default_registry()

        result = runner.run(
            agent=agent,
            history=[{"role": "user", "content": "帮我计算并获取时间"}],
            tool_registry=registry,
        )

        success_rate = calculate_success_rate(result)
        print(f"\n=== Multiple Tool Calls Test ===")
        print(f"Tool events: {len(result['tool_events'])}")
        print(f"Success rate: {success_rate:.1%}")
        print(f"===========================")

        assert success_rate == 1.0, f"Expected 100% success rate, got {success_rate}"
        assert len(result["tool_events"]) == 2


class TestMixedSuccessFailure:
    """Test success rate calculation with mixed success/failure scenarios."""

    def test_no_tool_calls_returns_full_success(self):
        """When no tools are called, success rate should reflect overall run success."""
        result: AgentRunResult = {
            "answer": "No tools needed",
            "success": True,
            "steps": 1,
            "tool_events": [],
            "error": None
        }

        success_rate = calculate_success_rate(result)
        assert success_rate == 1.0

    def test_tool_events_status_tracking(self):
        """Test that success rate correctly counts status field."""
        result: AgentRunResult = {
            "answer": "Done",
            "success": True,
            "steps": 2,
            "tool_events": [
                {"status": "success", "tool_name": "calculator"},
                {"status": "success", "tool_name": "get_current_time"},
                {"status": "error", "tool_name": "unknown_tool"},
            ],
            "error": None
        }

        success_rate = calculate_success_rate(result)
        assert success_rate == pytest.approx(2/3)
        print(f"\n=== Mixed Success/Failure Test ===")
        print(f"Total tool events: 3")
        print(f"Successful: 2")
        print(f"Success rate: {success_rate:.1%}")
        print(f"=================================")


class TestToolNotFoundHandling:
    """Test error handling when tool is not found."""

    def test_tool_not_found_success_rate_is_zero(self, monkeypatch):
        """When tool doesn't exist, success rate should be 0% for that tool."""
        events = []

        def listener(event):
            events.append(event)

        agent = ToolAwareAgent(
            name="tool-aware-agent",
            model="test-model",
            system_prompt="You are a test agent.",
            tool_call_listener=listener,
        )

        fake_client = SimpleNamespace()
        fake_client.responses = SimpleNamespace()
        fake_client.responses.create = SimpleNamespace()

        unknown_tool_call = SimpleNamespace(
            type="function_call",
            name="nonexistent_tool",
            arguments='{}',
            call_id="call_1"
        )

        first_response = SimpleNamespace(
            output=[unknown_tool_call],
            output_text=""
        )

        second_response = SimpleNamespace(
            output=[],
            output_text="工具不存在"
        )

        responses = [first_response, second_response]

        def fake_create(*args, **kwargs):
            return responses.pop(0)

        monkeypatch.setattr(fake_client.responses, "create", fake_create)

        runner = AgentRunner(client=fake_client, max_steps=5)
        registry = build_default_registry()

        result = runner.run(
            agent=agent,
            history=[{"role": "user", "content": "使用不存在的工具"}],
            tool_registry=registry,
        )

        success_rate = calculate_success_rate(result)
        print(f"\n=== Tool Not Found Test ===")
        print(f"Tool events: {len(result['tool_events'])}")
        print(f"Success rate: {success_rate:.1%}")
        print(f"=================================")

        assert success_rate == 0.0, f"Expected 0% success rate for missing tool, got {success_rate}"


class TestToolCallSuccessRateSummary:
    """Summary test reporting overall tool call success rate metrics."""

    def test_overall_success_rate_metrics(self, monkeypatch):
        """Calculate and report overall tool call success rate metrics."""
        events = []

        def listener(event):
            events.append(event)

        agent = ToolAwareAgent(
            name="tool-aware-agent",
            model="test-model",
            system_prompt="You are a test agent.",
            tool_call_listener=listener,
        )

        fake_client = SimpleNamespace()
        fake_client.responses = SimpleNamespace()
        fake_client.responses.create = SimpleNamespace()

        calc_call = SimpleNamespace(
            type="function_call",
            name="calculator",
            arguments='{"expression": "5 + 5"}',
            call_id="call_1"
        )

        first_response = SimpleNamespace(
            output=[calc_call],
            output_text=""
        )

        second_response = SimpleNamespace(
            output=[],
            output_text="5 + 5 = 10"
        )

        responses = [first_response, second_response]

        def fake_create(*args, **kwargs):
            return responses.pop(0)

        monkeypatch.setattr(fake_client.responses, "create", fake_create)

        runner = AgentRunner(client=fake_client, max_steps=5)
        registry = build_default_registry()

        result = runner.run(
            agent=agent,
            history=[{"role": "user", "content": "Calculate 5 + 5"}],
            tool_registry=registry,
        )

        success_rate = calculate_success_rate(result)
        total_calls = len(result.get("tool_events", []))
        successful_calls = sum(1 for e in result.get("tool_events", []) if e.get("status") == "success")

        print(f"\n{'='*40}")
        print(f"  Tool Call Success Rate Metrics")
        print(f"{'='*40}")
        print(f"  Total tool calls:     {total_calls}")
        print(f"  Successful calls:     {successful_calls}")
        print(f"  Failed calls:         {total_calls - successful_calls}")
        print(f"  Success rate:         {success_rate:.1%}")
        print(f"{'='*40}")

        assert success_rate == 1.0
        assert result["success"] is True
