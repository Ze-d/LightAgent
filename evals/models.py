"""Shared result models for runtime eval suites."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class EvalCaseResult:
    case_id: str
    passed: bool
    metrics: dict[str, float | int] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvalSuiteResult:
    suite: str
    total_cases: int
    passed_cases: int
    metrics: dict[str, float | int] = field(default_factory=dict)
    cases: list[EvalCaseResult] = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        if self.total_cases == 0:
            return 0.0
        return self.passed_cases / self.total_cases

