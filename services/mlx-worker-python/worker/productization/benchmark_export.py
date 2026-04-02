from __future__ import annotations

import json
import time
from pathlib import Path

_EXPORT_SCHEMA_VERSION = "melix.benchmark_export.v1"


def collect_benchmark_artifacts(jobs_root: Path) -> dict[str, object]:
    jobs_root = _resolve_artifact_root(Path(jobs_root), fallback_dir="bench", job_filename="bench-job.json")
    jobs: list[dict[str, object]] = []
    results: list[dict[str, object]] = []

    _collect_benchmark_run(jobs_root, jobs=jobs, results=results)
    runs_root = jobs_root / "runs"
    if runs_root.is_dir():
        for run_root in sorted(path for path in runs_root.iterdir() if path.is_dir()):
            _collect_benchmark_run(run_root, jobs=jobs, results=results)

    return {"benchmark_jobs": jobs, "benchmark_results": results}


def collect_evaluation_artifacts(jobs_root: Path) -> dict[str, object]:
    jobs_root = _resolve_artifact_root(
        Path(jobs_root),
        fallback_dir="evaluation",
        job_filename="evaluation-job.json",
    )
    jobs: list[dict[str, object]] = []
    results: list[dict[str, object]] = []

    job_path = jobs_root / "evaluation-job.json"
    if job_path.is_file():
        jobs.append(json.loads(job_path.read_text(encoding="utf-8")))

    result_path = jobs_root / "evaluation-result.json"
    if result_path.is_file():
        results.append(json.loads(result_path.read_text(encoding="utf-8")))

    return {"evaluation_jobs": jobs, "evaluation_results": results}


def build_export_bundle(jobs_root: Path) -> dict[str, object]:
    benchmark = collect_benchmark_artifacts(jobs_root)
    evaluation = collect_evaluation_artifacts(jobs_root)
    return {
        "export_schema_version": _EXPORT_SCHEMA_VERSION,
        "exported_at_unix_ms": int(time.time() * 1000),
        **benchmark,
        **evaluation,
    }


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
        for result in run.get("evaluation_results", []):
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
    for result in run.get("evaluation_results", []):
        for metric in result.get("metrics", []):
            if metric.get("name") == metric_name:
                return float(metric["value"])
    return None


def _resolve_artifact_root(jobs_root: Path, *, fallback_dir: str, job_filename: str) -> Path:
    direct_job = jobs_root / job_filename
    direct_runs = jobs_root / "runs"
    fallback_root = jobs_root / fallback_dir
    fallback_job = fallback_root / job_filename
    fallback_runs = fallback_root / "runs"
    if direct_job.is_file() or direct_runs.is_dir():
        return jobs_root
    if fallback_job.is_file() or fallback_runs.is_dir():
        return fallback_root
    return jobs_root


def _collect_benchmark_run(
    run_root: Path,
    *,
    jobs: list[dict[str, object]],
    results: list[dict[str, object]],
) -> None:
    job_path = run_root / "bench-job.json"
    if job_path.is_file():
        jobs.append(json.loads(job_path.read_text(encoding="utf-8")))

    for result_path in sorted(run_root.glob("bench-result-*.json")):
        if result_path.is_file():
            results.append(json.loads(result_path.read_text(encoding="utf-8")))
