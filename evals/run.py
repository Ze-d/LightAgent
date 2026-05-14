"""Command line entry point for runtime eval suites."""
from __future__ import annotations

import argparse
import logging
from contextlib import contextmanager
from pathlib import Path

from app.configs.logger import logger
from app.memory.document_store import DocumentMemoryStore
from app.tools.register import build_default_registry
from app.tools.memory_tools import init_memory_store

from evals.fixtures.tool_zoo import build_large_tool_registry, build_tool_zoo_registry
from evals.models import EvalSuiteResult
from evals.report import write_markdown_report
from evals.runners.checkpoint_eval import (
    CheckpointEvalRunner,
    load_checkpoint_cases,
)
from evals.runners.tool_eval import ToolEvalRunner, load_tool_cases
from evals.runners.tool_retrieval_eval import (
    ToolRetrievalEvalRunner,
    load_tool_retrieval_cases,
)


DEFAULT_TOOL_CASES = Path("evals/cases/tool_calling.jsonl")
DEFAULT_TOOL_ZOO_CASES = Path("evals/cases/tool_zoo.jsonl")
DEFAULT_TOOL_RETRIEVAL_CASES = Path("evals/cases/tool_retrieval.jsonl")
DEFAULT_CHECKPOINT_CASES = Path("evals/cases/checkpoint_recovery.jsonl")
DEFAULT_REPORT_PATH = Path("reports/evals/runtime-eval-latest.md")


@contextmanager
def _eval_logging(*, quiet: bool):
    previous_level = logger.level
    if quiet:
        logger.setLevel(logging.CRITICAL)
    try:
        yield
    finally:
        logger.setLevel(previous_level)


def run_runtime_evals(
    *,
    tool_cases_path: str | Path = DEFAULT_TOOL_CASES,
    tool_zoo_cases_path: str | Path = DEFAULT_TOOL_ZOO_CASES,
    tool_retrieval_cases_path: str | Path = DEFAULT_TOOL_RETRIEVAL_CASES,
    checkpoint_cases_path: str | Path = DEFAULT_CHECKPOINT_CASES,
    report_path: str | Path = DEFAULT_REPORT_PATH,
    quiet: bool = True,
) -> list[EvalSuiteResult]:
    with _eval_logging(quiet=quiet):
        init_memory_store(DocumentMemoryStore(base_dir="test-runtime/evals-memory"))
        tool_cases = load_tool_cases(tool_cases_path)
        tool_zoo_cases = load_tool_cases(tool_zoo_cases_path)
        tool_retrieval_cases = load_tool_retrieval_cases(tool_retrieval_cases_path)
        checkpoint_cases = load_checkpoint_cases(checkpoint_cases_path)
        results = [
            ToolEvalRunner(build_default_registry()).run(tool_cases),
            ToolEvalRunner(
                build_tool_zoo_registry(),
                suite_name="tool_calling_zoo",
            ).run(tool_zoo_cases),
            ToolRetrievalEvalRunner(build_large_tool_registry()).run(
                tool_retrieval_cases
            ),
            CheckpointEvalRunner().run(checkpoint_cases),
        ]
    write_markdown_report(results, report_path)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Agent Runtime eval suites and write a Markdown report.",
    )
    parser.add_argument(
        "--tool-cases",
        default=str(DEFAULT_TOOL_CASES),
        help="Path to tool calling JSONL cases.",
    )
    parser.add_argument(
        "--tool-zoo-cases",
        default=str(DEFAULT_TOOL_ZOO_CASES),
        help="Path to eval-only tool zoo JSONL cases.",
    )
    parser.add_argument(
        "--tool-retrieval-cases",
        default=str(DEFAULT_TOOL_RETRIEVAL_CASES),
        help="Path to tool retrieval JSONL cases.",
    )
    parser.add_argument(
        "--checkpoint-cases",
        default=str(DEFAULT_CHECKPOINT_CASES),
        help="Path to checkpoint recovery JSONL cases.",
    )
    parser.add_argument(
        "--report",
        default=str(DEFAULT_REPORT_PATH),
        help="Path to write the Markdown report.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show runtime logs during eval execution.",
    )
    args = parser.parse_args()
    results = run_runtime_evals(
        tool_cases_path=args.tool_cases,
        tool_zoo_cases_path=args.tool_zoo_cases,
        tool_retrieval_cases_path=args.tool_retrieval_cases,
        checkpoint_cases_path=args.checkpoint_cases,
        report_path=args.report,
        quiet=not args.verbose,
    )
    for result in results:
        print(
            f"{result.suite}: {result.passed_cases}/"
            f"{result.total_cases} passed ({result.pass_rate:.1%})"
        )
    print(f"Report written to {args.report}")


if __name__ == "__main__":
    main()
