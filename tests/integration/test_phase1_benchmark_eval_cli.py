from __future__ import annotations

import json
import os
from pathlib import Path

from tests.integration.helpers import (
    LiveMelixStack,
    run_melix_cli,
    run_phase1_canonical_cli,
)


def _combined_output(result) -> str:
    return f"{result.stdout}\n{result.stderr}"


def test_phase1_cli_smoke_covers_bench_matrix_eval_and_exports(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    stack = LiveMelixStack(repo_root, swift_backend_mode="auto", python_backend_mode="auto")

    try:
        stack.start()
        environment = stack.cli_environment(repo_root)

        bench = run_phase1_canonical_cli(repo_root, environment, case_id="bench_run_positive")
        matrix = run_phase1_canonical_cli(repo_root, environment, case_id="bench_matrix_run_positive")
        evaluation = run_phase1_canonical_cli(repo_root, environment, case_id="eval_run_positive")

        assert bench.returncode == 0, _combined_output(bench)
        assert matrix.returncode == 0, _combined_output(matrix)
        assert evaluation.returncode == 0, _combined_output(evaluation)

        bench_payload = json.loads(bench.stdout)
        matrix_payload = json.loads(matrix.stdout)
        evaluation_payload = json.loads(evaluation.stdout)

        assert bench_payload["report_path"]
        assert matrix_payload["job"]["job_id"]
        assert evaluation_payload[0]["job"]["job_id"]

        bench_list = run_melix_cli(repo_root, ["bench", "list", "--json"], environment)
        matrix_list = run_melix_cli(repo_root, ["bench", "matrix", "list", "--json"], environment)
        eval_list = run_melix_cli(repo_root, ["eval", "list", "--json"], environment)

        assert bench_list.returncode == 0, _combined_output(bench_list)
        assert matrix_list.returncode == 0, _combined_output(matrix_list)
        assert eval_list.returncode == 0, _combined_output(eval_list)

        bench_history = json.loads(bench_list.stdout)
        matrix_history = json.loads(matrix_list.stdout)
        eval_history = json.loads(eval_list.stdout)

        assert bench_history
        assert matrix_history
        assert eval_history

        bench_job_id = bench_history[0]["job_id"]
        matrix_job_id = matrix_history[0]["job_id"]
        eval_job_id = eval_history[0]["job_id"]

        bench_export_path = tmp_path / "bench.csv"
        matrix_export_path = tmp_path / "bench-matrix-summary.csv"
        eval_export_path = tmp_path / "eval-samples.jsonl"

        bench_export = run_melix_cli(
            repo_root,
            ["bench", "export-csv", "--job-id", bench_job_id, "--output", os.fspath(bench_export_path), "--json"],
            environment,
        )
        matrix_export = run_melix_cli(
            repo_root,
            [
                "bench",
                "matrix",
                "export-summary-csv",
                "--job-id",
                matrix_job_id,
                "--output",
                os.fspath(matrix_export_path),
                "--json",
            ],
            environment,
        )
        eval_export = run_melix_cli(
            repo_root,
            [
                "eval",
                "export-samples-jsonl",
                "--job-id",
                eval_job_id,
                "--output",
                os.fspath(eval_export_path),
                "--json",
            ],
            environment,
        )

        assert bench_export.returncode == 0, _combined_output(bench_export)
        assert matrix_export.returncode == 0, _combined_output(matrix_export)
        assert eval_export.returncode == 0, _combined_output(eval_export)

        assert json.loads(bench_export.stdout)["job_id"] == bench_job_id
        assert json.loads(matrix_export.stdout)["job_id"] == matrix_job_id
        assert json.loads(eval_export.stdout)["job_id"] == eval_job_id
        assert bench_export_path.exists() is True
        assert matrix_export_path.exists() is True
        assert eval_export_path.exists() is True
    finally:
        stack.stop()


def test_phase1_cli_rejects_conflicting_matrix_load_budget() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    stack = LiveMelixStack(repo_root)

    try:
        stack.start()
        result = run_phase1_canonical_cli(
            repo_root,
            stack.cli_environment(repo_root),
            case_id="bench_matrix_conflicting_load_budget_negative",
        )

        assert result.returncode != 0
        assert "Exactly one of --requests or --duration-seconds" in _combined_output(result)
    finally:
        stack.stop()


def test_phase1_cli_surfaces_unsupported_evaluation_target() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    stack = LiveMelixStack(repo_root)

    try:
        stack.start()
        result = run_phase1_canonical_cli(
            repo_root,
            stack.cli_environment(repo_root),
            case_id="eval_run_unsupported_repo_negative",
        )

        assert result.returncode != 0
        assert 'code: "unsupported_task_family"' in _combined_output(result)
        assert "Evaluation supports only text-generation" in _combined_output(result)
    finally:
        stack.stop()


def test_phase1_cli_export_fails_for_missing_job(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    stack = LiveMelixStack(repo_root)

    try:
        stack.start()
        result = run_melix_cli(
            repo_root,
            [
                "eval",
                "export-summary-csv",
                "--job-id",
                "eval-missing",
                "--output",
                os.fspath(tmp_path / "eval-missing.csv"),
            ],
            stack.cli_environment(repo_root),
        )

        assert result.returncode != 0
        assert "No evaluation rows were found for job eval-missing." in _combined_output(result)
    finally:
        stack.stop()


def test_phase1_cli_surfaces_worker_failure_after_live_workers_stop() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    stack = LiveMelixStack(repo_root, swift_backend_mode="auto", python_backend_mode="auto")

    try:
        stack.start()
        stack.stop_python_worker()
        stack.stop_swift_text_worker()

        result = run_phase1_canonical_cli(
            repo_root,
            stack.cli_environment(repo_root),
            case_id="bench_run_positive",
        )
        combined_output = _combined_output(result)

        assert result.returncode != 0
        assert "Model operation worker request failed" in combined_output
        assert "unavailable" in combined_output.lower()
    finally:
        stack.stop()
