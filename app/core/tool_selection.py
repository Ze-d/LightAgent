"""Catalog and selection utilities for large tool sets."""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from app.obj.types import SideEffectPolicy


UNAVAILABLE_HEALTH_STATES = {"circuit_open", "disabled", "unhealthy", "open"}


@dataclass
class ToolMetadata:
    name: str
    description: str
    parameters: dict[str, Any]
    side_effect_policy: SideEffectPolicy = "read_only"
    namespace: str = "local"
    source_type: str = "local"
    tags: frozenset[str] = field(default_factory=frozenset)
    enabled: bool = True
    health_state: str = "healthy"
    failure_count: int = 0
    success_count: int = 0
    avg_latency_ms: float = 0.0

    def to_openai_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }

    @property
    def schema_token_estimate(self) -> int:
        return estimate_schema_tokens(self.to_openai_tool())


@dataclass(frozen=True)
class ToolSelectionRequest:
    query: str
    history: Sequence[dict[str, Any]] = ()
    allow_side_effects: bool | None = None
    required_tools: Sequence[str] = ()


@dataclass(frozen=True)
class ToolSelectionResult:
    selected_names: list[str]
    scores: dict[str, float]
    filtered_names: list[str]
    namespace_counts: dict[str, int]
    schema_token_estimate: int


