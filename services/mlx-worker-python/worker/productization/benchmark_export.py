from __future__ import annotations

import csv
import json
import io
import time
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
import os
from pathlib import Path

from worker.trajectory_provenance import TRAJECTORY_PROVENANCE_CSV_FIELDS

_EXPORT_SCHEMA_VERSION = "melix.benchmark_export.v1"

_BENCHMARK_SUMMARY_COLUMNS = (
    "job_id",
    "model_id",
    "task_kind",
    "source_repo",
    "suites",
    "context_lengths",
    "generation_length",
    "batch_sizes",
    "repeats",
    "cache_profile",
    "reasoning_mode",
    "structured_output_mode",
    "request_p50_ms",
    "request_p95_ms",
    "status",
    "output_dir",
    "created_at_unix_ms",
    "updated_at_unix_ms",
)


@dataclass(frozen=True)
class _ScannedDirectoryEntries:
    directory: Path
    file_names: tuple[str, ...]
    dir_names: tuple[str, ...]
    file_name_set: frozenset[str] = field(init=False, repr=False)
    dir_name_set: frozenset[str] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "file_name_set", frozenset(self.file_names))
        object.__setattr__(self, "dir_name_set", frozenset(self.dir_names))

    def file_path(self, name: str) -> Path | None:
        if name not in self.file_name_set:
            return None
        return self.directory / name

    def has_dir(self, name: str) -> bool:
        return name in self.dir_name_set

    def matching_file_paths(self, *, prefix: str, suffix: str) -> tuple[Path, ...]:
        return tuple(
            self.directory / name
            for name in self.file_names
            if name.startswith(prefix) and name.endswith(suffix)
        )


def _scan_directory(directory: Path) -> _ScannedDirectoryEntries | None:
    try:
        file_names: list[str] = []
        dir_names: list[str] = []
        with os.scandir(directory) as entries:
            for entry in entries:
                try:
                    if entry.is_file():
                        file_names.append(entry.name)
                        continue
                    if entry.is_dir():
                        dir_names.append(entry.name)
                except OSError:
                    continue
    except OSError:
        return None
    return _ScannedDirectoryEntries(
        directory=directory,
        file_names=tuple(sorted(file_names)),
        dir_names=tuple(sorted(dir_names)),
    )


def collect_benchmark_artifacts(jobs_root: Path) -> dict[str, object]:
    jobs_root = _resolve_artifact_root(
        Path(jobs_root),
        fallback_dir="bench",
        alternate_fallback_dirs=["model-ops/bench"],
        job_filename="bench-job.json",
        summary_filename="bench-summary.json",
    )
    summary_rows: list[dict[str, object]] = []
    context_rows: list[dict[str, object]] = []
    batch_rows: list[dict[str, object]] = []
    results: list[dict[str, object]] = []
    matrix_jobs: list[dict[str, object]] = []
    matrix_summary_rows: list[dict[str, object]] = []
    matrix_request_rows: list[dict[str, object]] = []
    run_evidence: list[dict[str, object]] = []

    _collect_benchmark_run(
        jobs_root,
        summary_rows=summary_rows,
        context_rows=context_rows,
        batch_rows=batch_rows,
        results=results,
        run_evidence=run_evidence,
    )
    matrix_roots = [jobs_root]
    nested_bench_root = jobs_root / "bench"
    if nested_bench_root.is_dir() and nested_bench_root != jobs_root:
        matrix_roots.append(nested_bench_root)
    for matrix_root in matrix_roots:
        _collect_benchmark_matrix_run(
            matrix_root,
            jobs=matrix_jobs,
            summary_rows=matrix_summary_rows,
            request_rows=matrix_request_rows,
        )
    runs_root = jobs_root / "runs"
    for run_root in _iter_sorted_child_directories(runs_root):
        _collect_benchmark_run(
            run_root,
            summary_rows=summary_rows,
            context_rows=context_rows,
            batch_rows=batch_rows,
            results=results,
            run_evidence=run_evidence,
        )
    for matrix_root in matrix_roots:
        matrix_runs_root = matrix_root / "matrix-runs"
        for run_root in _iter_sorted_child_directories(matrix_runs_root):
            _collect_benchmark_matrix_run(
                run_root,
                jobs=matrix_jobs,
                summary_rows=matrix_summary_rows,
                request_rows=matrix_request_rows,
            )

    return {
        "benchmark_jobs": summary_rows,
        "benchmark_summary_rows": summary_rows,
        "benchmark_context_rows": context_rows,
        "benchmark_batch_rows": batch_rows,
        "benchmark_results": results,
        "benchmark_matrix_jobs": matrix_jobs,
        "benchmark_matrix_summary_rows": matrix_summary_rows,
        "benchmark_matrix_request_rows": matrix_request_rows,
        "run_evidence": _dedupe_run_evidence(run_evidence),
    }


def collect_evaluation_artifacts(jobs_root: Path) -> dict[str, object]:
    jobs_root = _resolve_artifact_root(
        Path(jobs_root),
        fallback_dir="evaluation",
        job_filename="evaluation-job.json",
        alternate_job_filenames=["evaluation-compare-job.json"],
    )
    jobs: list[dict[str, object]] = []
    results: list[dict[str, object]] = []
    summaries: list[dict[str, object]] = []
    samples: list[dict[str, object]] = []
    compare_jobs: list[dict[str, object]] = []
    compare_summary_rows: list[dict[str, object]] = []
    compare_samples: list[dict[str, object]] = []
    run_evidence: list[dict[str, object]] = []

    _collect_evaluation_run(
        jobs_root,
        jobs=jobs,
        results=results,
        summaries=summaries,
        samples=samples,
        compare_jobs=compare_jobs,
        compare_summary_rows=compare_summary_rows,
        compare_samples=compare_samples,
        run_evidence=run_evidence,
    )
    runs_root = jobs_root / "runs"
    for run_root in _iter_sorted_child_directories(runs_root):
        _collect_evaluation_run(
            run_root,
            jobs=jobs,
            results=results,
            summaries=summaries,
            samples=samples,
            compare_jobs=compare_jobs,
            compare_summary_rows=compare_summary_rows,
            compare_samples=compare_samples,
            run_evidence=run_evidence,
        )

    return {
        "evaluation_jobs": jobs,
        "evaluation_results": results,
        "evaluation_summary_rows": summaries,
        "evaluation_samples": samples,
        "evaluation_compare_jobs": compare_jobs,
        "evaluation_compare_summary_rows": compare_summary_rows,
        "evaluation_compare_samples": compare_samples,
        "run_evidence": _dedupe_run_evidence(run_evidence),
    }


