from types import SimpleNamespace

from app.exceptions.agent import MinimalAgent


def test_agent_returns_direct_text(monkeypatch):
    agent = MinimalAgent(model="test-model")

    fake_response = SimpleNamespace(
        output=[],
        output_text="这是最终答案"
    )

    def fake_create(*args, **kwargs):
        return fake_response

    monkeypatch.setattr(agent.client.responses, "create", fake_create)

    history = [
        {"role": "system", "content": "你是助手"},
        {"role": "user", "content": "你好"}
    ]

    result = agent.run(history)
    assert result == "这是最终答案"

def test_agent_function_call_then_final_text(monkeypatch):

    agent = MinimalAgent(model="test-model")

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
        output_text="计算结果是 5"
    )

    responses = [first_response, second_response]

    def fake_create(*args, **kwargs):
        return responses.pop(0)

    monkeypatch.setattr(agent.client.responses, "create", fake_create)

    history = [
        {"role": "system", "content": "你是助手"},
        {"role": "user", "content": "帮我算 2 + 3"}
    ]

    result = agent.run(history)
    assert result == "计算结果是 5"

from types import SimpleNamespace

from app.exceptions.agent import MinimalAgent


def test_agent_handles_invalid_tool_arguments(monkeypatch):
    agent = MinimalAgent(model="test-model")

    function_call_item = SimpleNamespace(
        type="function_call",
        name="calculator",
        arguments='{"expression": 2 + }',
        call_id="call_bad"
    )

    first_response = SimpleNamespace(
        output=[function_call_item],
        output_text=""
    )

    second_response = SimpleNamespace(
        output=[],
        output_text="工具参数解析失败。"
    )

    responses = [first_response, second_response]

    def fake_create(*args, **kwargs):
        return responses.pop(0)

    monkeypatch.setattr(agent.client.responses, "create", fake_create)

    history = [
        {"role": "system", "content": "你是助手"},
        {"role": "user", "content": "帮我算一个表达式"}
    ]

    result = agent.run(history)
    assert result == "工具参数解析失败。"