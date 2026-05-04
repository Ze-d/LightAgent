from app.core.token_budget import (
    EstimatedTokenCounter,
    TokenBudgetTrimmer,
    trim_text_to_token_budget,
)


def test_estimated_token_counter_counts_cjk_more_densely_than_ascii():
    counter = EstimatedTokenCounter()

    assert counter.count_text("你好世界") == 4
    assert counter.count_text("abcdefghijkl") == 3


def test_token_budget_trimmer_keeps_system_and_latest_user_message():
    trimmer = TokenBudgetTrimmer(max_input_tokens=45)
    messages = [
        {"role": "system", "content": "System prompt"},
        {"role": "user", "content": "old " * 40},
        {"role": "assistant", "content": "old answer " * 40},
        {"role": "user", "content": "new question"},
    ]

    result = trimmer.apply(messages)

    assert result.status == "estimated"
    assert result.reason == "trimmed_history"
    assert result.dropped_messages == 2
    assert result.input_tokens <= 45
    assert result.messages == [
        {"role": "system", "content": "System prompt"},
        {"role": "user", "content": "new question"},
    ]


def test_token_budget_trimmer_drops_optional_system_context_when_needed():
    trimmer = TokenBudgetTrimmer(max_input_tokens=35)
    messages = [
        {"role": "system", "content": "System prompt"},
        {"role": "system", "content": "optional memory " * 50},
        {"role": "user", "content": "new question"},
    ]

    result = trimmer.apply(messages)

    assert result.reason == "trimmed_history_and_optional_system"
    assert result.dropped_messages == 1
    assert result.messages == [
        {"role": "system", "content": "System prompt"},
        {"role": "user", "content": "new question"},
    ]


def test_trim_text_to_token_budget_keeps_tail_when_requested():
    counter = EstimatedTokenCounter()
    text = "old " * 80 + "latest decision"
    trimmed = trim_text_to_token_budget(text, 20, keep="end")

    assert counter.count_text(trimmed) <= 20
    assert "latest decision" in trimmed
    assert trimmed.startswith("[truncated]")
