"""Eval-only tool zoo for broad ToolRegistry coverage.

These tools are intentionally not registered in the production default registry.
They exercise varied parameter shapes and deterministic tool outputs for runtime
evaluation.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter
from datetime import date, datetime, timedelta
from io import StringIO
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from app.core.tool_registry import ToolRegistry
from app.tools.validator import create_tool_spec


class ExtractKeywordsInput(BaseModel):
    text: str
    top_k: int = Field(default=5, ge=1, le=20)


class RegexExtractInput(BaseModel):
    text: str
    pattern: str
    group: int = 0


class NormalizeWhitespaceInput(BaseModel):
    text: str


class JsonPathReadInput(BaseModel):
    json_text: str
    path: str


class CsvSummarizeInput(BaseModel):
    csv_text: str


class RenderMarkdownTableInput(BaseModel):
    headers: list[str]
    rows: list[list[str]]


class DateDiffInput(BaseModel):
    start_date: str
    end_date: str


class AddBusinessDaysInput(BaseModel):
    start_date: str
    days: int = Field(ge=0, le=365)


class SplitTasksInput(BaseModel):
    text: str


class PrioritizeTasksInput(BaseModel):
    tasks: list[str]
    priority_keyword: str = "urgent"


class ValidateUrlInput(BaseModel):
    url: str


class HashTextInput(BaseModel):
    text: str
    algorithm: str = "sha256"


class DedupeLinesInput(BaseModel):
    text: str
    case_sensitive: bool = False


class SortItemsInput(BaseModel):
    items: list[str]
    reverse: bool = False


class TemplateRenderInput(BaseModel):
    template: str
    values: dict[str, Any]


class GenericQueryInput(BaseModel):
    query: str = ""


def extract_keywords(text: str, top_k: int = 5) -> str:
    words = [
        word.lower()
        for word in re.findall(r"[A-Za-z0-9_]+", text)
        if len(word) > 2
    ]
    counts = Counter(words)
    first_index = {word: words.index(word) for word in counts}
    ranked = sorted(counts, key=lambda word: (-counts[word], first_index[word]))
    return json.dumps(ranked[:top_k], ensure_ascii=False)


def regex_extract(text: str, pattern: str, group: int = 0) -> str:
    matches: list[str] = []
    for match in re.finditer(pattern, text):
        try:
            matches.append(match.group(group))
        except IndexError:
            return f"Invalid regex group: {group}"
    return json.dumps(matches, ensure_ascii=False)


def normalize_whitespace(text: str) -> str:
    return " ".join(text.split())


def json_path_read(json_text: str, path: str) -> str:
    try:
        current: Any = json.loads(json_text)
    except json.JSONDecodeError as exc:
        return f"Invalid JSON: {exc.msg}"
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit():
            index = int(part)
            if index >= len(current):
                return f"Path not found: {path}"
            current = current[index]
        else:
            return f"Path not found: {path}"
    return json.dumps(current, ensure_ascii=False)


def csv_summarize(csv_text: str) -> str:
    rows = list(csv.reader(StringIO(csv_text)))
    if not rows:
        return json.dumps({"columns": 0, "data_rows": 0}, ensure_ascii=False)
    return json.dumps(
        {
            "columns": len(rows[0]),
            "data_rows": max(0, len(rows) - 1),
            "headers": rows[0],
        },
        ensure_ascii=False,
    )


def render_markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    header_line = "| " + " | ".join(headers) + " |"
    separator = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([header_line, separator, *body])


def date_diff(start_date: str, end_date: str) -> str:
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    return str((end - start).days)


def add_business_days(start_date: str, days: int) -> str:
    current = _parse_date(start_date)
    remaining = days
    while remaining > 0:
        current += timedelta(days=1)
        if current.weekday() < 5:
            remaining -= 1
    return current.isoformat()


def split_tasks(text: str) -> str:
    parts = re.split(r"[\n;,]+", text)
    tasks = [part.strip(" -\t") for part in parts if part.strip(" -\t")]
    return json.dumps(tasks, ensure_ascii=False)


def prioritize_tasks(tasks: list[str], priority_keyword: str = "urgent") -> str:
    keyword = priority_keyword.lower()
    ordered = sorted(
        tasks,
        key=lambda task: (keyword not in task.lower(), tasks.index(task)),
    )
    return json.dumps(ordered, ensure_ascii=False)


def validate_url(url: str) -> str:
    parsed = urlparse(url)
    valid = parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    return json.dumps({"valid": valid, "scheme": parsed.scheme}, ensure_ascii=False)


def hash_text(text: str, algorithm: str = "sha256") -> str:
    if algorithm not in {"sha256", "md5"}:
        return f"Unsupported hash algorithm: {algorithm}"
    digest = hashlib.new(algorithm)
    digest.update(text.encode("utf-8"))
    return digest.hexdigest()


def dedupe_lines(text: str, case_sensitive: bool = False) -> str:
    seen: set[str] = set()
    lines: list[str] = []
    for line in text.splitlines():
        key = line if case_sensitive else line.lower()
        if key in seen:
            continue
        seen.add(key)
        lines.append(line)
    return "\n".join(lines)


def sort_items(items: list[str], reverse: bool = False) -> str:
    return json.dumps(sorted(items, reverse=reverse), ensure_ascii=False)


def template_render(template: str, values: dict[str, Any]) -> str:
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{{" + key + "}}", str(value))
    return rendered


def generic_eval_tool(query: str = "") -> str:
    return f"ok:{query}"


def build_tool_zoo_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(create_tool_spec(
        "extract_keywords", "Extract top keywords from text.",
        ExtractKeywordsInput, extract_keywords,
    ))
    registry.register(create_tool_spec(
        "regex_extract", "Extract regex matches from text.",
        RegexExtractInput, regex_extract,
    ))
    registry.register(create_tool_spec(
        "normalize_whitespace", "Collapse repeated whitespace.",
        NormalizeWhitespaceInput, normalize_whitespace,
    ))
    registry.register(create_tool_spec(
        "json_path_read", "Read a dotted path from JSON text.",
        JsonPathReadInput, json_path_read,
    ))
    registry.register(create_tool_spec(
        "csv_summarize", "Summarize CSV headers and data rows.",
        CsvSummarizeInput, csv_summarize,
    ))
    registry.register(create_tool_spec(
        "render_markdown_table", "Render rows as a Markdown table.",
        RenderMarkdownTableInput, render_markdown_table,
    ))
    registry.register(create_tool_spec(
        "date_diff", "Calculate day difference between ISO dates.",
        DateDiffInput, date_diff,
    ))
    registry.register(create_tool_spec(
        "add_business_days", "Add business days to an ISO date.",
        AddBusinessDaysInput, add_business_days,
    ))
    registry.register(create_tool_spec(
        "split_tasks", "Split free text into task items.",
        SplitTasksInput, split_tasks,
    ))
    registry.register(create_tool_spec(
        "prioritize_tasks", "Move keyword-matching tasks first.",
        PrioritizeTasksInput, prioritize_tasks,
    ))
    registry.register(create_tool_spec(
        "validate_url", "Validate HTTP or HTTPS URLs.",
        ValidateUrlInput, validate_url,
    ))
    registry.register(create_tool_spec(
        "hash_text", "Hash text with a deterministic algorithm.",
        HashTextInput, hash_text,
    ))
    registry.register(create_tool_spec(
        "dedupe_lines", "Remove duplicate lines while preserving order.",
        DedupeLinesInput, dedupe_lines,
    ))
    registry.register(create_tool_spec(
        "sort_items", "Sort a list of strings.",
        SortItemsInput, sort_items,
    ))
    registry.register(create_tool_spec(
        "template_render", "Render a small {{key}} template.",
        TemplateRenderInput, template_render,
    ))
    return registry


def build_large_tool_registry(noise_tool_count: int = 40) -> ToolRegistry:
    """Build an eval-only registry large enough to test tool retrieval."""
    from app.tools.register import build_default_registry

    registry = ToolRegistry()
    _copy_registry_tools(registry, build_default_registry())
    _copy_registry_tools(registry, build_tool_zoo_registry())

    remote_tools = [
        (
            "mcp:github:search_issues",
            "Search GitHub issues by repository, label, author, or text query.",
            "read_only",
        ),
        (
            "mcp:github:create_issue",
            "Create a GitHub issue with title, body, labels, and assignees.",
            "non_idempotent",
        ),
        (
            "mcp:github:list_pull_requests",
            "List GitHub pull requests for a repository.",
            "read_only",
        ),
        (
            "a2a:researcher:run",
            "Delegate deep research tasks to a remote A2A researcher agent.",
            "idempotent",
        ),
        (
            "a2a:reporter:run",
            "Delegate report writing and synthesis to a remote A2A reporter agent.",
            "idempotent",
        ),
    ]
    for name, description, policy in remote_tools:
        registry.register(create_tool_spec(
            name,
            description,
            GenericQueryInput,
            generic_eval_tool,
            side_effect_policy=policy,
        ))

    for index in range(noise_tool_count):
        registry.register(create_tool_spec(
            f"noise_tool_{index:02d}",
            f"Archive unrelated administrative record number {index}.",
            GenericQueryInput,
            generic_eval_tool,
        ))
    return registry


def _copy_registry_tools(target: ToolRegistry, source: ToolRegistry) -> None:
    for spec in source.list_specs():
        target.register(spec)


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()