class ToolCatalog:
    """In-memory inventory for every discovered tool."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolMetadata] = {}

    @classmethod
    def from_registry(cls, registry: Any) -> "ToolCatalog":
        catalog = cls()
        for tool in registry.get_openai_tools():
            policy: SideEffectPolicy = "read_only"
            if hasattr(registry, "get_side_effect_policy"):
                policy = registry.get_side_effect_policy(tool["name"])
            catalog.register_from_openai_tool(tool, side_effect_policy=policy)
        return catalog

    @property
    def count(self) -> int:
        return len(self._tools)

    def register(self, metadata: ToolMetadata) -> None:
        if metadata.name in self._tools:
            raise ValueError(f"Tool already registered in catalog: {metadata.name}")
        self._tools[metadata.name] = metadata

    def register_from_openai_tool(
        self,
        tool: dict[str, Any],
        *,
        side_effect_policy: SideEffectPolicy = "read_only",
        tags: Iterable[str] = (),
        enabled: bool = True,
        health_state: str = "healthy",
    ) -> ToolMetadata:
        name = _openai_tool_name(tool)
        namespace, source_type = infer_tool_namespace(name)
        metadata = ToolMetadata(
            name=name,
            description=_openai_tool_description(tool),
            parameters=_openai_tool_parameters(tool),
            side_effect_policy=side_effect_policy,
            namespace=namespace,
            source_type=source_type,
            tags=frozenset(tags),
            enabled=enabled,
            health_state=health_state,
        )
        self.register(metadata)
        return metadata

    def get(self, name: str) -> ToolMetadata:
        return self._tools[name]

    def list_names(self) -> list[str]:
        return list(self._tools.keys())

    def all_tools(self) -> list[ToolMetadata]:
        return list(self._tools.values())

    def openai_tools(self, names: Iterable[str] | None = None) -> list[dict[str, Any]]:
        if names is None:
            return [tool.to_openai_tool() for tool in self._tools.values()]
        return [
            self._tools[name].to_openai_tool()
            for name in names
            if name in self._tools
        ]

    def record_success(self, name: str, latency_ms: float | None = None) -> None:
        metadata = self._tools.get(name)
        if metadata is None:
            return
        metadata.success_count += 1
        metadata.health_state = "healthy"
        if latency_ms is not None:
            metadata.avg_latency_ms = _rolling_average(
                metadata.avg_latency_ms,
                latency_ms,
                metadata.success_count,
            )

    def record_failure(self, name: str, *, circuit_open: bool = False) -> None:
        metadata = self._tools.get(name)
        if metadata is None:
            return
        metadata.failure_count += 1
        if circuit_open:
            metadata.health_state = "circuit_open"


class HeuristicToolSelector:
    """Deterministic top-k selector for limiting per-turn tool exposure."""

    def __init__(
        self,
        *,
        max_tools: int = 16,
        namespace_cap: int = 3,
        always_include: Iterable[str] = (),
        min_score: float = 3.0,
        token_budget: int | None = None,
        allow_side_effects: bool = True,
    ) -> None:
        self.max_tools = max_tools
        self.namespace_cap = namespace_cap
        self.always_include = tuple(always_include)
        self.min_score = min_score
        self.token_budget = token_budget
        self.allow_side_effects = allow_side_effects

    def select(
        self,
        catalog: ToolCatalog,
        request: ToolSelectionRequest,
    ) -> ToolSelectionResult:
        query = request.query or _latest_user_query(request.history)
        query_tokens = _expanded_tokens(query)
        allow_side_effects = (
            self.allow_side_effects
            if request.allow_side_effects is None
            else request.allow_side_effects
        )
        filtered_names: list[str] = []
        scores: dict[str, float] = {}
        candidates: list[tuple[float, ToolMetadata]] = []

        for metadata in catalog.all_tools():
            if not metadata.enabled:
                filtered_names.append(metadata.name)
                continue
            if metadata.health_state in UNAVAILABLE_HEALTH_STATES:
                filtered_names.append(metadata.name)
                continue
            if not allow_side_effects and metadata.side_effect_policy != "read_only":
                filtered_names.append(metadata.name)
                continue

            score = _score_tool(metadata, query_tokens, query)
            if metadata.name in self.always_include:
                score = max(score, 10_000.0)
            if metadata.name in request.required_tools:
                score = max(score, 20_000.0)
            if score < self.min_score:
                filtered_names.append(metadata.name)
                continue
            scores[metadata.name] = score
            candidates.append((score, metadata))

        candidates.sort(
            key=lambda item: (
                -item[0],
                item[1].failure_count,
                item[1].avg_latency_ms,
                item[1].name,
            )
        )

        selected: list[str] = []
        namespace_counts: Counter[str] = Counter()
        token_total = 0
        for _, metadata in candidates:
            if len(selected) >= self.max_tools:
                filtered_names.append(metadata.name)
                continue
            if (
                metadata.source_type != "local"
                and namespace_counts[metadata.namespace] >= self.namespace_cap
            ):
                filtered_names.append(metadata.name)
                continue
            next_tokens = metadata.schema_token_estimate
            if self.token_budget is not None and token_total + next_tokens > self.token_budget:
                filtered_names.append(metadata.name)
                continue
            selected.append(metadata.name)
            namespace_counts[metadata.namespace] += 1
            token_total += next_tokens

        ordered_selected = self._order_selected(selected)
        return ToolSelectionResult(
            selected_names=ordered_selected,
            scores=scores,
            filtered_names=_dedupe(filtered_names),
            namespace_counts=dict(namespace_counts),
            schema_token_estimate=token_total,
        )

    def _order_selected(self, selected: list[str]) -> list[str]:
        priority = [*self.always_include]
        ordered: list[str] = []
        for name in priority:
            if name in selected and name not in ordered:
                ordered.append(name)
        for name in selected:
            if name not in ordered:
                ordered.append(name)
        return ordered


class ScopedToolRegistryView:
    """Per-run view that exposes and executes only selected tools."""

    def __init__(
        self,
        inner_registry: Any,
        selected_names: Iterable[str],
        *,
        catalog: ToolCatalog | None = None,
    ) -> None:
        self._inner = inner_registry
        self._selected_names = _dedupe(selected_names)
        self._selected = set(self._selected_names)
        self._catalog = catalog

    def get_openai_tools(self) -> list[dict[str, Any]]:
        tools_by_name = {
            tool["name"]: tool
            for tool in self._inner.get_openai_tools()
        }
        return [
            tools_by_name[name]
            for name in self._selected_names
            if name in tools_by_name
        ]

    def call(self, name: str, **kwargs: Any) -> str:
        self._ensure_selected(name)
        return self._inner.call(name, **kwargs)

    async def call_async(self, name: str, **kwargs: Any) -> str:
        self._ensure_selected(name)
        return await self._inner.call_async(name, **kwargs)

    def is_async(self, name: str) -> bool:
        if name not in self._selected:
            return False
        return self._inner.is_async(name)

    def get_side_effect_policy(self, name: str) -> SideEffectPolicy:
        if hasattr(self._inner, "get_side_effect_policy"):
            return self._inner.get_side_effect_policy(name)
        return "read_only"

    def list_names(self) -> list[str]:
        available = set(self._inner.list_names())
        return [name for name in self._selected_names if name in available]

    def _ensure_selected(self, name: str) -> None:
        if name not in self._selected:
            raise ValueError(f"Tool not selected for this run: {name}")


def estimate_schema_tokens(tool: dict[str, Any]) -> int:
    payload = json.dumps(tool, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return max(1, (len(payload) + 3) // 4)


def infer_tool_namespace(name: str) -> tuple[str, str]:
    parts = name.split(":")
    if len(parts) >= 3 and parts[0] in {"mcp", "a2a"}:
        return f"{parts[0]}:{parts[1]}", parts[0]
    if len(parts) >= 2:
        return parts[0], "mcp"
    return "local", "local"


def _openai_tool_name(tool: dict[str, Any]) -> str:
    if "function" in tool:
        return tool["function"]["name"]
    return tool["name"]


def _openai_tool_description(tool: dict[str, Any]) -> str:
    if "function" in tool:
        return tool["function"].get("description", "")
    return tool.get("description", "")


def _openai_tool_parameters(tool: dict[str, Any]) -> dict[str, Any]:
    if "function" in tool:
        return tool["function"].get("parameters", {})
    return tool.get("parameters", {})


def _score_tool(
    metadata: ToolMetadata,
    query_tokens: set[str],
    query: str,
) -> float:
    if not query_tokens:
        return 1.0
    searchable = " ".join(
        [
            metadata.name,
            metadata.description,
            " ".join(metadata.tags),
            json.dumps(metadata.parameters, ensure_ascii=False),
        ]
    )
    tool_tokens = _expanded_tokens(searchable)
    overlap = query_tokens & tool_tokens
    score = float(len(overlap) * 2)

    lowered_searchable = searchable.lower()
    lowered_query = query.lower()
    for token in query_tokens:
        if len(token) >= 4 and token in lowered_searchable:
            score += 0.5
    for token in tool_tokens:
        if len(token) >= 5 and token in lowered_query:
            score += 0.25
    if metadata.source_type != "local":
        score -= 0.05 * metadata.failure_count
    return score


def _expanded_tokens(text: str) -> set[str]:
    tokens = {
        stemmed
        for token in _tokenize(text)
        for stemmed in [_stem(token)]
        if stemmed not in _STOPWORDS
    }
    expanded = set(tokens)
    for token in list(tokens):
        expanded.update(_SYNONYMS.get(token, set()))
    return {token for token in expanded if token and token not in _STOPWORDS}


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z0-9_]+", text.lower())


def _stem(token: str) -> str:
    for suffix in ("ing", "ed", "er", "or", "es", "s", "e"):
        if len(token) > len(suffix) + 3 and token.endswith(suffix):
            return token[: -len(suffix)]
    return token


def _latest_user_query(history: Sequence[dict[str, Any]]) -> str:
    for message in reversed(history):
        if message.get("role") == "user":
            return str(message.get("content", ""))
    return ""


def _rolling_average(previous: float, value: float, count: int) -> float:
    if count <= 1:
        return value
    return previous + (value - previous) / count


def _dedupe(names: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        result.append(name)
    return result


_SYNONYMS: dict[str, set[str]] = {
    "calculat": {"calculator", "math", "arithmetic", "expression", "evaluate"},
    "calc": {"calculator", "math", "arithmetic"},
    "math": {"calculator", "arithmetic", "expression"},
    "weather": {"forecast", "temperature"},
    "forecast": {"weather"},
    "keyword": {"extract", "keywords"},
    "regex": {"pattern", "extract", "match"},
    "tabl": {"table", "markdown", "render"},
    "markdown": {"table", "render"},
    "url": {"validate", "http", "https"},
    "hash": {"digest", "sha256", "md5"},
    "business": {"date", "days", "calendar"},
    "issue": {"ticket"},
    "memory": {"remember", "recall", "search"},
    "research": {"a2a", "agent", "delegate"},
    "delegat": {"a2a", "agent", "remote"},
}


_STOPWORDS = {
    "a",
    "an",
    "and",
    "a2a",
    "are",
    "as",
    "at",
    "by",
    "delegat",
    "delegate",
    "for",
    "from",
    "agent",
    "github",
    "in",
    "into",
    "is",
    "of",
    "on",
    "or",
    "remote",
    "remot",
    "the",
    "this",
    "that",
    "to",
    "with",
    "whether",
}