def build_export_bundle(jobs_root: Path) -> dict[str, object]:
    jobs_root = Path(jobs_root)
    root_scan = _scan_directory(jobs_root)
    benchmark_root = _resolve_artifact_root(
        jobs_root,
        fallback_dir="bench",
        alternate_fallback_dirs=["model-ops/bench"],
        job_filename="bench-job.json",
        summary_filename="bench-summary.json",
        scanned_entries=root_scan,
    )
    evaluation_root = _resolve_artifact_root(
        jobs_root,
        fallback_dir="evaluation",
        job_filename="evaluation-job.json",
        alternate_job_filenames=["evaluation-compare-job.json"],
        scanned_entries=root_scan,
    )
    if benchmark_root == evaluation_root:
        benchmark, evaluation = _collect_shared_export_artifacts(
            shared_root=benchmark_root,
            shared_scan=root_scan if benchmark_root == jobs_root else _scan_directory(benchmark_root),
        )
    else:
        benchmark = collect_benchmark_artifacts(jobs_root)
        evaluation = collect_evaluation_artifacts(jobs_root)
    run_evidence = _dedupe_run_evidence(
        [
            *[row for row in benchmark.get("run_evidence", []) if isinstance(row, dict)],
            *[row for row in evaluation.get("run_evidence", []) if isinstance(row, dict)],
        ]
    )
    benchmark_payload = {key: value for key, value in benchmark.items() if key != "run_evidence"}
    evaluation_payload = {key: value for key, value in evaluation.items() if key != "run_evidence"}
    return {
        "export_schema_version": _EXPORT_SCHEMA_VERSION,
        "exported_at_unix_ms": int(time.time() * 1000),
        **benchmark_payload,
        **evaluation_payload,
        "run_evidence": run_evidence,
    }


def _collect_shared_export_artifacts(
    *,
    shared_root: Path,
    shared_scan: _ScannedDirectoryEntries | None,
) -> tuple[dict[str, object], dict[str, object]]:
    summary_rows: list[dict[str, object]] = []
    context_rows: list[dict[str, object]] = []
    batch_rows: list[dict[str, object]] = []
    benchmark_results: list[dict[str, object]] = []
    matrix_jobs: list[dict[str, object]] = []
    matrix_summary_rows: list[dict[str, object]] = []
    matrix_request_rows: list[dict[str, object]] = []
    evaluation_jobs: list[dict[str, object]] = []
    evaluation_results: list[dict[str, object]] = []
    evaluation_summary_rows: list[dict[str, object]] = []
    evaluation_samples: list[dict[str, object]] = []
    compare_jobs: list[dict[str, object]] = []
    compare_summary_rows: list[dict[str, object]] = []
    compare_samples: list[dict[str, object]] = []
    run_evidence: list[dict[str, object]] = []

    _collect_benchmark_run(
        shared_root,
        summary_rows=summary_rows,
        context_rows=context_rows,
        batch_rows=batch_rows,
        results=benchmark_results,
        run_evidence=run_evidence,
        scanned_entries=shared_scan,
    )
    _collect_evaluation_run(
        shared_root,
        jobs=evaluation_jobs,
        results=evaluation_results,
        summaries=evaluation_summary_rows,
        samples=evaluation_samples,
        compare_jobs=compare_jobs,
        compare_summary_rows=compare_summary_rows,
        compare_samples=compare_samples,
        run_evidence=run_evidence,
        scanned_entries=shared_scan,
    )

    matrix_roots: list[tuple[Path, _ScannedDirectoryEntries | None]] = [(shared_root, shared_scan)]
    nested_bench_root = shared_root / "bench"
    if shared_scan is not None and shared_scan.directory == shared_root:
        has_nested_bench_dir = shared_scan.has_dir("bench")
    else:
        has_nested_bench_dir = nested_bench_root.is_dir()
    if has_nested_bench_dir and nested_bench_root != shared_root:
        matrix_roots.append((nested_bench_root, None))
    for matrix_root, matrix_scan in matrix_roots:
        has_matrix_root_artifacts = False
        if matrix_scan is not None and matrix_scan.directory == matrix_root:
            has_matrix_root_artifacts = any(
                matrix_scan.file_path(name) is not None
                for name in (
                    "bench-matrix-job.json",
                    "bench-matrix-summary.jsonl",
                    "bench-matrix-requests.jsonl",
                )
            )
        else:
            has_matrix_root_artifacts = _root_contains_artifact_markers(
                matrix_root,
                job_filename="bench-matrix-job.json",
                summary_filename="bench-matrix-summary.jsonl",
                scanned_entries=matrix_scan,
            )
        if has_matrix_root_artifacts:
            _collect_benchmark_matrix_run(
                matrix_root,
                jobs=matrix_jobs,
                summary_rows=matrix_summary_rows,
                request_rows=matrix_request_rows,
            )
        matrix_runs_root = matrix_root / "matrix-runs"
        for run_root in _iter_sorted_child_directories(matrix_runs_root):
            _collect_benchmark_matrix_run(
                run_root,
                jobs=matrix_jobs,
                summary_rows=matrix_summary_rows,
                request_rows=matrix_request_rows,
            )

    runs_root = shared_root / "runs"
    for run_root in _iter_sorted_child_directories(runs_root):
        run_scan = _scan_directory(run_root)
        _collect_benchmark_run(
            run_root,
            summary_rows=summary_rows,
            context_rows=context_rows,
            batch_rows=batch_rows,
            results=benchmark_results,
            run_evidence=run_evidence,
            scanned_entries=run_scan,
        )
        _collect_evaluation_run(
            run_root,
            jobs=evaluation_jobs,
            results=evaluation_results,
            summaries=evaluation_summary_rows,
            samples=evaluation_samples,
            compare_jobs=compare_jobs,
            compare_summary_rows=compare_summary_rows,
            compare_samples=compare_samples,
            run_evidence=run_evidence,
            scanned_entries=run_scan,
        )

    benchmark = {
        "benchmark_jobs": summary_rows,
        "benchmark_summary_rows": summary_rows,
        "benchmark_context_rows": context_rows,
        "benchmark_batch_rows": batch_rows,
        "benchmark_results": benchmark_results,
        "benchmark_matrix_jobs": matrix_jobs,
        "benchmark_matrix_summary_rows": matrix_summary_rows,
        "benchmark_matrix_request_rows": matrix_request_rows,
        "run_evidence": _dedupe_run_evidence(run_evidence),
    }
    evaluation = {
        "evaluation_jobs": evaluation_jobs,
        "evaluation_results": evaluation_results,
        "evaluation_summary_rows": evaluation_summary_rows,
        "evaluation_samples": evaluation_samples,
        "evaluation_compare_jobs": compare_jobs,
        "evaluation_compare_summary_rows": compare_summary_rows,
        "evaluation_compare_samples": compare_samples,
    }
    return benchmark, evaluation


