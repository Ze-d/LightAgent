"""Eval suite for top-k tool retrieval under large registries."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.tool_selection import (
    HeuristicToolSelector,
    ToolCatalog,
    ToolSelectionRequest,
    estimate_schema_tokens,
)
from evals.metrics import average, safe_divide
from evals.models import EvalCaseResult, EvalSuiteResult


@dataclass(frozen=True)
class ToolRetrievalCase:
    id: str
    input: str
    expected_tools: list[str]
    irrelevant_tools: list[str] = field(default_factory=list)
    max_tools_per_namespace: int | None = None
    allow_side_effects: bool | None = None


class ToolRetrievalEvalRunner:
    def __init__(
        self,
        registry_or_catalog: Any,
        *,
        selector: HeuristicToolSelector | None = None,
        suite_name: str = "tool_retrieval",
    ) -> None:
        self.catalog = (
            registry_or_catalog
            if isinstance(registry_or_catalog, ToolCatalog)
            else ToolCatalog.from_registry(registry_or_catalog)
        )
        self.selector = selector or HeuristicToolSelector(max_tools=12, namespace_cap=3)
        self.suite_name = suite_name

    def run(self, cases: list[ToolRetrievalCase]) -> EvalSuiteResult:
        case_results: list[EvalCaseResult] = []
        recall_scores: list[float] = []
        schema_reductions: list[float] = []
        irrelevant_rates: list[float] = []
        selected_counts: list[int] = []
        namespace_passes: list[int] = []

        full_schema_tokens = sum(
            estimate_schema_tokens(tool)
            for tool in self.catalog.openai_tools()
        )

        for case in cases:
            selection = self.selector.select(
                self.catalog,
                ToolSelectionRequest(
                    query=case.input,
                    allow_side_effects=case.allow_side_effects,
                ),
            )
            selected = set(selection.selected_names)
            expected = set(case.expected_tools)
            irrelevant = set(case.irrelevant_tools)
            recall = safe_divide(len(expected & selected), len(expected))
            irrelevant_rate = safe_divide(len(irrelevant & selected), max(1, len(selected)))
            namespace_cap_pass = _namespace_cap_passes(
                selection.namespace_counts,
                case.max_tools_per_namespace,
            )
            schema_reduction = 1.0 - safe_divide(
                selection.schema_token_estimate,
                full_schema_tokens,
            )
            passed = (
                recall == 1.0
                and irrelevant_rate == 0.0
                and namespace_cap_pass
            )

            recall_scores.append(recall)
            schema_reductions.append(schema_reduction)
            irrelevant_rates.append(irrelevant_rate)
            selected_counts.append(len(selection.selected_names))
            namespace_passes.append(1 if namespace_cap_pass else 0)
            case_results.append(EvalCaseResult(
                case_id=case.id,
                passed=passed,
                metrics={
                    "recall_at_k": recall,
                    "schema_token_reduction_rate": schema_reduction,
                    "irrelevant_exposure_rate": irrelevant_rate,
                    "selected_tool_count": len(selection.selected_names),
                    "namespace_cap_pass": 1 if namespace_cap_pass else 0,
                },
                details={
                    "selected_tools": selection.selected_names,
                    "expected_tools": case.expected_tools,
                    "namespace_counts": selection.namespace_counts,
                    "filtered_tools": selection.filtered_names,
                },
            ))

        return EvalSuiteResult(
            suite=self.suite_name,
            total_cases=len(cases),
            passed_cases=sum(1 for result in case_results if result.passed),
            metrics={
                "recall_at_k": average(recall_scores),
                "schema_token_reduction_rate": average(schema_reductions),
                "irrelevant_exposure_rate": average(irrelevant_rates),
                "avg_selected_tool_count": average(selected_counts),
                "min_selected_tool_count": min(selected_counts, default=0),
                "max_selected_tool_count": max(selected_counts, default=0),
                "namespace_cap_pass_rate": average(namespace_passes),
            },
            cases=case_results,
        )


def load_tool_retrieval_cases(path: str | Path) -> list[ToolRetrievalCase]:
    cases: list[ToolRetrievalCase] = []
    with Path(path).open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            payload = json.loads(line)
            cases.append(ToolRetrievalCase(**payload))
    return cases


def _namespace_cap_passes(
    namespace_counts: dict[str, int],
    max_tools_per_namespace: int | None,
) -> bool:
    if max_tools_per_namespace is None:
        return True
    return all(count <= max_tools_per_namespace for count in namespace_counts.values())
