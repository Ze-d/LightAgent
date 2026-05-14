"""Tests for ContextPipeline and its five processors."""
from app.obj.types import ChatMessage
from app.core.context_pipeline import (
    BudgetAllocation,
    ContextPipeline,
    DeduplicationProcessor,
    DynamicBudgetAllocator,
    HierarchicalSummarizer,
    ImportanceScorer,
    ImportanceScore,
    IntelligentTrimmer,
    TrimResult,
)


# ── DeduplicationProcessor ─────────────────────────────────────────────────


class TestDeduplicationProcessor:
    def test_removes_consecutive_identical_messages(self):
        processor = DeduplicationProcessor()
        messages: list[ChatMessage] = [
            {"role": "system", "content": "prompt"},
            {"role": "user", "content": "hello"},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
            {"role": "assistant", "content": "hi"},
            {"role": "user", "content": "next"},
        ]
        result = processor.process(messages, {})
        assert result.messages == [
            {"role": "system", "content": "prompt"},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
            {"role": "user", "content": "next"},
        ]
        assert result.metadata["dedup_count"] == 2

    def test_preserves_non_consecutive_duplicates(self):
        processor = DeduplicationProcessor()
        messages: list[ChatMessage] = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
            {"role": "user", "content": "hello"},
        ]
        result = processor.process(messages, {})
        assert len(result.messages) == 3
        assert result.metadata["dedup_count"] == 0

    def test_empty_messages(self):
        processor = DeduplicationProcessor()
        result = processor.process([], {})
        assert result.messages == []
        assert result.metadata["dedup_count"] == 0

    def test_single_message(self):
        processor = DeduplicationProcessor()
        messages: list[ChatMessage] = [{"role": "user", "content": "hello"}]
        result = processor.process(messages, {})
        assert result.messages == messages
        assert result.metadata["dedup_count"] == 0


# ── ImportanceScorer ───────────────────────────────────────────────────────


class TestImportanceScorer:
    def test_system_prompt_gets_highest_score(self):
        scorer = ImportanceScorer()
        messages: list[ChatMessage] = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        result = scorer.process(messages, {})
        scores: list[ImportanceScore] = result.metadata["importance_scores"]
        assert scores[0].score == 100
        assert scores[0].reason == "system_prompt"

    def test_recent_exchanges_get_high_scores(self):
        scorer = ImportanceScorer(recent_window=3)
        messages: list[ChatMessage] = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        result = scorer.process(messages, {})
        scores: list[ImportanceScore] = result.metadata["importance_scores"]
        assert scores[1].score == 90
        assert scores[1].reason == "recent_exchange"
        assert scores[2].score == 90

    def test_older_exchanges_decay(self):
        scorer = ImportanceScorer(recent_window=1, decay_per_turn=5)
        messages: list[ChatMessage] = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "old"},
            {"role": "assistant", "content": "old response"},
            {"role": "user", "content": "old2"},
            {"role": "assistant", "content": "old response2"},
            {"role": "user", "content": "recent"},
            {"role": "assistant", "content": "recent response"},
        ]
        result = scorer.process(messages, {})
        scores: list[ImportanceScore] = result.metadata["importance_scores"]
        # Older messages should have lower scores than recent ones
        assert scores[1].score < scores[5].score
        assert scores[5].reason == "recent_exchange"

    def test_transient_memory_gets_low_score(self):
        scorer = ImportanceScorer()
        messages: list[ChatMessage] = [
            {"role": "system", "content": "[Memory]\nsome context"},
            {"role": "user", "content": "hello"},
        ]
        result = scorer.process(messages, {})
        scores: list[ImportanceScore] = result.metadata["importance_scores"]
        assert scores[0].score == 30
        assert scores[0].reason == "transient_memory"

    def test_summary_messages_scored(self):
        scorer = ImportanceScorer()
        messages: list[ChatMessage] = [
            {"role": "system", "content": "System prompt"},
            {"role": "system", "content": "[Previous conversation summary]\nold"},
            {"role": "user", "content": "hello"},
        ]
        result = scorer.process(messages, {})
        scores: list[ImportanceScore] = result.metadata["importance_scores"]
        assert scores[1].reason == "summary"
        assert scores[1].score == 70

    def test_tool_outputs_scored(self):
        scorer = ImportanceScorer()
        messages: list[ChatMessage] = [
            {"role": "system", "content": "System prompt"},
            {"role": "tool", "content": "tool output 1"},
            {"role": "tool", "content": "tool output 2"},
        ]
        result = scorer.process(messages, {})
        scores: list[ImportanceScore] = result.metadata["importance_scores"]
        assert scores[1].reason == "recent_tool_output"
        assert scores[1].score == 85
        assert scores[2].reason == "recent_tool_output"
        assert scores[2].score == 85


