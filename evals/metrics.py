"""Metric helpers for runtime eval suites."""
from __future__ import annotations


def safe_divide(numerator: float | int, denominator: float | int) -> float:
    if denominator == 0:
        return 0.0
    return float(numerator) / float(denominator)


def average(values: list[float | int]) -> float:
    if not values:
        return 0.0
    return sum(float(item) for item in values) / len(values)

