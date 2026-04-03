from __future__ import annotations

import csv
import json
import io
import time
from pathlib import Path

_EXPORT_SCHEMA_VERSION = "melix.benchmark_export.v1"


def collect_benchmark_artifacts(jobs_root: Path) -> dict[str, object]:
    jobs_root = _resolve_artifact_root(
        Path(jobs_root),
        fallback_dir="bench",
        job_filename="bench-job.json",
        summary_filename="bench-summary.json",
    )
    summary_rows: list[dict[str, object]] = []
    context_rows: list[dict[str, object]] = []
    batch_rows: list[dict[str, object]] = []
    results: list[dict[str, object]] = []

    _collect_benchmark_run(
        jobs_root,
        summary_rows=summary_rows,
        context_rows=context_rows,
        batch_rows=batch_rows,
        results=results,
    )
    runs_root = jobs_root / "runs"
    if runs_root.is_dir():
        for run_root in sorted(path for path in runs_root.iterdir() if path.is_dir()):
            _collect_benchmark_run(
                run_root,
                summary_rows=summary_rows,
                context_rows=context_rows,
                batch_rows=batch_rows,
                results=results,
            )

    return {
        "benchmark_jobs": summary_rows,
        "benchmark_summary_rows": summary_rows,
        "benchmark_context_rows": context_rows,
        "benchmark_batch_rows": batch_rows,
        "benchmark_results": results,
    }


def collect_evaluation_artifacts(jobs_root: Path) -> dict[str, object]:
    jobs_root = _resolve_artifact_root(
        Path(jobs_root),
        fallback_dir="evaluation",
        job_filename="evaluation-job.json",
    )
    jobs: list[dict[str, object]] = []
    results: list[dict[str, object]] = []
    samples: list[dict[str, object]] = []

    _collect_evaluation_run(jobs_root, jobs=jobs, results=results, samples=samples)
    runs_root = jobs_root / "runs"
    if runs_root.is_dir():
        for run_root in sorted(path for path in runs_root.iterdir() if path.is_dir()):
            _collect_evaluation_run(run_root, jobs=jobs, results=results, samples=samples)

    return {
        "evaluation_jobs": jobs,
        "evaluation_results": results,
        "evaluation_samples": samples,
    }


def build_export_bundle(jobs_root: Path) -> dict[str, object]:
    benchmark = collect_benchmark_artifacts(jobs_root)
    evaluation = collect_evaluation_artifacts(jobs_root)
    return {
        "export_schema_version": _EXPORT_SCHEMA_VERSION,
        "exported_at_unix_ms": int(time.time() * 1000),
        **benchmark,
        **evaluation,
    }


def build_benchmark_summary_csv(bundle: dict[str, object]) -> str:
    rows = [row for row in bundle.get("benchmark_summary_rows", []) if isinstance(row, dict)]
    return _rows_to_csv(
        rows,
        [
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
        ],
    )


def build_benchmark_context_csv(bundle: dict[str, object]) -> str:
    rows = [row for row in bundle.get("benchmark_context_rows", []) if isinstance(row, dict)]
    return _rows_to_csv(rows, _canonical_benchmark_row_columns())


def build_benchmark_batch_csv(bundle: dict[str, object]) -> str:
    rows = [row for row in bundle.get("benchmark_batch_rows", []) if isinstance(row, dict)]
    return _rows_to_csv(rows, _canonical_benchmark_row_columns())


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
    for run in runs:
        for result in run.get("benchmark_results", []):
            for metric in result.get("metrics", []):
                name = metric.get("name", "")
                if name and name not in seen:
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
        for run in runs:
            value = _find_metric_value(run, metric_name)
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


def _find_metric_value(
    run: dict[str, object],
    metric_name: str,
) -> float | None:
    for result in run.get("benchmark_results", []):
        for metric in result.get("metrics", []):
            if metric.get("name") == metric_name:
                return float(metric["value"])
    return None


def _resolve_artifact_root(
    jobs_root: Path,
    *,
    fallback_dir: str,
    job_filename: str,
    summary_filename: str | None = None,
) -> Path:
    direct_job = jobs_root / job_filename
    direct_runs = jobs_root / "runs"
    fallback_root = jobs_root / fallback_dir
    fallback_job = fallback_root / job_filename
    fallback_runs = fallback_root / "runs"
    direct_summary = jobs_root / summary_filename if summary_filename else None
    fallback_summary = fallback_root / summary_filename if summary_filename else None
    if direct_job.is_file() or direct_runs.is_dir() or (direct_summary is not None and direct_summary.is_file()):
        return jobs_root
    if fallback_job.is_file() or fallback_runs.is_dir() or (fallback_summary is not None and fallback_summary.is_file()):
        return fallback_root
    return jobs_root


def _collect_benchmark_run(
    run_root: Path,
    *,
    summary_rows: list[dict[str, object]],
    context_rows: list[dict[str, object]],
    batch_rows: list[dict[str, object]],
    results: list[dict[str, object]],
) -> None:
    summary_path = run_root / "bench-summary.json"
    job_path = run_root / "bench-job.json"
    if summary_path.is_file():
        summary_rows.append(json.loads(summary_path.read_text(encoding="utf-8")))
    elif job_path.is_file():
        summary_rows.append(json.loads(job_path.read_text(encoding="utf-8")))

    context_path = run_root / "bench-context-rows.jsonl"
    if context_path.is_file():
        for line in context_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if isinstance(row, dict):
                    context_rows.append(row)

    batch_path = run_root / "bench-batch-rows.jsonl"
    if batch_path.is_file():
        for line in batch_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if isinstance(row, dict):
                    batch_rows.append(row)

    for result_path in sorted(run_root.glob("bench-result-*.json")):
        if result_path.is_file():
            results.append(json.loads(result_path.read_text(encoding="utf-8")))


def _rows_to_csv(rows: list[dict[str, object]], fieldnames: list[str]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: _csv_value(row.get(field, "")) for field in fieldnames})
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
    ]


def _csv_value(value: object) -> str:
    if isinstance(value, list):
        return ",".join(str(item) for item in value)
    if isinstance(value, tuple):
        return ",".join(str(item) for item in value)
    if value is None:
        return ""
    return str(value)


def _collect_evaluation_run(
    run_root: Path,
    *,
    jobs: list[dict[str, object]],
    results: list[dict[str, object]],
    samples: list[dict[str, object]],
) -> None:
    job_path = run_root / "evaluation-job.json"
    if job_path.is_file():
        jobs.append(json.loads(job_path.read_text(encoding="utf-8")))

    result_path = run_root / "evaluation-result.json"
    if result_path.is_file():
        results.append(json.loads(result_path.read_text(encoding="utf-8")))

    samples_path = run_root / "evaluation-samples.jsonl"
    if samples_path.is_file():
        for line in samples_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                samples.append(json.loads(line))