# ── HierarchicalSummarizer ─────────────────────────────────────────────────


class TestHierarchicalSummarizer:
    def test_no_summarization_when_under_target(self):
        summarizer = HierarchicalSummarizer(target_messages=10)
        messages: list[ChatMessage] = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        result = summarizer.process(messages, {})
        assert result.messages == messages
        assert result.metadata["summary_generated"] is False

    def test_summarizes_large_history(self):
        summarizer = HierarchicalSummarizer(target_messages=6)
        messages: list[ChatMessage] = [
            {"role": "system", "content": "System prompt"},
        ]
        for i in range(10):
            messages.append({"role": "user", "content": f"Question {i}"})
            messages.append({"role": "assistant", "content": f"Answer {i}"})

        result = summarizer.process(messages, {})
        assert len(result.messages) <= 7
        assert result.metadata["summary_generated"] is True
        assert result.messages[0]["role"] == "system"
        assert result.messages[0]["content"] == "System prompt"
        summary = result.messages[1]
        assert summary["role"] == "system"
        assert summary["content"].startswith("[Previous conversation summary]")

    def test_preserves_system_prompt(self):
        summarizer = HierarchicalSummarizer(target_messages=4)
        messages: list[ChatMessage] = [
            {"role": "system", "content": "Important system prompt"},
        ]
        for i in range(8):
            messages.append({"role": "user", "content": f"Q{i}"})
            messages.append({"role": "assistant", "content": f"A{i}"})

        result = summarizer.process(messages, {})
        assert result.messages[0]["content"] == "Important system prompt"


# ── DynamicBudgetAllocator ─────────────────────────────────────────────────


class TestDynamicBudgetAllocator:
    def test_short_conversation_allocation(self):
        allocator = DynamicBudgetAllocator(max_input_tokens=8000)
        messages: list[ChatMessage] = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        result = allocator.process(messages, {})
        allocation: BudgetAllocation = result.metadata["budget_allocation"]
        assert allocation is not None
        assert allocation.conversation_type == "short"
        assert allocation.for_conversation > allocation.for_summaries

    def test_tool_heavy_conversation_allocation(self):
        allocator = DynamicBudgetAllocator(max_input_tokens=8000)
        messages: list[ChatMessage] = [
            {"role": "system", "content": "System prompt"},
        ]
        for i in range(10):
            messages.append({"role": "tool", "content": f"tool output {i}"})

        result = allocator.process(messages, {})
        allocation: BudgetAllocation = result.metadata["budget_allocation"]
        assert allocation.conversation_type == "tool_heavy"
        assert allocation.for_tools >= allocation.for_summaries

    def test_disabled_when_no_budget(self):
        allocator = DynamicBudgetAllocator(max_input_tokens=None)
        messages: list[ChatMessage] = [
            {"role": "user", "content": "hello"},
        ]
        result = allocator.process(messages, {})
        assert result.metadata["budget_allocation"] is None
        assert result.metadata["budget_disabled"] is True


# ── IntelligentTrimmer ─────────────────────────────────────────────────────


