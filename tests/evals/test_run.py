import json
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from evals.run import run_runtime_evals


def test_run_runtime_evals_loads_cases_and_writes_report():
    base_dir = Path("test-runtime") / f"runtime-evals-{uuid4().hex}"
    tool_cases_path = base_dir / "tool_calling.jsonl"
    checkpoint_cases_path = base_dir / "checkpoint_recovery.jsonl"
    tool_zoo_cases_path = base_dir / "tool_zoo.jsonl"
    tool_retrieval_cases_path = base_dir / "tool_retrieval.jsonl"
    report_path = base_dir / "reports" / "runtime-eval-latest.md"
    tool_cases_path.parent.mkdir(parents=True, exist_ok=True)
    tool_cases_path.write_text(
        json.dumps({
            "id": "tool_calculator",
            "input": "Calculate 18 * 7.",
            "expected_tool": "calculator",
            "expected_args": {"expression": "18 * 7"},
            "expected_answer_contains": ["done"],
        }) + "\n",
        encoding="utf-8",
    )
    checkpoint_cases_path.write_text(
        json.dumps({
            "id": "resume_read_only_once",
            "scenario": "tool_output_resume_no_repeat",
            "tool_name": "lookup",
            "side_effect_policy": "read_only",
            "expected_resume_success": True,
            "expected_duplicate_tool_count": 0,
        }) + "\n",
        encoding="utf-8",
    )
    tool_zoo_cases_path.write_text(
        json.dumps({
            "id": "zoo_keywords",
            "input": "Extract top keywords.",
            "expected_tool": "extract_keywords",
            "expected_args": {
                "text": "agent runtime agent eval tool",
                "top_k": 2,
            },
            "expected_result_contains": ["agent", "runtime"],
        }) + "\n",
        encoding="utf-8",
    )
    tool_retrieval_cases_path.write_text(
        json.dumps({
            "id": "retrieve_calculator",
            "input": "Calculate 18 * 7.",
            "expected_tools": ["calculator"],
        }) + "\n",
        encoding="utf-8",
    )

    results = run_runtime_evals(
        tool_cases_path=tool_cases_path,
        checkpoint_cases_path=checkpoint_cases_path,
        tool_zoo_cases_path=tool_zoo_cases_path,
        tool_retrieval_cases_path=tool_retrieval_cases_path,
        report_path=report_path,
    )

    assert [result.suite for result in results] == [
        "tool_calling",
        "tool_calling_zoo",
        "tool_retrieval",
        "checkpoint_recovery",
    ]
    assert report_path.exists()
    report = report_path.read_text(encoding="utf-8")
    assert "tool_calling" in report
    assert "tool_calling_zoo" in report
    assert "tool_retrieval" in report
    assert "checkpoint_recovery" in report


def test_run_runtime_evals_suppresses_expected_fault_logs_by_default(capfd):
    base_dir = Path("test-runtime") / f"runtime-evals-quiet-{uuid4().hex}"
    tool_cases_path = base_dir / "tool_calling.jsonl"
    checkpoint_cases_path = base_dir / "checkpoint_recovery.jsonl"
    tool_zoo_cases_path = base_dir / "tool_zoo.jsonl"
    tool_retrieval_cases_path = base_dir / "tool_retrieval.jsonl"
    report_path = base_dir / "reports" / "runtime-eval-latest.md"
    tool_cases_path.parent.mkdir(parents=True, exist_ok=True)
    tool_cases_path.write_text(
        json.dumps({
            "id": "tool_calculator",
            "input": "Calculate 18 * 7.",
            "expected_tool": "calculator",
            "expected_args": {"expression": "18 * 7"},
        }) + "\n",
        encoding="utf-8",
    )
    checkpoint_cases_path.write_text(
        json.dumps({
            "id": "resume_read_only_once",
            "scenario": "tool_output_resume_no_repeat",
            "tool_name": "lookup",
            "side_effect_policy": "read_only",
            "expected_resume_success": True,
            "expected_duplicate_tool_count": 0,
        }) + "\n",
        encoding="utf-8",
    )
    tool_zoo_cases_path.write_text(
        json.dumps({
            "id": "zoo_keywords",
            "input": "Extract top keywords.",
            "expected_tool": "extract_keywords",
            "expected_args": {
                "text": "agent runtime agent eval tool",
                "top_k": 2,
            },
        }) + "\n",
        encoding="utf-8",
    )
    tool_retrieval_cases_path.write_text(
        json.dumps({
            "id": "retrieve_calculator",
            "input": "Calculate 18 * 7.",
            "expected_tools": ["calculator"],
        }) + "\n",
        encoding="utf-8",
    )

    run_runtime_evals(
        tool_cases_path=tool_cases_path,
        checkpoint_cases_path=checkpoint_cases_path,
        tool_zoo_cases_path=tool_zoo_cases_path,
        tool_retrieval_cases_path=tool_retrieval_cases_path,
        report_path=report_path,
    )

    captured = capfd.readouterr()
    assert "eval injected interruption" not in captured.err


def test_eval_cli_suppresses_expected_fault_logs_by_default():
    base_dir = Path("test-runtime") / f"runtime-evals-cli-{uuid4().hex}"
    tool_cases_path = base_dir / "tool_calling.jsonl"
    checkpoint_cases_path = base_dir / "checkpoint_recovery.jsonl"
    tool_zoo_cases_path = base_dir / "tool_zoo.jsonl"
    tool_retrieval_cases_path = base_dir / "tool_retrieval.jsonl"
    report_path = base_dir / "reports" / "runtime-eval-latest.md"
    tool_cases_path.parent.mkdir(parents=True, exist_ok=True)
    tool_cases_path.write_text(
        json.dumps({
            "id": "tool_calculator",
            "input": "Calculate 18 * 7.",
            "expected_tool": "calculator",
            "expected_args": {"expression": "18 * 7"},
        }) + "\n",
        encoding="utf-8",
    )
    checkpoint_cases_path.write_text(
        json.dumps({
            "id": "resume_read_only_once",
            "scenario": "tool_output_resume_no_repeat",
            "tool_name": "lookup",
            "side_effect_policy": "read_only",
            "expected_resume_success": True,
            "expected_duplicate_tool_count": 0,
        }) + "\n",
        encoding="utf-8",
    )
    tool_zoo_cases_path.write_text(
        json.dumps({
            "id": "zoo_keywords",
            "input": "Extract top keywords.",
            "expected_tool": "extract_keywords",
            "expected_args": {
                "text": "agent runtime agent eval tool",
                "top_k": 2,
            },
        }) + "\n",
        encoding="utf-8",
    )
    tool_retrieval_cases_path.write_text(
        json.dumps({
            "id": "retrieve_calculator",
            "input": "Calculate 18 * 7.",
            "expected_tools": ["calculator"],
        }) + "\n",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "evals.run",
            "--tool-cases",
            str(tool_cases_path),
            "--checkpoint-cases",
            str(checkpoint_cases_path),
            "--tool-zoo-cases",
            str(tool_zoo_cases_path),
            "--tool-retrieval-cases",
            str(tool_retrieval_cases_path),
            "--report",
            str(report_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "eval injected interruption" not in completed.stderr
    assert "tool_calling: 1/1 passed" in completed.stdout
    assert "tool_calling_zoo: 1/1 passed" in completed.stdout
    assert "tool_retrieval: 1/1 passed" in completed.stdout
