from app.core.tool_selection import HeuristicToolSelector, ToolCatalog
from evals.fixtures.tool_zoo import build_large_tool_registry
from evals.runners.tool_retrieval_eval import (
    ToolRetrievalCase,
    ToolRetrievalEvalRunner,
    load_tool_retrieval_cases,
)


def test_tool_retrieval_eval_scores_recall_and_schema_reduction():
    registry = build_large_tool_registry(noise_tool_count=30)
    cases = [
        ToolRetrievalCase(
            id="retrieve_calculator",
            input="Calculate 18 * 7.",
            expected_tools=["calculator"],
        ),
        ToolRetrievalCase(
            id="retrieve_markdown_table",
            input="Render rows as a markdown table.",
            expected_tools=["render_markdown_table"],
        ),
    ]
    runner = ToolRetrievalEvalRunner(
        registry,
        selector=HeuristicToolSelector(max_tools=8, namespace_cap=3),
    )

    result = runner.run(cases)

    assert result.suite == "tool_retrieval"
    assert result.total_cases == 2
    assert result.passed_cases == 2
    assert result.metrics["recall_at_k"] == 1.0
    assert result.metrics["schema_token_reduction_rate"] > 0.5
    assert result.metrics["avg_selected_tool_count"] <= 8
    assert result.metrics["min_selected_tool_count"] >= 1
    assert result.metrics["max_selected_tool_count"] >= 1


def test_tool_retrieval_eval_checks_namespace_cap():
    catalog = ToolCatalog()
    descriptions = {
        "mcp:github:search_issues": "Search GitHub issues by text query.",
        "mcp:github:create_issue": "Create a GitHub issue.",
        "mcp:github:list_pull_requests": "List GitHub pull requests.",
    }
    for name, description in descriptions.items():
        catalog.register_from_openai_tool(
            {
                "type": "function",
                "name": name,
                "description": description,
                "parameters": {"type": "object", "properties": {}},
            },
            side_effect_policy="read_only",
        )
    runner = ToolRetrievalEvalRunner(
        catalog,
        selector=HeuristicToolSelector(max_tools=5, namespace_cap=2),
    )

    result = runner.run([
            ToolRetrievalCase(
                id="github_namespace_cap",
                input="search github issues",
                expected_tools=["mcp:github:search_issues"],
                max_tools_per_namespace=2,
            )
    ])

    assert result.passed_cases == 1
    assert result.metrics["namespace_cap_pass_rate"] == 1.0
    assert result.cases[0].details["namespace_counts"]["mcp:github"] <= 2


def test_tool_retrieval_cases_load_from_jsonl():
    cases = load_tool_retrieval_cases("evals/cases/tool_retrieval.jsonl")

    assert len(cases) >= 8
    assert all(case.expected_tools for case in cases)


def test_tool_retrieval_cases_include_multi_tool_scenarios():
    cases = load_tool_retrieval_cases("evals/cases/tool_retrieval.jsonl")

    multi_tool_cases = [
        case for case in cases
        if len(case.expected_tools) >= 2
    ]

    assert len(multi_tool_cases) >= 6
    assert max(len(case.expected_tools) for case in cases) >= 4