def build_evaluation_summary_csv(bundle: dict[str, object]) -> str:
    return _rows_to_csv(
        (row for row in bundle.get("evaluation_summary_rows", []) if isinstance(row, dict)),
        [
            "job_id",
            "model_id",
            "task_kind",
            "source_repo",
            "suite_id",
            "dataset_id",
            "primary_score_name",
            "primary_score_value",
            "sample_size",
            "extraction_success_count",
            "validation_success_count",
            "scored_sample_count",
            "failure_count",
            "effect_threshold",
            "verdict",
            "bootstrap_lower_bound",
            "bootstrap_upper_bound",
            "analytical_lower_bound",
            "analytical_upper_bound",
            "duration_seconds",
            "created_at_unix_ms",
        ],
    )


def build_evaluation_samples_csv(bundle: dict[str, object]) -> str:
    return _rows_to_csv(
        (
            _normalized_evaluation_sample_row(row)
            for row in bundle.get("evaluation_samples", [])
            if isinstance(row, dict)
        ),
        _canonical_evaluation_sample_columns(),
    )


def build_evaluation_compare_summary_csv(bundle: dict[str, object]) -> str:
    return _rows_to_csv(
        (row for row in bundle.get("evaluation_compare_summary_rows", []) if isinstance(row, dict)),
        [
            "job_id",
            "base_model_id",
            "target_model_id",
            "suite_id",
            "dataset_id",
            "sample_size",
            "win_count",
            "loss_count",
            "tie_count",
            "regression_count",
            "base_accuracy",
            "target_accuracy",
            "delta_accuracy",
            "duration_seconds",
        ],
    )


def build_evaluation_compare_samples_csv(bundle: dict[str, object]) -> str:
    return _rows_to_csv(
        (row for row in bundle.get("evaluation_compare_samples", []) if isinstance(row, dict)),
        [
            "job_id",
            "suite_id",
            "dataset_id",
            "sample_id",
            "target_model_id",
            "input_text",
            "target",
            "base_extracted_result",
            "target_extracted_result",
            "base_raw_response",
            "target_raw_response",
            "base_typed_score",
            "target_typed_score",
            "outcome",
            "regression_kind",
            "base_time_s",
            "target_time_s",
            "base_extraction_status",
            "target_extraction_status",
            "base_validation_status",
            "target_validation_status",
            "base_failure_reason",
            "target_failure_reason",
            "base_parse_status",
            "target_parse_status",
            "code_language",
            "code_entry_point",
            "base_code_compile_status",
            "target_code_compile_status",
            "base_code_runtime_status",
            "target_code_runtime_status",
            "base_code_timeout_status",
            "target_code_timeout_status",
            "base_code_test_status",
            "target_code_test_status",
            "base_code_tests_passed",
            "target_code_tests_passed",
            "base_code_tests_total",
            "target_code_tests_total",
            "base_code_failure_detail",
            "target_code_failure_detail",
            "category_label",
            "subject_label",
        ],
    )


def build_benchmark_summary_csv(bundle: dict[str, object]) -> str:
    return _rows_to_csv(
        (row for row in bundle.get("benchmark_summary_rows", []) if isinstance(row, dict)),
        _BENCHMARK_SUMMARY_COLUMNS,
    )


def build_benchmark_context_csv(bundle: dict[str, object]) -> str:
    return _rows_to_csv(
        (row for row in bundle.get("benchmark_context_rows", []) if isinstance(row, dict)),
        _canonical_benchmark_row_columns(),
    )


def build_benchmark_batch_csv(bundle: dict[str, object]) -> str:
    return _rows_to_csv(
        (row for row in bundle.get("benchmark_batch_rows", []) if isinstance(row, dict)),
        _canonical_benchmark_row_columns(),
    )