class TestIntelligentTrimmer:
    def test_keeps_all_when_within_budget(self):
        trimmer = IntelligentTrimmer(max_input_tokens=10000)
        messages: list[ChatMessage] = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        result = trimmer.process(messages, {})
        trim_result: TrimResult = result.metadata["trim_result"]
        assert trim_result.reason == "within_budget"
        assert trim_result.dropped_count == 0

    def test_trims_when_over_budget(self):
        trimmer = IntelligentTrimmer(max_input_tokens=40)
        messages: list[ChatMessage] = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "old " * 30},
            {"role": "assistant", "content": "old answer " * 30},
            {"role": "user", "content": "new question"},
        ]
        result = trimmer.process(messages, {})
        trim_result: TrimResult = result.metadata["trim_result"]
        assert trim_result.reason in ("trimmed", "minimum_exceeds_budget")
        assert len(result.messages) <= len(messages)

    def test_preserves_mandatory_messages(self):
        trimmer = IntelligentTrimmer(max_input_tokens=60)
        messages: list[ChatMessage] = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "old " * 30},
            {"role": "assistant", "content": "old answer " * 30},
            {"role": "user", "content": "new question"},
            {"role": "assistant", "content": "new answer"},
        ]
        result = trimmer.process(messages, {})
        # Mandatory messages must be preserved
        contents = {m["content"] for m in result.messages}
        assert "System prompt" in contents
        assert "new question" in contents
        assert "new answer" in contents

    def test_disabled_when_no_budget(self):
        trimmer = IntelligentTrimmer(max_input_tokens=None)
        messages: list[ChatMessage] = [
            {"role": "user", "content": "hello"},
        ]
        result = trimmer.process(messages, {})
        trim_result: TrimResult = result.metadata["trim_result"]
        assert trim_result.reason == "within_budget"


# ── Pipeline Integration ───────────────────────────────────────────────────


class TestContextPipeline:
    def test_executes_all_processors_in_order(self):
        pipeline = ContextPipeline([
            DeduplicationProcessor(),
            HierarchicalSummarizer(target_messages=10),
            ImportanceScorer(),
            DynamicBudgetAllocator(max_input_tokens=8000),
            IntelligentTrimmer(max_input_tokens=8000),
        ])
        messages: list[ChatMessage] = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        result = pipeline.run(messages)
        assert len(result.stages_executed) == 5
        assert result.stages_executed == [
            "DeduplicationProcessor",
            "HierarchicalSummarizer",
            "ImportanceScorer",
            "DynamicBudgetAllocator",
            "IntelligentTrimmer",
        ]
        assert "importance_scores" in result.metadata
        assert "trim_result" in result.metadata

    def test_pipeline_works_with_subset_of_processors(self):
        pipeline = ContextPipeline([
            DeduplicationProcessor(),
            ImportanceScorer(),
        ])
        messages: list[ChatMessage] = [
            {"role": "user", "content": "hello"},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        result = pipeline.run(messages)
        assert len(result.stages_executed) == 2
        assert len(result.messages) == 2
        assert "importance_scores" in result.metadata

    def test_summarize_before_scoring_scores_align_with_final_messages(self):
        pipeline = ContextPipeline([
            DeduplicationProcessor(),
            HierarchicalSummarizer(target_messages=10),
            ImportanceScorer(),
            IntelligentTrimmer(max_input_tokens=8000),
        ])
        messages: list[ChatMessage] = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "question"},
            {"role": "user", "content": "question"},
            {"role": "assistant", "content": "answer"},
        ]
        result = pipeline.run(messages)
        # After dedup: 3 messages. Summarizer doesn't trigger (< target).
        # Scores align 1:1 with the 3 final messages.
        assert len(result.messages) == 3
        scores: list[ImportanceScore] = result.metadata["importance_scores"]
        assert len(scores) == 3

    def test_fast_path_skips_heavy_stages_when_within_budget(self):
        pipeline = ContextPipeline(
            [
                DeduplicationProcessor(),
                HierarchicalSummarizer(target_messages=10),
                ImportanceScorer(),
                DynamicBudgetAllocator(max_input_tokens=8000),
                IntelligentTrimmer(max_input_tokens=8000),
            ],
            max_input_tokens=5000,  # budget is huge relative to 3 messages
        )
        messages: list[ChatMessage] = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        result = pipeline.run(messages)
        # Only dedup ran; heavy stages skipped via fast path.
        assert "DeduplicationProcessor" in result.stages_executed
        assert "_fast_path" in result.stages_executed
        assert "ImportanceScorer" not in result.stages_executed
        assert "HierarchicalSummarizer" not in result.stages_executed
        assert "IntelligentTrimmer" not in result.stages_executed
        assert result.messages == messages

    def test_fast_path_disabled_when_no_budget_configured(self):
        pipeline = ContextPipeline(
            [
                DeduplicationProcessor(),
                ImportanceScorer(),
            ],
            # No max_input_tokens → fast path disabled.
        )
        messages: list[ChatMessage] = [
            {"role": "user", "content": "hello"},
        ]
        result = pipeline.run(messages)
        assert "_fast_path" not in result.stages_executed
        assert "ImportanceScorer" in result.stages_executed
