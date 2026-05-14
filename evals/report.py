"""Markdown report rendering for runtime eval results."""
from __future__ import annotations

from pathlib import Path

from evals.models import EvalSuiteResult


def render_markdown_report(results: list[EvalSuiteResult]) -> str:
    lines = [
        "# Agent Runtime Eval Report",
        "",
        "| Suite | Cases | Passed | Pass Rate | Key Metrics |",
        "|------|------:|------:|----------:|-------------|",
    ]
    for result in results:
        metrics = ", ".join(
            f"{name}={_format_metric(value)}"
            for name, value in result.metrics.items()
        )
        lines.append(
            f"| {result.suite} | {result.total_cases} | "
            f"{result.passed_cases} | {result.pass_rate:.1%} | {metrics} |"
        )

    lines.extend(["", "## Case Results", ""])
    for result in results:
        lines.append(f"### {result.suite}")
        lines.append("")
        lines.append("| Case | Status | Metrics |")
        lines.append("|------|--------|---------|")
        for case in result.cases:
            status = "PASS" if case.passed else "FAIL"
            metrics = ", ".join(
                f"{name}={_format_metric(value)}"
                for name, value in case.metrics.items()
            )
            lines.append(f"| {case.case_id} | {status} | {metrics} |")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_markdown_report(
    results: list[EvalSuiteResult],
    path: str | Path,
) -> Path:
    report_path = Path(path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_markdown_report(results), encoding="utf-8")
    return report_path


def _format_metric(value: float | int) -> str:
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)