def build_benchmark_matrix_summary_csv(bundle: dict[str, object]) -> str:
    return _rows_to_csv(
        (row for row in bundle.get("benchmark_matrix_summary_rows", []) if isinstance(row, dict)),
        _canonical_benchmark_matrix_summary_columns(),
    )


def build_benchmark_matrix_requests_csv(bundle: dict[str, object]) -> str:
    return _rows_to_csv(
        (row for row in bundle.get("benchmark_matrix_request_rows", []) if isinstance(row, dict)),
        _canonical_benchmark_matrix_request_columns(),
    )


def write_export_bundle(jobs_root: Path, output_path: Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    bundle = build_export_bundle(jobs_root)
    output_path.write_text(
        json.dumps(bundle, indent=2) + "\n",
        encoding="utf-8",
    )
    return output_path


def build_comparison_table(runs: list[dict[str, object]]) -> str:
    if not runs:
        return ""

    all_metric_names: list[str] = []
    seen: set[str] = set()
    metric_values_by_run: list[dict[str, float]] = []
    for run in runs:
        metric_values = _collect_metric_values(run)
        metric_values_by_run.append(metric_values)
        for name in metric_values:
            if name not in seen:
                all_metric_names.append(name)
                seen.add(name)

    if not all_metric_names:
        return ""

    labels = [_run_label(run, index) for index, run in enumerate(runs)]

    header = "| Metric | " + " | ".join(labels) + " |"
    separator = "| --- | " + " | ".join("---" for _ in labels) + " |"
    rows: list[str] = []
    for metric_name in all_metric_names:
        cells: list[str] = []
        for metric_values in metric_values_by_run:
            value = metric_values.get(metric_name)
            cells.append(f"{value:.2f}" if value is not None else "-")
        rows.append(f"| {metric_name} | " + " | ".join(cells) + " |")

    return "\n".join([header, separator, *rows]) + "\n"


def _run_label(run: dict[str, object], index: int) -> str:
    jobs = run.get("benchmark_jobs", [])
    if jobs:
        job = jobs[0]
        model_id = job.get("model_id", "")
        job_id = job.get("job_id", "")
        if model_id:
            return model_id
        if job_id:
            return job_id
    return f"run-{index}"


def _collect_metric_values(run: dict[str, object]) -> dict[str, float]:
    metric_values: dict[str, float] = {}
    for result in run.get("benchmark_results", []):
        for metric in result.get("metrics", []):
            name = metric.get("name", "")
            if not name or name in metric_values:
                continue
            metric_values[name] = float(metric["value"])
    return metric_values


def _root_contains_artifact_markers(
    root: Path,
    *,
    job_filename: str,
    summary_filename: str | None = None,
    alternate_job_filenames: list[str] | None = None,
    scanned_entries: _ScannedDirectoryEntries | None = None,
) -> bool:
    file_markers = {job_filename, *(alternate_job_filenames or [])}
    if summary_filename is not None:
        file_markers.add(summary_filename)

    scan = scanned_entries if scanned_entries is not None and scanned_entries.directory == root else _scan_directory(root)
    if scan is None:
        return False
    if scan.has_dir("runs"):
        return True
    for marker in file_markers:
        if scan.file_path(marker) is not None:
            return True
    return False


def _resolve_artifact_root(
    jobs_root: Path,
    *,
    fallback_dir: str,
    alternate_fallback_dirs: list[str] | None = None,
    job_filename: str,
    summary_filename: str | None = None,
    alternate_job_filenames: list[str] | None = None,
    scanned_entries: _ScannedDirectoryEntries | None = None,
) -> Path:
    if _root_contains_artifact_markers(
        jobs_root,
        job_filename=job_filename,
        summary_filename=summary_filename,
        alternate_job_filenames=alternate_job_filenames,
        scanned_entries=scanned_entries,
    ):
        return jobs_root
    for candidate_fallback_dir in (fallback_dir, *(alternate_fallback_dirs or [])):
        fallback_root = jobs_root / candidate_fallback_dir
        if _root_contains_artifact_markers(
            fallback_root,
            job_filename=job_filename,
            summary_filename=summary_filename,
            alternate_job_filenames=alternate_job_filenames,
        ):
            return fallback_root
    return jobs_root



def _iter_sorted_child_directories(parent: Path) -> tuple[Path, ...]:
    try:
        names: list[str] = []
        with os.scandir(parent) as entries:
            for entry in entries:
                try:
                    if not entry.is_dir():
                        continue
                except OSError:
                    continue
                names.append(entry.name)
    except OSError:
        return ()
    return tuple(parent / name for name in sorted(names))


def _iter_sorted_matching_files(parent: Path, *, prefix: str, suffix: str) -> tuple[Path, ...]:
    try:
        names: list[str] = []
        with os.scandir(parent) as entries:
            for entry in entries:
                name = entry.name
                if not name.startswith(prefix) or not name.endswith(suffix):
                    continue
                try:
                    if not entry.is_file():
                        continue
                except OSError:
                    continue
                names.append(name)
    except OSError:
        return ()
    return tuple(parent / name for name in sorted(names))


def _load_json_object(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_bytes())
    if not isinstance(payload, dict):
        raise TypeError(f"expected JSON object in {path}")
    return payload


def _try_load_json_object(path: Path) -> dict[str, object] | None:
    try:
        return _load_json_object(path)
    except OSError:
        return None


def _try_iter_jsonl_dict_rows(path: Path) -> Iterator[dict[str, object]]:
    try:
        yield from _iter_jsonl_dict_rows(path)
    except OSError:
        return


def _dedupe_run_evidence(rows: Iterable[dict[str, object]]) -> list[dict[str, object]]:
    deduped: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        key = (str(row.get("schema_version", "")), str(row.get("run_id", "")))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _collect_benchmark_run(
    run_root: Path,
    *,
    summary_rows: list[dict[str, object]],
    context_rows: list[dict[str, object]],
    batch_rows: list[dict[str, object]],
    results: list[dict[str, object]],
    run_evidence: list[dict[str, object]] | None = None,
    scanned_entries: _ScannedDirectoryEntries | None = None,
) -> None:
    scan = scanned_entries if scanned_entries is not None and scanned_entries.directory == run_root else _scan_directory(run_root)
    if scan is None:
        return
    summary_path = scan.file_path("bench-summary.json")
    job_path = scan.file_path("bench-job.json")
    context_path = scan.file_path("bench-context-rows.jsonl")
    batch_path = scan.file_path("bench-batch-rows.jsonl")
    result_paths = scan.matching_file_paths(prefix="bench-result-", suffix=".json")
    evidence_path = scan.file_path("run-evidence.json")

    if summary_path is not None:
        summary_row = _try_load_json_object(summary_path)
        if summary_row is not None:
            summary_rows.append(summary_row)
        elif job_path is not None:
            job_row = _try_load_json_object(job_path)
            if job_row is not None:
                summary_rows.append(job_row)
    elif job_path is not None:
        job_row = _try_load_json_object(job_path)
        if job_row is not None:
            summary_rows.append(job_row)

    if context_path is not None:
        context_rows.extend(_try_iter_jsonl_dict_rows(context_path))

    if batch_path is not None:
        batch_rows.extend(_try_iter_jsonl_dict_rows(batch_path))

    for result_path in result_paths:
        result_row = _try_load_json_object(result_path)
        if result_row is not None:
            results.append(result_row)

    if run_evidence is not None and evidence_path is not None:
        evidence_row = _try_load_json_object(evidence_path)
        if evidence_row is not None:
            run_evidence.append(evidence_row)


def _collect_benchmark_matrix_run(
    run_root: Path,
    *,
    jobs: list[dict[str, object]],
    summary_rows: list[dict[str, object]],
    request_rows: list[dict[str, object]],
) -> None:
    job_path: Path | None = None
    summary_path: Path | None = None
    requests_path: Path | None = None

    try:
        with os.scandir(run_root) as entries:
            for entry in entries:
                name = entry.name
                try:
                    if not entry.is_file():
                        continue
                except OSError:
                    continue
                path = run_root / name
                if name == "bench-matrix-job.json":
                    job_path = path
                elif name == "bench-matrix-summary.jsonl":
                    summary_path = path
                elif name == "bench-matrix-requests.jsonl":
                    requests_path = path
    except OSError:
        return

    if job_path is not None:
        jobs.append(_load_json_object(job_path))

    if summary_path is not None:
        summary_rows.extend(_iter_jsonl_dict_rows(summary_path))

    if requests_path is not None:
        request_rows.extend(_iter_jsonl_dict_rows(requests_path))


def _iter_jsonl_dict_rows(path: Path) -> Iterator[dict[str, object]]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            row = json.loads(stripped)
            if isinstance(row, dict):
                yield row


def _rows_to_csv(rows: Iterable[dict[str, object]], fieldnames: Sequence[str]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    fields = tuple(fieldnames)
    writer.writerow(fields)

    def csv_rows() -> Iterable[list[str]]:
        for row in rows:
            row_get = row.get
            csv_row: list[str] = []
            append_value = csv_row.append
            for field in fields:
                value = row_get(field, "")
                if value is None:
                    append_value("")
                    continue
                value_type = type(value)
                if value_type is str:
                    append_value(value)
                    continue
                if value_type is int or value_type is float or value_type is bool:
                    append_value(str(value))
                    continue
                if value_type is list or value_type is tuple:
                    append_value(",".join(map(str, value)) if value else "")
                    continue
                if value_type is dict:
                    append_value(json.dumps(value, sort_keys=True) if value else "")
                    continue
                append_value(_csv_value(value))
            yield csv_row

    writer.writerows(csv_rows())
    return buffer.getvalue()


def _canonical_benchmark_row_columns() -> list[str]:
    return [
        "job_id",
        "model_id",
        "task_kind",
        "source_repo",
        "suite",
        "context_length",
        "generation_length",
        "batch_size",
        "repeat_index",
        "prefill_tokens_per_second",
        "decode_tokens_per_second",
        "ttft_ms",
        "request_latency_ms",
        "peak_memory_bytes",
        "speedup_vs_batch_1",
        "cache_profile",
        "reasoning_mode",
        "structured_output_mode",
        "dataset_materialize_ms",
        "prompt_render_ms",
        "warmup_ms",
        "prefill_ms",
        "decode_ms",
        "tokens_in",
        "tokens_out",
        "first_token_index",
        "cache_hit",
        "runtime_kind",
        "error_stage",
        "speculative_acceptance_rate",
        "speculative_rollback_rate",
        "speculative_accepted_tokens",
        "speculative_rejected_tokens",
        "speculative_fallback_count",
        "speculative_num_draft_tokens",
        "speculative_draft_model_configured",
        "speculative_draft_propose_ms",
        "speculative_target_verify_ms",
        "dflash_enabled",
        "dflash_block_size",
        "dflash_rollback_count",
        "dflash_target_hidden_layers",
        *TRAJECTORY_PROVENANCE_CSV_FIELDS,
    ]


def _canonical_evaluation_sample_columns() -> list[str]:
    return [
        "job_id",
        "suite_id",
        "id",
        "task_kind",
        "target",
        "extracted_result",
        "input_text",
        "raw_response",
        "typed_score",
        "time_s",
        "extraction_status",
        "validation_status",
        "failure_reason",
        "input_modalities",
        "media_references",
        "code_language",
        "code_entry_point",
        "code_compile_status",
        "code_runtime_status",
        "code_timeout_status",
        "code_test_status",
        "code_tests_passed",
        "code_tests_total",
        "code_failure_detail",
        "category_label",
        "subject_label",
        "sample_render_ms",
        "inference_ms",
        "extraction_ms",
        "validation_ms",
        "scoring_ms",
        "raw_response_chars",
        "extracted_result_chars",
        "failure_stage",
        *TRAJECTORY_PROVENANCE_CSV_FIELDS,
    ]


def _normalized_evaluation_sample_row(row: dict[str, object]) -> dict[str, object]:
    parse_status = row.get("parse_status", "")
    typed_score = row.get("typed_score")
    if typed_score is None:
        typed_score = 1.0 if row.get("correct", False) else 0.0
    return {
        **row,
        "id": row.get("id") or row.get("sample_id", ""),
        "input_text": row.get("input_text", row.get("question", "")),
        "target": row.get("target", row.get("expected", "")),
        "extracted_result": row.get("extracted_result", row.get("predicted", "")),
        "typed_score": typed_score,
        "extraction_status": row.get(
            "extraction_status",
            "extracted" if parse_status not in ("", None) else "",
        ),
        "validation_status": row.get(
            "validation_status",
            "validated" if ("correct" in row or "predicted" in row) else "",
        ),
        "failure_reason": row.get("failure_reason", ""),
        "task_kind": row.get("task_kind", ""),
        "input_modalities": row.get("input_modalities", []),
        "media_references": row.get("media_references", []),
        "code_language": row.get("code_language", ""),
        "code_entry_point": row.get("code_entry_point", ""),
        "code_compile_status": row.get("code_compile_status", ""),
        "code_runtime_status": row.get("code_runtime_status", ""),
        "code_timeout_status": row.get("code_timeout_status", ""),
        "code_test_status": row.get("code_test_status", ""),
        "code_tests_passed": row.get("code_tests_passed", 0),
        "code_tests_total": row.get("code_tests_total", 0),
        "code_failure_detail": row.get("code_failure_detail", ""),
        "category_label": row.get("category_label", ""),
        "subject_label": row.get("subject_label", ""),
        "sample_render_ms": row.get("sample_render_ms", 0.0),
        "inference_ms": row.get("inference_ms", 0.0),
        "extraction_ms": row.get("extraction_ms", 0.0),
        "validation_ms": row.get("validation_ms", 0.0),
        "scoring_ms": row.get("scoring_ms", 0.0),
        "raw_response_chars": row.get("raw_response_chars", len(str(row.get("raw_response", "")))),
        "extracted_result_chars": row.get(
            "extracted_result_chars",
            len(str(row.get("extracted_result", row.get("predicted", "")))),
        ),
        "failure_stage": row.get("failure_stage", ""),
        **{
            field_name: row.get(field_name, "")
            for field_name in TRAJECTORY_PROVENANCE_CSV_FIELDS
        },
    }


def _canonical_benchmark_matrix_summary_columns() -> list[str]:
    return [
        "job_id",
        "task_kind",
        "source_repo",
        "model_id",
        "suite_id",
        "context_length",
        "generation_length",
        "batch_size",
        "cache_profile",
        "reasoning_mode",
        "structured_output_mode",
        "concurrency_level",
        "repeats",
        "requests",
        "duration_seconds",
        "ttft_mean_ms",
        "ttft_std_ms",
        "request_latency_mean_ms",
        "request_latency_std_ms",
        "prefill_tokens_per_second_mean",
        "decode_tokens_per_second_mean",
        "throughput_requests_per_second",
        "throughput_tokens_per_second",
        "success_rate",
        "peak_memory_bytes_max",
        "queue_wait_mean_ms",
        "queue_wait_p95_ms",
        "cell_wall_ms",
        "completed_count",
        "failed_count",
        "ttft_p50_ms",
        "ttft_p95_ms",
        "request_latency_p50_ms",
        "request_latency_p95_ms",
        "created_at_unix_ms",
        *TRAJECTORY_PROVENANCE_CSV_FIELDS,
    ]


def _canonical_benchmark_matrix_request_columns() -> list[str]:
    return [
        "job_id",
        "cell_id",
        "task_kind",
        "suite_id",
        "context_length",
        "generation_length",
        "batch_size",
        "cache_profile",
        "reasoning_mode",
        "structured_output_mode",
        "concurrency_level",
        "repeat_index",
        "request_index",
        "ttft_ms",
        "request_latency_ms",
        "prefill_tokens_per_second",
        "decode_tokens_per_second",
        "queue_wait_ms",
        "peak_memory_bytes",
        "status",
        "error_code",
        "dataset_materialize_ms",
        "prompt_render_ms",
        "warmup_ms",
        "prefill_ms",
        "decode_ms",
        "tokens_in",
        "tokens_out",
        "first_token_index",
        "cache_hit",
        "runtime_kind",
        "error_stage",
        "speculative_acceptance_rate",
        "speculative_rollback_rate",
        "speculative_accepted_tokens",
        "speculative_rejected_tokens",
        "speculative_fallback_count",
        "speculative_num_draft_tokens",
        "speculative_draft_model_configured",
        "speculative_draft_propose_ms",
        "speculative_target_verify_ms",
        "dflash_enabled",
        "dflash_block_size",
        "dflash_rollback_count",
        "dflash_target_hidden_layers",
        "created_at_unix_ms",
        *TRAJECTORY_PROVENANCE_CSV_FIELDS,
    ]


def _csv_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        if not value:
            return ""
        return ",".join(str(item) for item in value)
    if isinstance(value, tuple):
        if not value:
            return ""
        return ",".join(str(item) for item in value)
    if isinstance(value, dict):
        if not value:
            return ""
        return json.dumps(value, sort_keys=True)
    return str(value)


def _collect_evaluation_run(
    run_root: Path,
    *,
    jobs: list[dict[str, object]],
    results: list[dict[str, object]],
    summaries: list[dict[str, object]],
    samples: list[dict[str, object]],
    compare_jobs: list[dict[str, object]],
    compare_summary_rows: list[dict[str, object]],
    compare_samples: list[dict[str, object]],
    run_evidence: list[dict[str, object]] | None = None,
    scanned_entries: _ScannedDirectoryEntries | None = None,
) -> None:
    scan = scanned_entries if scanned_entries is not None and scanned_entries.directory == run_root else _scan_directory(run_root)
    if scan is None:
        return
    job_path = scan.file_path("evaluation-job.json")
    result_path = scan.file_path("evaluation-result.json")
    summary_path = scan.file_path("evaluation-summary.json")
    samples_path = scan.file_path("evaluation-samples.jsonl")
    compare_job_path = scan.file_path("evaluation-compare-job.json")
    compare_summary_path = scan.file_path("evaluation-compare-summary.json")
    compare_samples_path = scan.file_path("evaluation-compare-samples.jsonl")
    evidence_path = scan.file_path("run-evidence.json")

    if run_evidence is not None and evidence_path is not None:
        evidence_row = _try_load_json_object(evidence_path)
        if evidence_row is not None:
            run_evidence.append(evidence_row)

    job: dict[str, object] | None = None
    if job_path is not None:
        job = _load_json_object(job_path)
        jobs.append(job)

    result: dict[str, object] | None = None
    if result_path is not None:
        result = _load_json_object(result_path)
        results.append(result)

    if summary_path is not None:
        summaries.append(_load_json_object(summary_path))
    elif job is not None and result is not None:
        summaries.append(_build_evaluation_summary_row(job, result))

    if samples_path is not None:
        samples.extend(_iter_jsonl_dict_rows(samples_path))

    if compare_job_path is None:
        return

    compare_job = _load_json_object(compare_job_path)
    compare_jobs.append(compare_job)
    jobs.append(_normalize_evaluation_compare_job(compare_job))

    if compare_summary_path is not None:
        compare_summary_payload = _load_json_object(compare_summary_path)
        for summary in _compare_target_summaries(compare_summary_payload):
            results.append(_normalize_evaluation_compare_result(summary))
            summaries.append(_normalize_evaluation_compare_summary_row(compare_job, summary))
            compare_summary_rows.append(summary)

    if compare_samples_path is not None:
        for sample in _iter_jsonl_dict_rows(compare_samples_path):
            compare_samples.append(sample)
            samples.append(
                _normalize_evaluation_compare_sample(
                    sample,
                    compare_job=compare_job,
                )
            )


def _normalize_evaluation_compare_job(compare_job: dict[str, object]) -> dict[str, object]:
    parameters = dict(compare_job.get("parameters", {}) if isinstance(compare_job.get("parameters"), dict) else {})
    target_model_ids = compare_job.get("target_model_ids", [])
    if isinstance(target_model_ids, list) and target_model_ids and "compare_target_model_ids" not in parameters:
        parameters["compare_target_model_ids"] = ",".join(str(item) for item in target_model_ids)
    parameters.setdefault("compare_mode", "base_vs_targets")
    return {
        "schema_version": "melix.evaluation_job.v1",
        "job_id": compare_job.get("job_id", ""),
        "model_id": compare_job.get("base_model_id", ""),
        "task_kind": compare_job.get("task_kind", ""),
        "source_repo": compare_job.get("source_repo", ""),
        "suite_id": compare_job.get("suite_id", ""),
        "dataset_id": compare_job.get("dataset_id", ""),
        "sample_size": compare_job.get("sample_size", 0),
        "scoring_mode": compare_job.get("scoring_mode", ""),
        "parameters": parameters,
        "status": compare_job.get("status", ""),
        "output_dir": compare_job.get("output_dir", ""),
        "created_at_unix_ms": compare_job.get("created_at_unix_ms", 0),
        "updated_at_unix_ms": compare_job.get("updated_at_unix_ms", 0),
    }


def _compare_target_summaries(compare_summary_payload: dict[str, object]) -> list[dict[str, object]]:
    rows = compare_summary_payload.get("target_summaries", [])
    return [row for row in rows if isinstance(row, dict)]


def _normalize_evaluation_compare_result(summary: dict[str, object]) -> dict[str, object]:
    preferred_metric = _preferred_compare_metric(summary)
    sample_size = int(summary.get("sample_size", 0) or 0)
    return {
        "schema_version": "melix.evaluation_result.v2",
        "job_id": summary.get("job_id", ""),
        "suite_id": summary.get("suite_id", ""),
        "dataset_id": summary.get("dataset_id", ""),
        "sample_size": sample_size,
        "primary_score_name": preferred_metric.get("name", ""),
        "primary_score_value": preferred_metric.get("value", 0.0),
        "extraction_success_count": sample_size,
        "validation_success_count": sample_size,
        "scored_sample_count": sample_size,
        "failure_count": 0,
        "duration_seconds": summary.get("duration_seconds", 0.0),
        "metrics": summary.get("metrics", []),
        "report_path": summary.get("report_path", ""),
    }


def _normalize_evaluation_compare_summary_row(
    compare_job: dict[str, object],
    summary: dict[str, object],
) -> dict[str, object]:
    preferred_metric = _preferred_compare_metric(summary)
    sample_size = int(summary.get("sample_size", compare_job.get("sample_size", 0)) or 0)
    statistical_evidence = summary.get("statistical_evidence", {})
    bootstrap = statistical_evidence.get("bootstrap", {}) if isinstance(statistical_evidence, dict) else {}
    analytical = statistical_evidence.get("analytical", {}) if isinstance(statistical_evidence, dict) else {}
    return {
        "schema_version": "melix.evaluation_summary.v2",
        "job_id": compare_job.get("job_id", ""),
        "task_kind": compare_job.get("task_kind", ""),
        "source_repo": compare_job.get("source_repo", ""),
        "model_id": summary.get("target_model_id", ""),
        "suite_id": summary.get("suite_id", compare_job.get("suite_id", "")),
        "dataset_id": summary.get("dataset_id", compare_job.get("dataset_id", "")),
        "primary_score_name": preferred_metric.get("name", ""),
        "primary_score_value": preferred_metric.get("value", 0.0),
        "sample_size": sample_size,
        "extraction_success_count": sample_size,
        "validation_success_count": sample_size,
        "scored_sample_count": sample_size,
        "failure_count": 0,
        "effect_threshold": summary.get("effect_threshold", 0.0),
        "verdict": summary.get("verdict", ""),
        "bootstrap_lower_bound": bootstrap.get("lower_bound", ""),
        "bootstrap_upper_bound": bootstrap.get("upper_bound", ""),
        "analytical_lower_bound": analytical.get("lower_bound", ""),
        "analytical_upper_bound": analytical.get("upper_bound", ""),
        "duration_seconds": summary.get("duration_seconds", 0.0),
        "created_at_unix_ms": compare_job.get("created_at_unix_ms", 0),
    }


def _normalize_evaluation_compare_sample(
    sample: dict[str, object],
    *,
    compare_job: dict[str, object],
) -> dict[str, object]:
    target_model_id = str(sample.get("target_model_id", ""))
    sample_id = str(sample.get("sample_id", ""))
    normalized_sample_id = f"{target_model_id}:{sample_id}" if target_model_id and sample_id else sample_id
    return {
        "schema_version": "melix.evaluation_sample.v2",
        "job_id": sample.get("job_id", ""),
        "suite_id": sample.get("suite_id", ""),
        "dataset_id": sample.get("dataset_id", ""),
        "sample_id": normalized_sample_id,
        "input_text": sample.get("input_text", ""),
        "target": sample.get("target", ""),
        "extracted_result": sample.get("target_extracted_result", ""),
        "task_kind": compare_job.get("task_kind", ""),
        "raw_response": sample.get("target_raw_response", ""),
        "typed_score": sample.get("target_typed_score", 0.0),
        "time_s": sample.get("target_time_s", 0.0),
        "extraction_status": sample.get("target_extraction_status", ""),
        "validation_status": sample.get("target_validation_status", ""),
        "failure_reason": sample.get("target_failure_reason", ""),
        "input_modalities": [],
        "media_references": [],
        "parse_status": sample.get("target_parse_status", ""),
        "code_language": sample.get("code_language", ""),
        "code_entry_point": sample.get("code_entry_point", ""),
        "code_compile_status": sample.get("target_code_compile_status", ""),
        "code_runtime_status": sample.get("target_code_runtime_status", ""),
        "code_timeout_status": sample.get("target_code_timeout_status", ""),
        "code_test_status": sample.get("target_code_test_status", ""),
        "code_tests_passed": sample.get("target_code_tests_passed", 0),
        "code_tests_total": sample.get("target_code_tests_total", 0),
        "code_failure_detail": sample.get("target_code_failure_detail", ""),
        "category_label": sample.get("category_label", ""),
        "subject_label": sample.get("subject_label", ""),
    }


def _preferred_compare_metric(summary: dict[str, object]) -> dict[str, object]:
    metrics = summary.get("metrics", [])
    if not isinstance(metrics, list):
        return {"name": "", "value": 0.0}
    for preferred_name in (
        "eval.compare.delta_typed_score_mean",
        "eval.compare.target_typed_score_mean",
        "eval.compare.delta_accuracy",
        "eval.compare.target_accuracy",
        "eval.compare.win_count",
    ):
        for metric in metrics:
            if isinstance(metric, dict) and metric.get("name") == preferred_name:
                return metric
    for metric in metrics:
        if isinstance(metric, dict):
            return metric
    return {"name": "", "value": 0.0}


def _compare_target_correct_count(summary: dict[str, object]) -> int:
    sample_size = int(summary.get("sample_size", 0) or 0)
    target_accuracy = float(summary.get("target_accuracy", 0.0) or 0.0)
    return max(int(round(target_accuracy * sample_size)), 0)


def _build_evaluation_summary_row(job: dict[str, object], result: dict[str, object]) -> dict[str, object]:
    metrics = result.get("metrics", [])
    primary_score_name = str(result.get("primary_score_name") or "")
    primary_score_value = result.get("primary_score_value", 0.0)
    if not primary_score_name and isinstance(metrics, list) and metrics:
        first_metric = metrics[0] if isinstance(metrics[0], dict) else {}
        primary_score_name = str(first_metric.get("name", ""))
        primary_score_value = first_metric.get("value", 0.0)
    return {
        "schema_version": result.get("schema_version", "melix.evaluation_summary.v2"),
        "job_id": job.get("job_id", ""),
        "task_kind": job.get("task_kind", ""),
        "source_repo": job.get("source_repo", ""),
        "model_id": job.get("model_id", ""),
        "suite_id": job.get("suite_id", ""),
        "dataset_id": job.get("dataset_id", ""),
        "primary_score_name": primary_score_name,
        "primary_score_value": primary_score_value,
        "sample_size": result.get("sample_size", job.get("sample_size", 0)),
        "extraction_success_count": result.get("extraction_success_count", 0),
        "validation_success_count": result.get("validation_success_count", 0),
        "scored_sample_count": result.get("scored_sample_count", 0),
        "failure_count": result.get("failure_count", 0),
        "duration_seconds": result.get("duration_seconds", 0.0),
        "created_at_unix_ms": job.get("created_at_unix_ms", 0),
    }
