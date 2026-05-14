from evals.models import EvalSuiteResult
from evals.fixtures.tool_zoo import build_tool_zoo_registry
from evals.runners.tool_eval import (
    ToolCallingCase,
    ToolEvalRunner,
    load_tool_cases,
)
from app.tools.register import build_default_registry


def test_tool_eval_runner_scores_tool_selection_and_arguments():
    cases = [
        ToolCallingCase(
            id="tool_calculator",
            input="Calculate 18 * 7.",
            expected_tool="calculator",
            expected_args={"expression": "18 * 7"},
            expected_result_contains=["126"],
            expected_answer_contains=["done"],
        ),
        ToolCallingCase(
            id="tool_convert_units",
            input="Convert 2.5 kilometers to meters.",
            expected_tool="convert_units",
            expected_args={
                "value": 2.5,
                "from_unit": "kilometer",
                "to_unit": "meter",
            },
            expected_result_contains=["2500"],
            expected_answer_contains=["done"],
        ),
    ]

    result = ToolEvalRunner(build_default_registry()).run(cases)

    assert isinstance(result, EvalSuiteResult)
    assert result.suite == "tool_calling"
    assert result.total_cases == 2
    assert result.passed_cases == 2
    assert result.metrics["tool_selection_accuracy"] == 1.0
    assert result.metrics["argument_accuracy"] == 1.0
    assert result.metrics["schema_valid_rate"] == 1.0
    assert result.metrics["tool_success_rate"] == 1.0
    assert result.metrics["tool_result_contains_rate"] == 1.0
    assert [case.case_id for case in result.cases] == [
        "tool_calculator",
        "tool_convert_units",
    ]


def test_tool_eval_runner_records_selection_failures():
    cases = [
        ToolCallingCase(
            id="tool_wrong",
            input="Calculate 1 + 1.",
            expected_tool="calculator",
            expected_args={"expression": "1 + 1"},
            llm_tool_name="get_current_time",
            llm_args={"city": "tokyo"},
        )
    ]

    result = ToolEvalRunner(build_default_registry()).run(cases)

    assert result.total_cases == 1
    assert result.passed_cases == 0
    assert result.metrics["tool_selection_accuracy"] == 0.0
    assert result.metrics["argument_accuracy"] == 0.0
    assert result.cases[0].passed is False
    assert result.cases[0].details["actual_tool"] == "get_current_time"


def test_tool_eval_runner_checks_tool_output_fragments():
    cases = [
        ToolCallingCase(
            id="tool_result_mismatch",
            input="Calculate 1 + 1.",
            expected_tool="calculator",
            expected_args={"expression": "1 + 1"},
            expected_result_contains=["not-the-result"],
        )
    ]

    result = ToolEvalRunner(build_default_registry()).run(cases)

    assert result.passed_cases == 0
    assert result.metrics["tool_result_contains_rate"] == 0.0
    assert result.cases[0].details["tool_output"] == "2"


def test_tool_zoo_registry_covers_varied_eval_only_tools():
    registry = build_tool_zoo_registry()

    assert set(registry.list_names()) == {
        "extract_keywords",
        "regex_extract",
        "normalize_whitespace",
        "json_path_read",
        "csv_summarize",
        "render_markdown_table",
        "date_diff",
        "add_business_days",
        "split_tasks",
        "prioritize_tasks",
        "validate_url",
        "hash_text",
        "dedupe_lines",
        "sort_items",
        "template_render",
    }


def test_tool_zoo_cases_run_as_separate_suite():
    cases = [
        ToolCallingCase(
            id="zoo_keywords",
            input="Extract top keywords.",
            expected_tool="extract_keywords",
            expected_args={"text": "agent runtime agent eval tool", "top_k": 2},
            expected_result_contains=["agent", "runtime"],
        )
    ]

    result = ToolEvalRunner(
        build_tool_zoo_registry(),
        suite_name="tool_calling_zoo",
    ).run(cases)

    assert result.suite == "tool_calling_zoo"
    assert result.total_cases == 1
    assert result.passed_cases == 1


def test_default_tool_cases_cover_every_default_registry_tool():
    registry = build_default_registry()
    cases = load_tool_cases("evals/cases/tool_calling.jsonl")

    covered_tools = {case.expected_tool for case in cases}

    assert set(registry.list_names()) <= covered_tools


def test_tool_zoo_cases_cover_every_zoo_tool():
    registry = build_tool_zoo_registry()
    cases = load_tool_cases("evals/cases/tool_zoo.jsonl")

    covered_tools = {case.expected_tool for case in cases}

    assert set(registry.list_names()) <= covered_tools
