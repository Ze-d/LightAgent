from pathlib import Path
from uuid import uuid4

from evals.models import EvalCaseResult, EvalSuiteResult
from evals.report import render_markdown_report, write_markdown_report


def test_render_markdown_report_contains_suite_metrics():
    suite = EvalSuiteResult(
        suite="tool_calling",
        total_cases=1,
        passed_cases=1,
        metrics={"tool_selection_accuracy": 1.0},
        cases=[
            EvalCaseResult(
                case_id="tool_001",
                passed=True,
                metrics={"tool_selection_accuracy": 1.0},
                details={"actual_tool": "calculator"},
            )
        ],
    )

    report = render_markdown_report([suite])

    assert "# Agent Runtime Eval Report" in report
    assert "| tool_calling | 1 | 1 | 100.0% |" in report
    assert "tool_selection_accuracy=1.000" in report


def test_write_markdown_report_creates_parent_directories():
    suite = EvalSuiteResult(
        suite="checkpoint_recovery",
        total_cases=1,
        passed_cases=0,
        metrics={"recovery_success_rate": 0.0},
        cases=[],
    )
    report_path = (
        Path("test-runtime")
        / f"eval-report-{uuid4().hex}"
        / "reports"
        / "evals"
        / "runtime-eval-latest.md"
    )

    write_markdown_report([suite], report_path)

    assert report_path.exists()
    assert "checkpoint_recovery" in report_path.read_text(encoding="utf-8")
    report_path.unlink(missing_ok=True)
