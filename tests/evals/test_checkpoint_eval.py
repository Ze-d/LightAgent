from evals.models import EvalSuiteResult
from evals.runners.checkpoint_eval import CheckpointEvalCase, CheckpointEvalRunner


def test_checkpoint_eval_runner_scores_resume_without_repeating_tool():
    cases = [
        CheckpointEvalCase(
            id="resume_read_only_once",
            scenario="tool_output_resume_no_repeat",
            tool_name="lookup",
            side_effect_policy="read_only",
            expected_resume_success=True,
            expected_duplicate_tool_count=0,
        )
    ]

    result = CheckpointEvalRunner().run(cases)

    assert isinstance(result, EvalSuiteResult)
    assert result.suite == "checkpoint_recovery"
    assert result.total_cases == 1
    assert result.passed_cases == 1
    assert result.metrics["recovery_success_rate"] == 1.0
    assert result.metrics["duplicate_tool_execution_count"] == 0
    assert result.metrics["checkpoint_phase_correct_rate"] == 1.0


def test_checkpoint_eval_runner_scores_non_idempotent_protection():
    cases = [
        CheckpointEvalCase(
            id="blocks_running_non_idempotent",
            scenario="non_idempotent_running_blocks",
            tool_name="send_email",
            side_effect_policy="non_idempotent",
            expected_resume_success=False,
            expected_error="tool_requires_manual_resume",
            expected_duplicate_tool_count=0,
        )
    ]

    result = CheckpointEvalRunner().run(cases)

    assert result.total_cases == 1
    assert result.passed_cases == 1
    assert result.metrics["non_idempotent_protection_rate"] == 1.0
    assert result.cases[0].details["actual_error"] == "tool_requires_manual_resume"


def test_checkpoint_eval_runner_recovery_rate_counts_only_recoverable_cases():
    cases = [
        CheckpointEvalCase(
            id="resume_read_only_once",
            scenario="tool_output_resume_no_repeat",
            tool_name="lookup",
            side_effect_policy="read_only",
            expected_resume_success=True,
            expected_duplicate_tool_count=0,
        ),
        CheckpointEvalCase(
            id="blocks_running_non_idempotent",
            scenario="non_idempotent_running_blocks",
            tool_name="send_email",
            side_effect_policy="non_idempotent",
            expected_resume_success=False,
            expected_error="tool_requires_manual_resume",
            expected_duplicate_tool_count=0,
        ),
    ]

    result = CheckpointEvalRunner().run(cases)

    assert result.passed_cases == 2
    assert result.metrics["recovery_success_rate"] == 1.0
    assert result.metrics["expected_outcome_rate"] == 1.0
