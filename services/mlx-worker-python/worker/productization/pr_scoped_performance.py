from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import fnmatch
import gc
import os
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import tracemalloc
import types
from typing import Any


def _glob_has_magic(glob: str) -> bool:
    return any(character in glob for character in "*?[")


_COMMENT_MARKER = "<!-- melix-pr-scoped-performance-report -->"
_SCOPE_SCHEMA_VERSION = "melix.pr_scoped_performance_scope.v1"
_PROBE_RESULT_SCHEMA_VERSION = "melix.pr_scoped_performance_probe_result.v1"
_REPORT_SCHEMA_VERSION = "melix.pr_scoped_performance_report.v1"
_FORCE_ALL_GLOBS = (
    ".github/workflows/pr-scoped-performance.yml",
    "infra/perf/pr_scoped_probes.json",
    "scripts/pr_scoped_performance_*.py",
    "services/mlx-worker-python/worker/productization/pr_scoped_performance.py",
    "services/mlx-worker-python/tests/test_pr_scoped_performance.py",
)
_FORCE_ALL_EXACT_PATHS = frozenset(glob for glob in _FORCE_ALL_GLOBS if not _glob_has_magic(glob))
_FORCE_ALL_WILDCARD_GLOBS = tuple(glob for glob in _FORCE_ALL_GLOBS if _glob_has_magic(glob))
_COVERAGE_PERCENT_RE = re.compile(r"TOTAL\s+\d+\s+\d+\s+(\d+)%")
_TEXT_FILE_SUFFIXES = {".md", ".py", ".json", ".txt", ".yaml", ".yml"}


@dataclass(frozen=True)
class MetricDefinition:
    key: str
    unit: str
    direction: str
    warn_pct: float = 5.0

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "unit": self.unit,
            "direction": self.direction,
            "warn_pct": self.warn_pct,
        }


@dataclass(frozen=True)
class ProbeDefinition:
    probe_id: str
    name: str
    runner: str
    watch_globs: tuple[str, ...]
    test_command: str
    coverage_command: str
    probe_impl: str
    probe_command: str
    metrics: tuple[MetricDefinition, ...]
    coverage_replays_tests: bool = False

    def to_scope_dict(self) -> dict[str, object]:
        return {
            "id": self.probe_id,
            "name": self.name,
            "runner": self.runner,
            "watch_globs": list(self.watch_globs),
            "test_command": self.test_command,
            "coverage_command": self.coverage_command,
            "probe_command": self.probe_command,
            "coverage_replays_tests": self.coverage_replays_tests,
            "metrics": [metric.to_dict() for metric in self.metrics],
        }


_PROBE_REGISTRY_CACHE: dict[str, tuple[int, int, tuple[ProbeDefinition, ...]]] = {}


def _probe_registry_cache_key(path: str | Path) -> str:
    return os.path.abspath(os.fspath(path))


def load_probe_registry(path: str | Path) -> tuple[ProbeDefinition, ...]:
    path_obj = Path(path)
    cache_key = _probe_registry_cache_key(path_obj)
    stat_result = path_obj.stat()
    cached = _PROBE_REGISTRY_CACHE.get(cache_key)
    if cached is not None and cached[0] == stat_result.st_mtime_ns and cached[1] == stat_result.st_size:
        return cached[2]

    payload = json.loads(path_obj.read_bytes())
    if not isinstance(payload, list):
        raise ValueError("probe registry must be a JSON list")
    probes: list[ProbeDefinition] = []
    for raw_probe in payload:
        if not isinstance(raw_probe, dict):
            raise ValueError("probe registry entries must be JSON objects")
        raw_metrics = raw_probe.get("metrics", [])
        if not isinstance(raw_metrics, list) or not raw_metrics:
            raise ValueError("probe registry metrics must be a non-empty list")
        metrics = tuple(
            MetricDefinition(
                key=str(raw_metric["key"]),
                unit=str(raw_metric.get("unit", "value")),
                direction=str(raw_metric["direction"]),
                warn_pct=float(raw_metric.get("warn_pct", 5.0)),
            )
            for raw_metric in raw_metrics
            if isinstance(raw_metric, dict)
        )
        probes.append(
            ProbeDefinition(
                probe_id=str(raw_probe["id"]),
                name=str(raw_probe["name"]),
                runner=str(raw_probe.get("runner", "ubuntu-latest")),
                watch_globs=tuple(str(glob) for glob in raw_probe.get("watch_globs", [])),
                test_command=str(raw_probe.get("test_command", "")).strip(),
                coverage_command=str(raw_probe.get("coverage_command", "")).strip(),
                probe_impl=str(raw_probe["probe_impl"]),
                probe_command=str(raw_probe.get("probe_command", "")).strip(),
                metrics=metrics,
                coverage_replays_tests=bool(raw_probe.get("coverage_replays_tests", False)),
            )
        )
    probe_tuple = tuple(probes)
    _PROBE_REGISTRY_CACHE[cache_key] = (stat_result.st_mtime_ns, stat_result.st_size, probe_tuple)
    return probe_tuple


def load_probe_registry_for_scope(path: str | Path) -> tuple[ProbeDefinition, ...]:
    registry_path = Path(path)
    cache_key = _probe_registry_cache_key(registry_path)
    stat_result = registry_path.stat()
    return _load_probe_registry_for_scope_cached(
        cache_key,
        stat_result.st_mtime_ns,
        stat_result.st_size,
    )


@lru_cache(maxsize=None)
def _load_probe_registry_for_scope_cached(
    registry_path: str,
    _mtime_ns: int,
    _size: int,
) -> tuple[ProbeDefinition, ...]:
    return load_probe_registry(registry_path)


def build_scope_report(
    *,
    registry_path: str | Path,
    changed_files: list[str],
) -> dict[str, object]:
    probes = load_probe_registry_for_scope(registry_path)
    changed_path_set = {path for path in changed_files if path}
    force_all = any(_path_matches_force_all(path) for path in changed_path_set)
    if force_all:
        selected = probes
    else:
        matched_probe_indexes = _match_probe_indexes(changed_paths=changed_path_set, probes=probes)
        selected = tuple(probe for index, probe in enumerate(probes) if index in matched_probe_indexes)
    changed_paths = tuple(sorted(changed_path_set))
    return {
        "schema_version": _SCOPE_SCHEMA_VERSION,
        "changed_files": list(changed_paths),
        "force_all": force_all,
        "selected_probes": [probe.to_scope_dict() for probe in selected],
        "selected_count": len(selected),
    }


def run_probe_job(
    *,
    registry_path: str | Path,
    probe_id: str,
    base_repo: str | Path,
    head_repo: str | Path,
) -> tuple[dict[str, object], bool]:
    probes = {probe.probe_id: probe for probe in load_probe_registry(registry_path)}
    probe = probes.get(probe_id)
    if probe is None:
        raise ValueError(f"unknown probe id: {probe_id}")

    head_verification = _run_head_verification(probe=probe, repo_root=Path(head_repo))
    base_probe = _run_probe_impl(probe=probe, repo_root=Path(base_repo), repo_label="base")
    head_probe = _run_probe_impl(probe=probe, repo_root=Path(head_repo), repo_label="head")
    success = (
        head_verification["test"]["ok"]
        and head_verification["coverage"]["ok"]
        and base_probe["ok"]
        and head_probe["ok"]
    )
    return (
        {
            "schema_version": _PROBE_RESULT_SCHEMA_VERSION,
            "probe": probe.to_scope_dict(),
            "head_verification": head_verification,
            "base_probe": base_probe,
            "head_probe": head_probe,
        },
        success,
    )


def build_performance_report(
    *,
    scope: dict[str, object],
    probe_results: list[dict[str, object]],
) -> dict[str, object]:
    selected_probes = _dict_list(scope.get("selected_probes"))
    probe_result_map = {
        str(result.get("probe", {}).get("id", "")): result
        for result in probe_results
        if isinstance(result, dict)
    }
    rows: list[dict[str, object]] = []
    regression_count = 0
    verification_failure_count = 0
    for probe_entry in selected_probes:
        probe_id = str(probe_entry.get("id", "")).strip()
        if not probe_id:
            continue
        result = probe_result_map.get(probe_id)
        if result is None:
            rows.append(
                {
                    "probe_id": probe_id,
                    "name": str(probe_entry.get("name", probe_id)),
                    "status": "missing_result",
                    "metrics": [],
                    "coverage_pct": None,
                    "test_ok": False,
                    "coverage_ok": False,
                    "details": "Probe result artifact is missing.",
                }
            )
            verification_failure_count += 1
            continue
        row = _build_probe_report_row(result)
        rows.append(row)
        if row["status"] == "regression":
            regression_count += 1
        if row["status"] in {"verification_failed", "probe_failed", "missing_result"}:
            verification_failure_count += 1
    status = "ok"
    if verification_failure_count:
        status = "verification_failed"
    elif regression_count:
        status = "regression"
    return {
        "schema_version": _REPORT_SCHEMA_VERSION,
        "summary": {
            "status": status,
            "changed_file_count": len(_string_list(scope.get("changed_files"))),
            "selected_probe_count": len(selected_probes),
            "regression_count": regression_count,
            "verification_failure_count": verification_failure_count,
            "force_all": bool(scope.get("force_all", False)),
        },
        "changed_files": _string_list(scope.get("changed_files")),
        "rows": rows,
    }


def render_terminal_report(report: dict[str, object]) -> str:
    summary = report.get("summary", {})
    lines = [
        "Melix PR Scoped Performance Report",
        f"Status: {summary.get('status', 'ok')}",
        f"Changed files: {summary.get('changed_file_count', 0)}",
        f"Selected probes: {summary.get('selected_probe_count', 0)}",
        f"Regressions: {summary.get('regression_count', 0)}",
        f"Verification failures: {summary.get('verification_failure_count', 0)}",
        "",
    ]
    rows = _dict_list(report.get("rows"))
    if not rows:
        lines.append("No registered performance probes were selected for this change set.")
        return "\n".join(lines) + "\n"
    for row in rows:
        lines.extend(_render_probe_terminal_block(row))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_markdown_report(report: dict[str, object]) -> str:
    summary = report.get("summary", {})
    lines = [
        "# Melix PR Scoped Performance Report",
        "",
        f"- Status: `{summary.get('status', 'ok')}`",
        f"- Changed files: `{summary.get('changed_file_count', 0)}`",
        f"- Selected probes: `{summary.get('selected_probe_count', 0)}`",
        f"- Regressions: `{summary.get('regression_count', 0)}`",
        f"- Verification failures: `{summary.get('verification_failure_count', 0)}`",
        "",
    ]
    changed_files = _string_list(report.get("changed_files"))
    if changed_files:
        lines.append("## Changed Files")
        lines.append("")
        for path in changed_files[:20]:
            lines.append(f"- `{path}`")
        if len(changed_files) > 20:
            lines.append(f"- `... (+{len(changed_files) - 20} more)`")
        lines.append("")
    rows = _dict_list(report.get("rows"))
    if not rows:
        lines.append("No registered performance probes were selected for this pull request.")
        lines.append("")
        return "\n".join(lines)
    for row in rows:
        lines.extend(_render_probe_markdown_block(row))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build_sticky_comment_body(markdown_report: str) -> str:
    return f"{_COMMENT_MARKER}\n{markdown_report.rstrip()}\n"


def write_report_outputs(
    report: dict[str, object],
    output_dir: str | Path,
    *,
    markdown_report: str | None = None,
    sticky_comment: bool = False,
) -> dict[str, Path]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / "report.json"
    markdown_path = root / "report.md"
    markdown = render_markdown_report(report) if markdown_report is None else markdown_report
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(markdown, encoding="utf-8")
    outputs = {"json": json_path, "markdown": markdown_path}
    if sticky_comment:
        sticky_comment_path = root / "pr-comment.md"
        sticky_comment_path.write_text(build_sticky_comment_body(markdown), encoding="utf-8")
        outputs["sticky_comment"] = sticky_comment_path
    return outputs


def _run_head_verification(*, probe: ProbeDefinition, repo_root: Path) -> dict[str, object]:
    if probe.coverage_replays_tests:
        coverage_result = _run_command(probe.coverage_command, cwd=repo_root)
        test_result = {
            "command": probe.test_command,
            "ok": coverage_result["ok"],
            "returncode": coverage_result["returncode"],
            "stdout": "Skipped standalone test command because coverage_command reruns the focused pytest selection.\n",
            "stderr": "",
            "coverage_pct": None,
        }
        return {"test": test_result, "coverage": coverage_result}
    test_result = _run_command(probe.test_command, cwd=repo_root)
    coverage_result = (
        _run_command(probe.coverage_command, cwd=repo_root)
        if test_result["ok"]
        else {
            "command": probe.coverage_command,
            "ok": False,
            "returncode": None,
            "stdout": "",
            "stderr": "Skipped because the targeted test command failed.\n",
            "coverage_pct": None,
        }
    )
    return {"test": test_result, "coverage": coverage_result}


def _run_command(command: str, *, cwd: Path) -> dict[str, object]:
    completed = subprocess.run(
        command,
        shell=True,
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    return {
        "command": command,
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "coverage_pct": _parse_coverage_percent(stdout),
    }


def _run_probe_impl(*, probe: ProbeDefinition, repo_root: Path, repo_label: str) -> dict[str, object]:
    started = time.perf_counter()
    try:
        metrics = _dispatch_probe_impl(probe=probe, repo_root=repo_root)
        return {
            "repo_label": repo_label,
            "ok": True,
            "elapsed_ms": round((time.perf_counter() - started) * 1000.0, 3),
            "metrics": metrics,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "repo_label": repo_label,
            "ok": False,
            "elapsed_ms": round((time.perf_counter() - started) * 1000.0, 3),
            "error": f"{type(exc).__name__}: {exc}",
            "metrics": {},
        }


def _dispatch_probe_impl(*, probe: ProbeDefinition, repo_root: Path) -> dict[str, float]:
    if probe.probe_impl == "benchmark_evaluation_report":
        return _probe_benchmark_evaluation_report(repo_root)
    if probe.probe_impl == "benchmark_export_run_scan":
        return _probe_benchmark_export_run_scan(repo_root)
    if probe.probe_impl == "benchmark_queue_cache":
        return _probe_benchmark_queue_cache(repo_root)
    if probe.probe_impl == "closure_audit":
        return _probe_closure_audit(repo_root)
    if probe.probe_impl == "deterministic_rerank_query_context_reuse":
        return _probe_deterministic_rerank_query_context_reuse(repo_root)
    if probe.probe_impl == "evaluation_store_compare_summary_csv_streaming":
        return _probe_evaluation_store_compare_summary_csv_streaming(repo_root)
    if probe.probe_impl == "evaluation_store_samples_csv_streaming":
        return _probe_evaluation_store_samples_csv_streaming(repo_root)
    if probe.probe_impl == "evaluation_sample_probe_aggregation":
        return _probe_evaluation_sample_probe_aggregation(repo_root)
    if probe.probe_impl == "evaluation_job_id":
        return _probe_evaluation_job_id(repo_root)
    if probe.probe_impl == "training_dataset_token_percentiles":
        return _probe_training_dataset_token_percentiles(repo_root)
    if probe.probe_impl == "upload_receipt_published_files":
        return _probe_upload_receipt_published_files(repo_root)
    if probe.probe_impl == "pr_scoped_scope_matcher":
        return _probe_pr_scoped_scope_matcher(repo_root)
    if probe.probe_impl == "model_ops_bundle_artifact_bytes":
        return _probe_model_ops_bundle_artifact_bytes(repo_root)
    if probe.probe_impl == "pr_scoped_performance_registry_cache":
        return _probe_pr_scoped_performance_registry_cache(repo_root)
    if probe.probe_impl == "command_json":
        return _probe_command_json(probe=probe, repo_root=repo_root)
    raise ValueError(f"unsupported probe implementation: {probe.probe_impl}")


def _probe_command_json(*, probe: ProbeDefinition, repo_root: Path) -> dict[str, float]:
    if not probe.probe_command:
        raise ValueError("command_json probes require a non-empty probe_command")
    completed = subprocess.run(
        probe.probe_command,
        shell=True,
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "probe_command failed "
            f"with exit {completed.returncode}: {(completed.stderr or completed.stdout).strip()}"
        )
    stdout = completed.stdout.strip()
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(f"probe_command must emit JSON object metrics: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("probe_command must emit a JSON object")
    metrics: dict[str, float] = {}
    for key, value in payload.items():
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ValueError(f"probe_command metric {key} must be numeric")
        metrics[str(key)] = float(value)
    return metrics


def _probe_pr_scoped_performance_registry_cache(repo_root: Path) -> dict[str, float]:
    module = _load_repo_module(
        repo_root / "services/mlx-worker-python/worker/productization/pr_scoped_performance.py",
        unique_name="melix_probe_pr_scoped_performance_registry_cache",
    )
    registry_path = repo_root / "infra/perf/pr_scoped_probes.json"
    changed_files = [
        "services/mlx-worker-python/worker/productization/pr_scoped_performance.py",
        "services/mlx-worker-python/tests/test_pr_scoped_performance.py",
    ]
    load_iterations = 400
    cold_load_iterations = 60
    scope_iterations = 200
    sample_count = 6
    load_samples: list[float] = []
    cold_load_samples: list[float] = []
    scope_samples: list[float] = []
    cache = getattr(module, "_PROBE_REGISTRY_CACHE", None)

    for _ in range(sample_count):
        if isinstance(cache, dict):
            cache.clear()
        started = time.perf_counter()
        for _ in range(load_iterations):
            module.load_probe_registry(registry_path)
        load_samples.append((time.perf_counter() - started) * 1000.0)

        started = time.perf_counter()
        for _ in range(cold_load_iterations):
            if isinstance(cache, dict):
                cache.clear()
            module.load_probe_registry(registry_path)
        cold_load_samples.append((time.perf_counter() - started) * 1000.0)

        if isinstance(cache, dict):
            cache.clear()
        started = time.perf_counter()
        for _ in range(scope_iterations):
            module.build_scope_report(registry_path=registry_path, changed_files=changed_files)
        scope_samples.append((time.perf_counter() - started) * 1000.0)

    return {
        "load_probe_registry_iterations": float(load_iterations),
        "load_probe_registry_ms_mean": round(sum(load_samples) / len(load_samples), 6),
        "cold_load_probe_registry_iterations": float(cold_load_iterations),
        "cold_load_probe_registry_ms_mean": round(sum(cold_load_samples) / len(cold_load_samples), 6),
        "build_scope_report_iterations": float(scope_iterations),
        "build_scope_report_ms_mean": round(sum(scope_samples) / len(scope_samples), 6),
        "sample_count": float(sample_count),
    }


def _probe_benchmark_evaluation_report(repo_root: Path) -> dict[str, float]:
    module = _load_repo_module(
        repo_root / "services/mlx-worker-python/worker/productization/benchmark_evaluation_report.py",
        unique_name="melix_probe_benchmark_evaluation_report",
    )
    baseline = _build_large_benchmark_bundle(base_value=100.0)
    candidate = _build_large_benchmark_bundle(base_value=108.0)
    elapsed_samples: list[float] = []
    peak_samples: list[float] = []
    row_count = 0.0
    for _ in range(3):
        gc.collect()
        tracemalloc.start()
        started = time.perf_counter()
        report = module.build_benchmark_evaluation_report(baseline=baseline, candidate=candidate)
        elapsed_samples.append((time.perf_counter() - started) * 1000.0)
        _, peak_bytes = tracemalloc.get_traced_memory()
        peak_samples.append(float(peak_bytes))
        tracemalloc.stop()
        row_count = float(len(report.get("rows", [])))
    return {
        "elapsed_ms_mean": round(sum(elapsed_samples) / len(elapsed_samples), 3),
        "peak_bytes_mean": round(sum(peak_samples) / len(peak_samples), 1),
        "row_count": row_count,
    }


def _probe_benchmark_export_run_scan(repo_root: Path) -> dict[str, float]:
    module = _load_repo_module(
        repo_root / "services/mlx-worker-python/worker/productization/benchmark_export.py",
        unique_name="melix_probe_benchmark_export",
    )
    run_directory_count = 240
    result_files_per_run = 3
    sample_count = 5
    elapsed_samples: list[float] = []
    csv_elapsed_samples: list[float] = []
    result_file_count = 0.0
    csv_bytes = 0.0
    with tempfile.TemporaryDirectory(prefix="melix-pr-perf-benchmark-export-") as temp_dir:
        temp_root = Path(temp_dir)
        bench_root = temp_root / "bench"
        runs_root = bench_root / "runs"
        for run_index in range(run_directory_count):
            run_root = runs_root / f"bench-{run_index:04d}"
            run_root.mkdir(parents=True, exist_ok=True)
            summary_payload = {
                "schema_version": "melix.serving_benchmark_job.v1",
                "job_id": f"bench-{run_index:04d}",
                "model_id": "melix-dev-text",
                "task_kind": "text-generation",
                "source_repo": "synthetic",
                "suites": ["smoke"],
                "context_lengths": [32],
                "generation_length": 8,
                "batch_sizes": [1],
                "repeats": 1,
                "cache_profile": "cold",
                "reasoning_mode": "",
                "structured_output_mode": "",
                "request_p50_ms": 24.45,
                "request_p95_ms": 24.45,
                "parameters": {},
                "status": "completed",
                "output_dir": str(run_root),
                "created_at_unix_ms": 101,
                "updated_at_unix_ms": 202,
            }
            (run_root / "bench-summary.json").write_text(json.dumps(summary_payload) + "\n", encoding="utf-8")
            (run_root / "bench-context-rows.jsonl").write_text(
                json.dumps({"job_id": summary_payload["job_id"], "row_kind": "context"}) + "\n",
                encoding="utf-8",
            )
            (run_root / "bench-batch-rows.jsonl").write_text(
                json.dumps({"job_id": summary_payload["job_id"], "row_kind": "batch"}) + "\n",
                encoding="utf-8",
            )
            for result_index, suite in enumerate(("gamma", "alpha", "omega")):
                (run_root / f"bench-result-{suite}.json").write_text(
                    json.dumps({
                        "job_id": summary_payload["job_id"],
                        "suite": suite,
                        "metric_index": result_index,
                    }) + "\n",
                    encoding="utf-8",
                )
        result_file_count = float(run_directory_count * result_files_per_run)
        for _ in range(sample_count):
            gc.collect()
            started = time.perf_counter()
            artifacts = module.collect_benchmark_artifacts(temp_root)
            elapsed_samples.append((time.perf_counter() - started) * 1000.0)
            if len(artifacts.get("benchmark_jobs", [])) != run_directory_count:
                raise ValueError("benchmark export probe produced an unexpected benchmark job count")
            if len(artifacts.get("benchmark_results", [])) != int(result_file_count):
                raise ValueError("benchmark export probe produced an unexpected benchmark result count")
            csv_started = time.perf_counter()
            summary_csv = module.build_benchmark_summary_csv(artifacts)
            csv_elapsed_samples.append((time.perf_counter() - csv_started) * 1000.0)
            csv_bytes = float(len(summary_csv.encode("utf-8")))
            if len(summary_csv.splitlines()) != run_directory_count + 1:
                raise ValueError("benchmark export probe produced an unexpected summary CSV line count")
    elapsed_ms_mean = sum(elapsed_samples) / len(elapsed_samples)
    csv_elapsed_ms_mean = sum(csv_elapsed_samples) / len(csv_elapsed_samples)
    return {
        "csv_bytes": csv_bytes,
        "csv_elapsed_ms_mean": round(csv_elapsed_ms_mean, 6),
        "elapsed_ms_mean": round(elapsed_ms_mean, 6),
        "per_run_ms_mean": round(elapsed_ms_mean / float(run_directory_count), 6),
        "result_file_count": result_file_count,
        "run_directory_count": float(run_directory_count),
        "sample_count": float(sample_count),
    }


def _probe_benchmark_queue_cache(repo_root: Path) -> dict[str, float]:
    module = _load_repo_module(
        repo_root / "services/mlx-worker-python/worker/productization/benchmark_queue.py",
        unique_name="melix_probe_benchmark_queue",
    )
    record_count = 128
    warm_sample_count = 5
    with tempfile.TemporaryDirectory(prefix="melix-pr-perf-benchmark-queue-") as temp_dir:
        queue_root = Path(temp_dir) / "queue"
        queue_root.mkdir(parents=True, exist_ok=True)
        for index in range(record_count):
            record = module.BenchmarkQueueRecord(
                queue_item_id=f"queue-{index:04d}",
                job_kind="benchmark",
                model_id="melix-dev-text",
                suite_ids=("smoke", "latency"),
                parameters={"sample_size": str(16 + (index % 4))},
                status="queued",
                created_at_unix_ms=1_000 + index,
                updated_at_unix_ms=1_000 + index,
            )
            (queue_root / f"queue-{index:04d}.json").write_text(
                json.dumps(record.to_dict(), indent=2) + "\n",
                encoding="utf-8",
            )
        store = module.BenchmarkQueueStore()
        tracked_loads = 0
        original_loads = module.json.loads

        def counting_loads(raw: str | bytes, *args: object, **kwargs: object) -> object:
            nonlocal tracked_loads
            tracked_loads += 1
            return original_loads(raw, *args, **kwargs)

        module.json.loads = counting_loads
        try:
            cold_started = time.perf_counter()
            cold_records = store.list_records(queue_root=queue_root)
            cold_elapsed_ms = (time.perf_counter() - cold_started) * 1000.0
            if len(cold_records) != record_count:
                raise ValueError("benchmark queue probe produced an unexpected benchmark queue record count")
            cold_json_loads = tracked_loads
            warm_elapsed_samples: list[float] = []
            warm_json_load_samples: list[float] = []
            for _ in range(warm_sample_count):
                before_loads = tracked_loads
                started = time.perf_counter()
                warm_records = store.list_records(queue_root=queue_root)
                warm_elapsed_samples.append((time.perf_counter() - started) * 1000.0)
                if len(warm_records) != record_count:
                    raise ValueError("benchmark queue probe produced an unexpected benchmark queue record count")
                warm_json_load_samples.append(float(tracked_loads - before_loads))
        finally:
            module.json.loads = original_loads
    return {
        "cold_elapsed_ms": round(cold_elapsed_ms, 6),
        "cold_json_loads": float(cold_json_loads),
        "record_count": float(record_count),
        "warm_elapsed_ms_mean": round(sum(warm_elapsed_samples) / len(warm_elapsed_samples), 6),
        "warm_json_loads_mean": round(sum(warm_json_load_samples) / len(warm_json_load_samples), 6),
        "warm_sample_count": float(warm_sample_count),
    }


def _probe_closure_audit(repo_root: Path) -> dict[str, float]:
    module = _load_repo_module(
        repo_root / "services/mlx-worker-python/worker/productization/closure_audit.py",
        unique_name="melix_probe_closure_audit",
    )
    with tempfile.TemporaryDirectory(prefix="melix-pr-perf-closure-audit-") as temp_dir:
        seeded_root = _seed_closure_audit_repo(Path(temp_dir))
        elapsed_samples: list[float] = []
        read_samples: list[float] = []
        finding_count = 0.0
        for _ in range(3):
            gc.collect()
            read_count = 0
            original_read_text = Path.read_text

            def tracked_read_text(path: Path, *args: object, **kwargs: object) -> str:
                nonlocal read_count
                if path.suffix in _TEXT_FILE_SUFFIXES and _is_relative_to(path, seeded_root):
                    read_count += 1
                return original_read_text(path, *args, **kwargs)

            Path.read_text = tracked_read_text  # type: ignore[method-assign]
            try:
                started = time.perf_counter()
                report = module.build_closure_audit(seeded_root, created_at_unix_ms=7)
                elapsed_samples.append((time.perf_counter() - started) * 1000.0)
            finally:
                Path.read_text = original_read_text  # type: ignore[method-assign]
            read_samples.append(float(read_count))
            finding_count = float(len(report.findings))
    return {
        "elapsed_ms_mean": round(sum(elapsed_samples) / len(elapsed_samples), 3),
        "probe_file_reads_mean": round(sum(read_samples) / len(read_samples), 3),
        "finding_count": finding_count,
    }


def _probe_deterministic_rerank_query_context_reuse(repo_root: Path) -> dict[str, float]:
    del repo_root
    from worker.runtime.deterministic_rerank_runtime import DeterministicRerankRuntime
    from worker.runtime.rerank_backends import DeterministicRerankBackend, JinaV3RerankFamilyAdapter

    document_count = 2048
    iteration_count = 8
    sample_count = 5
    query = "swift control plane runtime"
    documents = [
        f"swift runtime document {index} control plane" if index % 2 == 0 else f"python worker document {index} packaging"
        for index in range(document_count)
    ]

    class CountingBackend(DeterministicRerankBackend):
        def __init__(self) -> None:
            self.tokenize_calls = 0

        def tokenize(self, text: str) -> list[str]:
            self.tokenize_calls += 1
            return super().tokenize(text)

    class TrackingFamily(JinaV3RerankFamilyAdapter):
        def __init__(self) -> None:
            self.query_context_builds = 0

        def build_query_context(self, backend: DeterministicRerankBackend, query: str, **kwargs: object):
            self.query_context_builds += 1
            return super().build_query_context(backend, query, **kwargs)

    elapsed_samples: list[float] = []
    query_context_build_samples: list[float] = []
    tokenize_call_samples: list[float] = []

    runtime = DeterministicRerankRuntime()
    for _ in range(sample_count):
        backend = CountingBackend()
        family = TrackingFamily()
        started = time.perf_counter()
        for _ in range(iteration_count):
            scores = runtime.score_documents(
                {
                    "rerank_backend": backend,
                    "rerank_family_adapter": family,
                },
                query,
                documents,
            )
            if len(scores) != document_count:
                raise ValueError(f"expected {document_count} scores, got {len(scores)}")
        elapsed_samples.append((time.perf_counter() - started) * 1000.0)
        query_context_build_samples.append(float(family.query_context_builds) / float(iteration_count))
        tokenize_call_samples.append(float(backend.tokenize_calls) / float(iteration_count))

    return {
        "document_count": float(document_count),
        "elapsed_ms_mean": round(sum(elapsed_samples) / len(elapsed_samples), 6),
        "iteration_count": float(iteration_count),
        "query_context_builds_mean": round(
            sum(query_context_build_samples) / len(query_context_build_samples),
            6,
        ),
        "sample_count": float(sample_count),
        "tokenize_calls_mean": round(sum(tokenize_call_samples) / len(tokenize_call_samples), 6),
    }


def _probe_evaluation_store_compare_summary_csv_streaming(repo_root: Path) -> dict[str, float]:
    summary_count = 10000
    probe_script = f"""
import gc
import json
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path

repo_root = Path({str(repo_root)!r})
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / 'services/mlx-worker-python'))
from worker.productization.evaluation_schemas import (
    build_evaluation_compare_job_record,
    build_evaluation_compare_summary_record,
)
from worker.productization.evaluation_store import EvaluationStore

summary_count = {summary_count}
summaries = tuple(
    build_evaluation_compare_summary_record(
        job_id='eval-compare-perf',
        base_model_id='melix-dev-text',
        target_model_id=f'melix-dev-text-target-{{index:05d}}',
        suite_id='mmlu',
        dataset_id='mmlu.synthetic',
        sample_size=64,
        scoring_mode='multiple_choice_accuracy',
        win_count=index % 7,
        loss_count=(index + 1) % 5,
        tie_count=(index + 2) % 3,
        regression_count=index % 2,
        base_accuracy=0.5,
        target_accuracy=0.5 + ((index % 9) * 0.01),
        delta_accuracy=((index % 9) * 0.01),
        effect_threshold=0.02,
        verdict='improvement' if index % 2 == 0 else 'watch',
        category_breakdown={{}},
        statistical_evidence={{
            'bootstrap': {{
                'lower_bound': -0.01 + ((index % 7) * 0.001),
                'upper_bound': 0.03 + ((index % 7) * 0.001),
            }},
            'analytical': {{
                'lower_bound': -0.02 + ((index % 5) * 0.001),
                'upper_bound': 0.04 + ((index % 5) * 0.001),
            }},
        }},
        release_gate_summary={{}},
        duration_seconds=0.1 + ((index % 11) * 0.01),
        metrics={{'eval.compare.delta_accuracy': ((index % 9) * 0.01)}},
        report_path='',
    )
    for index in range(summary_count)
)
job = build_evaluation_compare_job_record(
    job_id='eval-compare-perf',
    base_model_id='melix-dev-text',
    target_model_ids=tuple(summary.target_model_id for summary in summaries),
    task_kind='text-generation',
    source_repo='synthetic',
    suite_id='mmlu',
    dataset_id='mmlu.synthetic',
    sample_size=64,
    scoring_mode='multiple_choice_accuracy',
    parameters={{'compare_mode': 'base_vs_targets'}},
    status='completed',
    output_dir='',
    created_at_unix_ms=101,
    updated_at_unix_ms=202,
)
store = EvaluationStore()
writer = getattr(store, '_write_compare_summary_csv', None)
elapsed_samples = []
peak_samples = []
csv_line_count = 0
csv_bytes = 0
for _ in range(3):
    with tempfile.TemporaryDirectory(prefix='melix-pr-perf-eval-compare-store-') as temp_dir:
        summary_csv_path = Path(temp_dir) / 'evaluation-compare-summary.csv'
        gc.collect()
        tracemalloc.start()
        started = time.perf_counter()
        if writer is not None:
            writer(summary_csv_path, job=job, summaries=summaries)
        else:
            summary_csv_path.write_text(
                store._compare_summary_csv(job=job, summaries=summaries),
                encoding='utf-8',
            )
        elapsed_samples.append((time.perf_counter() - started) * 1000.0)
        _, peak_bytes = tracemalloc.get_traced_memory()
        peak_samples.append(float(peak_bytes))
        tracemalloc.stop()
        csv_line_count = float(len(summary_csv_path.read_text(encoding='utf-8').splitlines()))
        if csv_line_count != float(summary_count + 1):
            raise ValueError(f'unexpected compare summary CSV line count: {{csv_line_count}}')
        csv_bytes = float(summary_csv_path.stat().st_size)
print(json.dumps({{
    'elapsed_ms_mean': round(sum(elapsed_samples) / len(elapsed_samples), 6),
    'peak_bytes_mean': round(sum(peak_samples) / len(peak_samples), 1),
    'summary_count': float(summary_count),
    'csv_line_count': float(csv_line_count),
    'csv_bytes': float(csv_bytes),
}}, sort_keys=True))
"""
    completed = subprocess.run(
        [
            "uv",
            "run",
            "--project",
            str(repo_root / "services/mlx-worker-python"),
            "python3",
            "-c",
            probe_script,
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads((completed.stdout or "").strip())



def _probe_evaluation_store_samples_csv_streaming(repo_root: Path) -> dict[str, float]:
    sample_count = 10000
    probe_script = f"""
import gc
import json
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path

repo_root = Path({str(repo_root)!r})
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / 'services/mlx-worker-python'))
from worker.productization.evaluation_schemas import (
    build_evaluation_job_record,
    build_evaluation_result_record,
    build_evaluation_sample_record,
)
from worker.productization.evaluation_store import EvaluationStore

sample_count = {sample_count}
samples = tuple(
    build_evaluation_sample_record(
        job_id='eval-perf',
        suite_id='mmlu',
        dataset_id='mmlu.synthetic',
        sample_id=f'sample-{{index:05d}}',
        system='',
        input_text=f'Question {{index}}?',
        target=str(index % 5),
        raw_response=f'Answer {{index % 5}}',
        extracted_result=str(index % 5),
        typed_score=1.0 if index % 2 == 0 else 0.0,
        time_s=0.01,
        extraction_status='extracted',
        validation_status='validated',
        failure_reason='',
        task_kind='text-generation',
        input_modalities=('text',),
        media_references=(),
        raw_response_chars=0 if index % 19 == 0 else len(f'Answer {{index % 5}}'),
        extracted_result_chars=0 if index % 23 == 0 else len(str(index % 5)),
    )
    for index in range(sample_count)
)
job = build_evaluation_job_record(
    job_id='eval-perf',
    model_id='melix-dev-text',
    task_kind='text-generation',
    source_repo='synthetic',
    suite_id='mmlu',
    dataset_id='mmlu.synthetic',
    sample_size=sample_count,
    scoring_mode='deterministic_accuracy',
    few_shot=0,
    seed=7,
    code_exec_policy='sandboxed',
    parameters={{}},
    status='completed',
    output_dir='',
    created_at_unix_ms=101,
    updated_at_unix_ms=202,
)
result = build_evaluation_result_record(
    job_id='eval-perf',
    suite_id='mmlu',
    dataset_id='mmlu.synthetic',
    sample_size=sample_count,
    primary_score_name='normalized_exact_match',
    primary_score_value=0.5,
    extraction_success_count=sample_count,
    validation_success_count=sample_count,
    scored_sample_count=sample_count,
    failure_count=0,
    duration_seconds=0.25,
    metrics={{'eval.mmlu.accuracy': 0.5}},
    report_path='',
    units={{'eval.mmlu.accuracy': 'ratio'}},
)
store = EvaluationStore()
elapsed_samples = []
peak_samples = []
csv_line_count = 0
for _ in range(3):
    with tempfile.TemporaryDirectory(prefix='melix-pr-perf-eval-store-') as temp_dir:
        jobs_root = Path(temp_dir) / 'evaluation'
        gc.collect()
        tracemalloc.start()
        started = time.perf_counter()
        persisted = store.persist_result(
            jobs_root=jobs_root,
            job=job,
            result=result,
            samples=samples,
        )
        elapsed_samples.append((time.perf_counter() - started) * 1000.0)
        _, peak_bytes = tracemalloc.get_traced_memory()
        peak_samples.append(float(peak_bytes))
        tracemalloc.stop()
        csv_line_count = float(len(persisted['samples_csv'].read_text(encoding='utf-8').splitlines()))
        if csv_line_count != float(sample_count + 1):
            raise ValueError(f'unexpected evaluation samples CSV line count: {{csv_line_count}}')
print(json.dumps({{
    'elapsed_ms_mean': round(sum(elapsed_samples) / len(elapsed_samples), 6),
    'peak_bytes_mean': round(sum(peak_samples) / len(peak_samples), 1),
    'sample_count': float(sample_count),
    'csv_line_count': float(csv_line_count),
}}, sort_keys=True))
"""
    completed = subprocess.run(
        [
            "uv",
            "run",
            "--project",
            str(repo_root / "services/mlx-worker-python"),
            "python3",
            "-c",
            probe_script,
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads((completed.stdout or "").strip())


def _probe_evaluation_sample_probe_aggregation(repo_root: Path) -> dict[str, float]:
    sample_count = 20000
    field_names = (
        "sample_render_ms",
        "inference_ms",
        "extraction_ms",
        "validation_ms",
        "scoring_ms",
        "raw_response_chars",
        "extracted_result_chars",
    )
    probe_script = f"""
import json
import sys
import time
from pathlib import Path

repo_root = Path({str(repo_root)!r})
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / 'services/mlx-worker-python'))
from worker.engine.evaluation_core import EvaluationCore
from worker.productization.evaluation_schemas import build_evaluation_sample_record

field_names = {field_names!r}
sample_count = {sample_count}
samples = tuple(
    build_evaluation_sample_record(
        job_id='eval-probe',
        suite_id='mmlu',
        dataset_id='mmlu-dev',
        sample_id=str(index),
        system='',
        input_text=f'prompt {{index}}',
        target='answer',
        raw_response=f'Answer: {{index % 10}}',
        extracted_result=str(index % 10),
        typed_score=1.0 if index % 2 == 0 else 0.0,
        time_s=0.1,
        extraction_status='extracted',
        validation_status='validated',
        failure_reason='',
        sample_render_ms=(index % 11) * 0.1,
        inference_ms=(index % 13) * 0.2,
        extraction_ms=(index % 7) * 0.3,
        validation_ms=(index % 5) * 0.4,
        scoring_ms=(index % 3) * 0.5,
        raw_response_chars=0 if index % 17 == 0 else len(f'Answer: {{index % 10}}'),
        extracted_result_chars=0 if index % 19 == 0 else len(str(index % 10)),
    )
    for index in range(sample_count)
)
elapsed_samples = []
metrics = {{}}
for _ in range(3):
    started = time.perf_counter()
    metrics = EvaluationCore._sample_probe_means(samples, field_names)
    elapsed_samples.append((time.perf_counter() - started) * 1000.0)

elapsed_ms_mean = sum(elapsed_samples) / len(elapsed_samples)
print(json.dumps({{
    'elapsed_ms_mean': round(elapsed_ms_mean, 3),
    'per_call_ms_mean': round(elapsed_ms_mean / max(sample_count, 1), 6),
    'sample_count': float(sample_count),
    'metric_count': float(len(metrics)),
}}, sort_keys=True))
"""
    completed = subprocess.run(
        [
            "uv",
            "run",
            "--project",
            str(repo_root / "services/mlx-worker-python"),
            "python3",
            "-c",
            probe_script,
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads((completed.stdout or "").strip())


def _probe_evaluation_job_id(repo_root: Path) -> dict[str, float]:
    seeded_run_count = 2000
    per_sample_allocations = 200
    probe_script = f"""
import json
import sys
import tempfile
import time
from pathlib import Path

repo_root = Path({str(repo_root)!r})
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / 'services/mlx-worker-python'))
from worker.engine.evaluation_core import EvaluationCore

elapsed_samples = []
allocation_count = 0
first_job_id = ''
last_job_id = ''
seeded_run_count = {seeded_run_count}
per_sample_allocations = {per_sample_allocations}
for _ in range(3):
    with tempfile.TemporaryDirectory(prefix='melix-pr-perf-eval-job-id-') as temp_dir:
        jobs_root = Path(temp_dir) / 'jobs'
        runs_root = jobs_root / 'runs'
        runs_root.mkdir(parents=True, exist_ok=True)
        for index in range(1, seeded_run_count + 1):
            (runs_root / f'eval-{{index:04d}}').mkdir()
        runner = EvaluationCore(jobs_root=jobs_root)
        started = time.perf_counter()
        allocated_job_ids = [runner._next_job_id() for _ in range(per_sample_allocations)]
        elapsed_samples.append((time.perf_counter() - started) * 1000.0)
        allocation_count = len(allocated_job_ids)
        first_job_id = allocated_job_ids[0]
        last_job_id = allocated_job_ids[-1]

elapsed_ms_mean = sum(elapsed_samples) / len(elapsed_samples)
print(json.dumps({{
    'elapsed_ms_mean': round(elapsed_ms_mean, 3),
    'per_call_ms_mean': round(elapsed_ms_mean / max(allocation_count, 1), 6),
    'allocation_count': float(allocation_count),
    'seeded_run_count': float(seeded_run_count),
    'first_job_id_numeric': float(first_job_id.removeprefix('eval-') or 0),
    'last_job_id_numeric': float(last_job_id.removeprefix('eval-') or 0),
}}, sort_keys=True))
"""
    completed = subprocess.run(
        [
            "uv",
            "run",
            "--project",
            str(repo_root / "services/mlx-worker-python"),
            "python3",
            "-c",
            probe_script,
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads((completed.stdout or "").strip())


def _probe_training_dataset_token_percentiles(repo_root: Path) -> dict[str, float]:
    module = _load_repo_module(
        repo_root / "services/mlx-worker-python/worker/model_ops/training_dataset.py",
        unique_name="melix_probe_training_dataset_token_percentiles",
    )
    samples = _build_large_training_dataset_quality_samples()
    elapsed_samples: list[float] = []
    peak_samples: list[float] = []
    sample_count = 0.0
    duplicate_count = 0.0
    dirty_count = 0.0
    for _ in range(3):
        gc.collect()
        tracemalloc.start()
        try:
            started = time.perf_counter()
            quality, token_stats = module._build_quality_and_token_stats(samples, "prompt_completion")
            elapsed_samples.append((time.perf_counter() - started) * 1000.0)
            _, peak_bytes = tracemalloc.get_traced_memory()
            peak_samples.append(float(peak_bytes))
            sample_count = float(token_stats["sample_count"])
            duplicate_count = float(quality["duplicate_count"])
            dirty_count = float(quality["dirty_count"])
        finally:
            tracemalloc.stop()
    return {
        "elapsed_ms_mean": round(sum(elapsed_samples) / len(elapsed_samples), 3),
        "peak_bytes_mean": round(sum(peak_samples) / len(peak_samples), 3),
        "sample_count": sample_count,
        "duplicate_count": duplicate_count,
        "dirty_count": dirty_count,
    }


def _probe_upload_receipt_published_files(repo_root: Path) -> dict[str, float]:
    module = _load_upload_receipt_pipeline_module(
        repo_root / "services/mlx-worker-python/worker/model_ops/upload_receipt_pipeline.py",
    )
    directory_count = 180
    files_per_directory = 40
    sample_count = 5
    elapsed_samples: list[float] = []
    published_file_count = 0.0
    with tempfile.TemporaryDirectory(prefix="melix-pr-perf-upload-receipt-") as temp_dir:
        source_root = Path(temp_dir) / "publish-bundle"
        expected_file_count = 0
        for directory_index in range(directory_count):
            directory = source_root / f"shard-{directory_index:04d}"
            directory.mkdir(parents=True, exist_ok=True)
            for file_index in range(files_per_directory):
                (directory / f"part-{file_index:04d}.safetensors").write_bytes(b"melix")
                expected_file_count += 1
        (source_root / "README.md").write_text("# Melix synthetic publish bundle\n", encoding="utf-8")
        expected_file_count += 1
        for _ in range(sample_count):
            started = time.perf_counter()
            published_files = module.UploadReceiptPipeline._collect_published_file_list(source_root)
            elapsed_samples.append((time.perf_counter() - started) * 1000.0)
            published_file_count = float(len(published_files))
            if len(published_files) != expected_file_count:
                raise ValueError(
                    f"expected {expected_file_count} published files, got {len(published_files)}"
                )
    return {
        "directory_count": float(directory_count),
        "elapsed_ms_mean": round(sum(elapsed_samples) / len(elapsed_samples), 6),
        "elapsed_ms_min": round(min(elapsed_samples), 6),
        "files_per_directory": float(files_per_directory),
        "published_file_count": published_file_count,
        "sample_count": float(sample_count),
    }


def _probe_pr_scoped_scope_matcher(repo_root: Path) -> dict[str, float]:
    registry_path = repo_root / "infra/perf/pr_scoped_probes.json"
    changed_files = _build_large_scope_probe_changed_files()
    sample_count = 6
    elapsed_samples: list[float] = []
    selected_probe_counts: list[float] = []
    force_all_selected_samples: list[float] = []
    for _ in range(sample_count):
        started = time.perf_counter()
        scope = build_scope_report(registry_path=registry_path, changed_files=changed_files)
        elapsed_samples.append((time.perf_counter() - started) * 1000.0)
        selected_probe_counts.append(float(scope["selected_count"]))
        force_all_selected_samples.append(1.0 if scope["force_all"] else 0.0)
    return {
        "build_scope_report_ms_mean": round(sum(elapsed_samples) / len(elapsed_samples), 6),
        "build_scope_report_ms_min": round(min(elapsed_samples), 6),
        "changed_file_count": float(len(changed_files)),
        "selected_probe_count_mean": round(sum(selected_probe_counts) / len(selected_probe_counts), 6),
        "force_all_selected_mean": round(sum(force_all_selected_samples) / len(force_all_selected_samples), 6),
        "sample_count": float(sample_count),
    }


def _build_large_scope_probe_changed_files() -> list[str]:
    changed_files: list[str] = []
    for index in range(1600):
        changed_files.append(f"docs/perf/synthetic/doc-{index:04d}.md")
    for index in range(1600):
        changed_files.append(f"services/mlx-worker-python/tests/synthetic/test_scope_{index:04d}.py")
    changed_files.extend(
        [
            "services/mlx-worker-python/worker/productization/benchmark_export.py",
            "services/mlx-worker-python/worker/engine/evaluation_core.py",
            "services/mlx-worker-python/worker/model_ops/download_pipeline.py",
            "README.md",
            "",
        ]
    )
    return changed_files


def _load_upload_receipt_pipeline_module(path: Path) -> Any:
    module_names = (
        "packages",
        "packages.protocol",
        "packages.protocol.python",
        "packages.protocol.python.worker",
        "packages.protocol.python.worker.v1",
        "packages.protocol.python.worker.v1.maintenance_pb2",
        "worker",
        "worker.model_ops",
        "worker.model_ops.errors",
    )
    missing = object()
    previous_modules = {name: sys.modules.get(name, missing) for name in module_names}

    packages_module = types.ModuleType("packages")
    protocol_module = types.ModuleType("packages.protocol")
    python_module = types.ModuleType("packages.protocol.python")
    worker_protocol_module = types.ModuleType("packages.protocol.python.worker")
    worker_v1_module = types.ModuleType("packages.protocol.python.worker.v1")
    maintenance_module = types.ModuleType("packages.protocol.python.worker.v1.maintenance_pb2")
    worker_module = types.ModuleType("worker")
    model_ops_module = types.ModuleType("worker.model_ops")
    errors_module = types.ModuleType("worker.model_ops.errors")

    class ModelOperationError(Exception):
        pass

    errors_module.ModelOperationError = ModelOperationError
    worker_v1_module.maintenance_pb2 = maintenance_module
    worker_protocol_module.v1 = worker_v1_module
    python_module.worker = worker_protocol_module
    protocol_module.python = python_module
    packages_module.protocol = protocol_module
    model_ops_module.errors = errors_module
    worker_module.model_ops = model_ops_module

    sys.modules.update(
        {
            "packages": packages_module,
            "packages.protocol": protocol_module,
            "packages.protocol.python": python_module,
            "packages.protocol.python.worker": worker_protocol_module,
            "packages.protocol.python.worker.v1": worker_v1_module,
            "packages.protocol.python.worker.v1.maintenance_pb2": maintenance_module,
            "worker": worker_module,
            "worker.model_ops": model_ops_module,
            "worker.model_ops.errors": errors_module,
        }
    )
    try:
        return _load_repo_module(
            path,
            unique_name="melix_probe_upload_receipt_pipeline",
        )
    finally:
        for name, previous in previous_modules.items():
            if previous is missing:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous


def _probe_model_ops_bundle_artifact_bytes(repo_root: Path) -> dict[str, float]:
    probe_script = """
import json
import os
import tempfile
import time
from pathlib import Path

from packages.protocol.python.worker.v1 import maintenance_pb2
from worker.grpc_server import WorkerMaintenanceService
from worker.model_registry.catalog import WorkerModelCatalog
from worker.registry import WorkerRegistry

elapsed_samples = []
scandir_samples = []
sample_count = 0.0

for _ in range(3):
    with tempfile.TemporaryDirectory(prefix='melix-pr-perf-model-ops-bundle-') as temp_dir:
        temp_root = Path(temp_dir)
        service = WorkerMaintenanceService(
            WorkerRegistry(model_catalog=WorkerModelCatalog()),
            jobs_root=temp_root / 'model-ops',
        )
        original_scandir = os.scandir
        bundle_scandir_calls = [0]

        def tracked_scandir(path):
            bundle_scandir_calls[0] += int(Path(path).name.endswith('.artifact'))
            return original_scandir(path)

        os.scandir = tracked_scandir
        try:
            started = time.perf_counter()
            convert_events = list(
                service.ConvertModel(
                    maintenance_pb2.ConvertModelRequest(
                        source_model='melix-dev-text',
                        output_dir=str(temp_root / 'convert'),
                        generate_manifest=True,
                    ),
                    context=None,
                )
            )
            quantize_events = list(
                service.ConvertModel(
                    maintenance_pb2.ConvertModelRequest(
                        source_model='melix-dev-text',
                        output_dir=str(temp_root / 'quantize'),
                        weight_quant='q4',
                        kv_quant='q8',
                        generate_manifest=True,
                        ext={'operation': 'quantize'},
                    ),
                    context=None,
                )
            )
            elapsed_samples.append((time.perf_counter() - started) * 1000.0)
        finally:
            os.scandir = original_scandir

        sample_count = float(len(convert_events) + len(quantize_events))
        scandir_samples.append(float(bundle_scandir_calls[0]))

print(json.dumps({
    'elapsed_ms_mean': round(sum(elapsed_samples) / len(elapsed_samples), 3),
    'bundle_scandir_calls_mean': round(sum(scandir_samples) / len(scandir_samples), 3),
    'sample_count': sample_count,
}, sort_keys=True))
"""
    completed = subprocess.run(
        "PYTHONPATH=\"$PWD:$PWD/services/mlx-worker-python\" uv run --project services/mlx-worker-python python3 - <<'PY'\n"
        f"{probe_script}"
        "\nPY",
        shell=True,
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads((completed.stdout or "").strip())


def _load_repo_module(path: Path, *, unique_name: str) -> Any:
    spec = importlib.util.spec_from_file_location(unique_name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"could not load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[unique_name] = module
    try:
        spec.loader.exec_module(module)
    except FileNotFoundError as exc:
        raise ValueError(f"could not load module from {path}") from exc
    return module


def _build_large_benchmark_bundle(*, base_value: float) -> dict[str, object]:
    benchmark_results = [
        {
            "job_id": f"bench-{index}",
            "suite": "smoke",
            "metrics": [
                {"name": f"bench.smoke.metric_{index}.ttft_ms", "value": base_value + index},
                {
                    "name": f"bench.smoke.metric_{index}.tokens_per_second",
                    "value": (base_value * 2.0) + index,
                },
            ],
        }
        for index in range(250)
    ]
    benchmark_context_rows = [
        {
            "suite": "smoke",
            "context_length": 1024 + index,
            "generation_length": 64,
            "batch_size": 1,
            "prefill_ms": base_value + (index % 7),
            "decode_ms": (base_value / 2.0) + (index % 5),
            "cache_hit": index % 3 == 0,
        }
        for index in range(900)
    ]
    benchmark_matrix_summary_rows = [
        {
            "suite_id": "smoke",
            "context_length": 1024 + index,
            "generation_length": 64,
            "batch_size": 1,
            "concurrency_level": 1,
            "request_latency_mean_ms": base_value + index,
            "request_latency_p95_ms": base_value + index + 3,
            "ttft_mean_ms": base_value + index / 4.0,
            "ttft_p95_ms": base_value + index / 3.0,
            "throughput_tokens_per_second": 200.0 + index,
            "success_rate": 1.0,
            "failed_count": 0,
        }
        for index in range(180)
    ]
    benchmark_matrix_request_rows = [
        {
            "suite_id": "smoke",
            "context_length": 1024 + (index % 180),
            "generation_length": 64,
            "batch_size": 1,
            "concurrency_level": 1,
            "prefill_ms": base_value + (index % 9),
            "decode_ms": base_value + (index % 11),
            "speculative_acceptance_rate": 0.7,
            "speculative_rejected_tokens": index % 4,
            "speculative_fallback_count": index % 2,
            "dflash_enabled": True,
            "dflash_rollback_count": index % 3,
        }
        for index in range(1200)
    ]
    evaluation_summary_rows = [
        {
            "suite_id": f"eval-{index}",
            "dataset_id": "mmlu.dev.v1",
            "primary_score_name": "typed_score_mean",
            "primary_score_value": 0.7 + ((index % 5) / 100.0),
            "sample_size": 8,
            "failure_count": 0,
            "duration_seconds": 5.0,
        }
        for index in range(90)
    ]
    evaluation_sample_rows = [
        {
            "suite_id": f"eval-{index % 90}",
            "dataset_id": "mmlu.dev.v1",
            "sample_render_ms": base_value + (index % 6),
            "inference_ms": base_value + (index % 8),
            "extraction_ms": base_value / 3.0,
            "validation_ms": base_value / 4.0,
            "scoring_ms": base_value / 5.0,
            "raw_response_chars": 120 + index,
            "extracted_result_chars": 80 + index,
        }
        for index in range(600)
    ]
    return {
        "benchmark_results": benchmark_results,
        "benchmark_context_rows": benchmark_context_rows,
        "benchmark_matrix_summary_rows": benchmark_matrix_summary_rows,
        "benchmark_matrix_request_rows": benchmark_matrix_request_rows,
        "evaluation_summary_rows": evaluation_summary_rows,
        "evaluation_sample_rows": evaluation_sample_rows,
    }


def _build_large_training_dataset_samples() -> list[dict[str, str]]:
    return [
        {
            "prompt": " ".join(f"prompt{index}_{token}" for token in range(1 + (index % 9))),
            "completion": " ".join(f"completion{index}_{token}" for token in range(1 + ((index * 3) % 7))),
        }
        for index in range(20000)
    ]


def _single_pass_sample_iterable(samples: list[dict[str, str]]) -> Iterable[dict[str, str]]:
    class _SinglePassIterable:
        def __init__(self, rows: list[dict[str, str]]) -> None:
            self._rows = rows
            self._iterated = False

        def __iter__(self) -> Iterable[dict[str, str]]:
            if self._iterated:
                raise RuntimeError("training dataset sample iterable was consumed more than once")
            self._iterated = True
            return iter(self._rows)

    return _SinglePassIterable(samples)


def _build_large_training_dataset_quality_samples() -> list[dict[str, str]]:
    samples = _build_large_training_dataset_samples()
    for index in range(0, len(samples), 17):
        sample = dict(samples[index - 1] if index else samples[index])
        if index % 51 == 0:
            sample["completion"] = sample["prompt"]
        samples[index] = sample
    return samples


def _seed_closure_audit_repo(root: Path) -> Path:
    repo_root = root / "repo"
    _write(repo_root / "docs/plans/2026-03-30-full-capability-roadmap-execution-index.md", _closure_index_text())
    _write(
        repo_root / "docs/plans/2026-03-30-m9-7-security-and-stability-closure-audit.md",
        "# M9.7\n\n- repository-owned evidence only\n",
    )
    _write(
        repo_root / "infra/release/phase8-release-gate-policy.json",
        json.dumps(
            {
                "install": {},
                "benchmarks": {},
                "training": {},
                "recovery": {},
                "audio": {},
                "runtime_core": {},
                "evaluation": {},
                "quantization": {},
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    _write(repo_root / "scripts/phase8_metrics_report.py", "print('phase8 metrics report')\n")
    _write(repo_root / "docs/runbooks/phase-8-release-gates.md", "# Phase 8 Release Gates\n")
    probe_text = "\n".join(
        [
            "gateway.accepted_api_key_count",
            "shared_access.accepted_client_count",
            "shared_access.rejected_request_count",
            "persistent_session.restore_success_rate",
            "persistent_session.sign_out_latency_ms",
            "sanitized_output.enforcement_count",
            "sanitized_output.blocked_html_fragment_count",
            "sanitized_output.unsafe_uri_rejection_count",
            "disconnect.keepalive_gap_ms",
            "disconnect.recovery_latency_ms",
            "disconnect.resume_success_rate",
            "disconnect.terminal_failure_count",
        ]
    )
    _write(repo_root / "docs/runbooks/security-and-stability-closure.md", probe_text + "\n")
    _write(
        repo_root / "docs/runbooks/shared-access.md",
        "\n".join(
            [
                "gateway.accepted_api_key_count",
                "shared_access.accepted_client_count",
                "shared_access.rejected_request_count",
                "",
            ]
        ),
    )
    _write(
        repo_root / "docs/runbooks/persistent-sessions.md",
        "\n".join(
            [
                "persistent_session.restore_success_rate",
                "persistent_session.sign_out_latency_ms",
                "",
            ]
        ),
    )
    _write(
        repo_root / "docs/runbooks/rich-output-sanitization.md",
        "\n".join(
            [
                "sanitized_output.enforcement_count",
                "sanitized_output.blocked_html_fragment_count",
                "sanitized_output.unsafe_uri_rejection_count",
                "",
            ]
        ),
    )
    _write(
        repo_root / "docs/runbooks/connection-lifecycle.md",
        "\n".join(
            [
                "disconnect.keepalive_gap_ms",
                "disconnect.recovery_latency_ms",
                "disconnect.resume_success_rate",
                "disconnect.terminal_failure_count",
                "",
            ]
        ),
    )
    _write(repo_root / "progress.md", probe_text + "\n")
    docs_root = repo_root / "docs"
    for index in range(250):
        _write(docs_root / f"a-noise-{index:03d}.md", f"noise file {index}\n")
    services_root = repo_root / "services"
    for index in range(150):
        _write(services_root / f"module-{index:03d}.py", f"# module {index}\n")
    return repo_root


def _closure_index_text() -> str:
    return "\n".join(
        [
            "# Melix Full Capability Roadmap Execution Index",
            "",
            "- `M9.3` `docs/plans/m9.3-placeholder.md`",
            "  Status: completed. placeholder.",
            "- `M9.4` `docs/plans/m9.4-placeholder.md`",
            "  Status: completed. placeholder.",
            "- `M9.5` `docs/plans/m9.5-placeholder.md`",
            "  Status: completed. placeholder.",
            "- `M9.6` `docs/plans/m9.6-placeholder.md`",
            "  Status: completed. placeholder.",
            "- `M9.7` `docs/plans/m9.7-placeholder.md`",
            "  Status: pending. placeholder.",
            "- `M9.8` `docs/plans/m9.8-placeholder.md`",
            "  Status: pending. placeholder.",
            "",
        ]
    )


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _build_probe_report_row(result: dict[str, object]) -> dict[str, object]:
    probe = result.get("probe", {}) if isinstance(result.get("probe"), dict) else {}
    metrics = []
    regression_count = 0
    for metric_definition in _dict_list(probe.get("metrics")):
        key = str(metric_definition.get("key", "")).strip()
        if not key:
            continue
        metric_row = _build_metric_row(
            key=key,
            unit=str(metric_definition.get("unit", "value")),
            direction=str(metric_definition.get("direction", "lower_is_better")),
            warn_pct=float(metric_definition.get("warn_pct", 5.0)),
            base_metrics=result.get("base_probe", {}).get("metrics", {}),
            head_metrics=result.get("head_probe", {}).get("metrics", {}),
        )
        metrics.append(metric_row)
        if metric_row["status"] == "regression":
            regression_count += 1
    test_ok = bool(result.get("head_verification", {}).get("test", {}).get("ok", False))
    coverage_ok = bool(result.get("head_verification", {}).get("coverage", {}).get("ok", False))
    base_ok = bool(result.get("base_probe", {}).get("ok", False))
    head_ok = bool(result.get("head_probe", {}).get("ok", False))
    coverage_pct = result.get("head_verification", {}).get("coverage", {}).get("coverage_pct")
    status = "ok"
    if not test_ok or not coverage_ok:
        status = "verification_failed"
    elif not base_ok or not head_ok:
        status = "probe_failed"
    elif regression_count:
        status = "regression"
    return {
        "probe_id": str(probe.get("id", "")),
        "name": str(probe.get("name", probe.get("id", "probe"))),
        "status": status,
        "metrics": metrics,
        "coverage_pct": coverage_pct,
        "test_ok": test_ok,
        "coverage_ok": coverage_ok,
        "base_ok": base_ok,
        "head_ok": head_ok,
        "details": _build_probe_details(result=result),
    }


def _build_metric_row(
    *,
    key: str,
    unit: str,
    direction: str,
    warn_pct: float,
    base_metrics: object,
    head_metrics: object,
) -> dict[str, object]:
    base_value = _float_or_none(base_metrics.get(key) if isinstance(base_metrics, dict) else None)
    head_value = _float_or_none(head_metrics.get(key) if isinstance(head_metrics, dict) else None)
    if base_value is None or head_value is None:
        return {
            "key": key,
            "unit": unit,
            "direction": direction,
            "warn_pct": warn_pct,
            "base": base_value,
            "head": head_value,
            "delta": None,
            "delta_pct": None,
            "status": "missing",
        }
    delta = head_value - base_value
    delta_pct = None if base_value == 0 else (delta / base_value) * 100.0
    status = "neutral"
    threshold = abs(base_value) * (warn_pct / 100.0)
    if direction == "lower_is_better":
        if head_value > base_value + threshold:
            status = "regression"
        elif head_value < base_value - threshold:
            status = "improvement"
    else:
        if head_value < base_value - threshold:
            status = "regression"
        elif head_value > base_value + threshold:
            status = "improvement"
    return {
        "key": key,
        "unit": unit,
        "direction": direction,
        "warn_pct": warn_pct,
        "base": base_value,
        "head": head_value,
        "delta": delta,
        "delta_pct": delta_pct,
        "status": status,
    }


def _build_probe_details(*, result: dict[str, object]) -> str:
    fragments: list[str] = []
    if not result.get("head_verification", {}).get("test", {}).get("ok", False):
        fragments.append("Targeted tests failed.")
    if not result.get("head_verification", {}).get("coverage", {}).get("ok", False):
        fragments.append("Coverage command failed.")
    if not result.get("base_probe", {}).get("ok", False):
        fragments.append(str(result.get("base_probe", {}).get("error", "Base probe failed.")))
    if not result.get("head_probe", {}).get("ok", False):
        fragments.append(str(result.get("head_probe", {}).get("error", "Head probe failed.")))
    return " ".join(fragment for fragment in fragments if fragment).strip()


def _render_probe_terminal_block(row: dict[str, object]) -> list[str]:
    lines = [
        f"Probe: {row['name']}",
        f"  Status: {row['status']}",
        f"  Targeted tests: {'pass' if row['test_ok'] else 'fail'}",
        f"  Coverage: {'pass' if row['coverage_ok'] else 'fail'}"
        + (f" ({row['coverage_pct']}%)" if row.get('coverage_pct') is not None else ""),
    ]
    if row.get("details"):
        lines.append(f"  Details: {row['details']}")
    metrics = _dict_list(row.get("metrics"))
    for metric in metrics:
        lines.append(
            "  - "
            + f"{metric['key']}: base={_format_value(metric.get('base'))} "
            + f"head={_format_value(metric.get('head'))} "
            + f"delta={_format_delta(metric)} status={metric['status']}"
        )
    return lines


def _render_probe_markdown_block(row: dict[str, object]) -> list[str]:
    lines = [
        f"## {row['name']}",
        "",
        f"- Status: `{row['status']}`",
        f"- Targeted tests: `{'pass' if row['test_ok'] else 'fail'}`",
        f"- Coverage: `{'pass' if row['coverage_ok'] else 'fail'}`"
        + (f" (`{row['coverage_pct']}%`)" if row.get('coverage_pct') is not None else ""),
    ]
    if row.get("details"):
        lines.append(f"- Details: {row['details']}")
    lines.extend(
        [
            "",
            "| Metric | Base | Head | Delta | Status |",
            "| --- | ---: | ---: | ---: | --- |",
        ]
    )
    for metric in _dict_list(row.get("metrics")):
        lines.append(
            "| "
            + " | ".join(
                [
                    _markdown_cell(metric.get("key")),
                    _markdown_cell(_format_value(metric.get("base"))),
                    _markdown_cell(_format_value(metric.get("head"))),
                    _markdown_cell(_format_delta(metric)),
                    _markdown_cell(metric.get("status")),
                ]
            )
            + " |"
        )
    return lines


def _parse_coverage_percent(output: str) -> float | None:
    match = _COVERAGE_PERCENT_RE.search(output)
    if match is None:
        return None
    return float(match.group(1))


def _format_value(value: object) -> str:
    if isinstance(value, float):
        return f"{value:.3f}"
    if isinstance(value, int):
        return str(value)
    if value is None:
        return "-"
    return str(value)


def _format_delta(metric: dict[str, object]) -> str:
    delta = _float_or_none(metric.get("delta"))
    delta_pct = _float_or_none(metric.get("delta_pct"))
    if delta is None:
        return "-"
    if delta_pct is None:
        return f"{delta:+.3f}"
    return f"{delta:+.3f} ({delta_pct:+.2f}%)"


def _markdown_cell(value: object) -> str:
    return str(value).replace("|", "\\|")


def _dict_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _float_or_none(value: object) -> float | None:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (float, int)):
        return float(value)
    return None


def _match_probe_indexes(*, changed_paths: set[str] | frozenset[str] | tuple[str, ...], probes: tuple[ProbeDefinition, ...]) -> set[int]:
    exact_path_to_probe_indexes, wildcard_glob_matchers = _probe_match_indexes(probes)
    matched_probe_indexes: set[int] = set()
    if not isinstance(changed_paths, (set, frozenset)):
        changed_paths = set(changed_paths)
    for path in exact_path_to_probe_indexes.keys() & changed_paths:
        matched_probe_indexes.update(exact_path_to_probe_indexes[path])
    if not wildcard_glob_matchers:
        return matched_probe_indexes
    for path in changed_paths:
        for prefix, pattern, probe_indexes in wildcard_glob_matchers:
            if prefix and not path.startswith(prefix):
                continue
            if pattern.match(path) is not None:
                matched_probe_indexes.update(probe_indexes)
    return matched_probe_indexes


@lru_cache(maxsize=None)
def _probe_match_indexes(
    probes: tuple[ProbeDefinition, ...],
) -> tuple[dict[str, tuple[int, ...]], tuple[tuple[str, re.Pattern[str], tuple[int, ...]], ...]]:
    exact_path_to_probe_indexes: dict[str, list[int]] = {}
    wildcard_glob_to_probe_indexes: dict[str, list[int]] = {}
    for probe_index, probe in enumerate(probes):
        for glob in probe.watch_globs:
            if _glob_has_magic(glob):
                wildcard_glob_to_probe_indexes.setdefault(glob, []).append(probe_index)
            else:
                exact_path_to_probe_indexes.setdefault(glob, []).append(probe_index)
    wildcard_glob_matchers = tuple(
        (_glob_literal_prefix(glob), _compiled_glob_pattern(glob), tuple(probe_indexes))
        for glob, probe_indexes in wildcard_glob_to_probe_indexes.items()
    )
    return (
        {path: tuple(probe_indexes) for path, probe_indexes in exact_path_to_probe_indexes.items()},
        wildcard_glob_matchers,
    )


@lru_cache(maxsize=None)
def _compiled_glob_pattern(glob: str) -> re.Pattern[str]:
    return re.compile(fnmatch.translate(glob))


@lru_cache(maxsize=None)
def _glob_literal_prefix(glob: str) -> str:
    first_special_index = len(glob)
    for token in "*?[":
        index = glob.find(token)
        if index != -1 and index < first_special_index:
            first_special_index = index
    if first_special_index == len(glob):
        return glob
    return glob[:first_special_index]


def _glob_matches_path(path: str, glob: str) -> bool:
    prefix = _glob_literal_prefix(glob)
    if prefix and not path.startswith(prefix):
        return False
    return _compiled_glob_pattern(glob).match(path) is not None


@lru_cache(maxsize=1)
def _force_all_wildcard_matchers() -> tuple[tuple[str, re.Pattern[str]], ...]:
    return tuple(
        (_glob_literal_prefix(glob), _compiled_glob_pattern(glob))
        for glob in _FORCE_ALL_WILDCARD_GLOBS
    )


def _path_matches_force_all(path: str) -> bool:
    return path in _FORCE_ALL_EXACT_PATHS or _matches_any_compiled_glob(
        path,
        _force_all_wildcard_matchers(),
    )


def _matches_any_glob(path: str, globs: tuple[str, ...]) -> bool:
    return any(_glob_matches_path(path, glob) for glob in globs)


def _matches_any_compiled_glob(path: str, matchers: tuple[tuple[str, re.Pattern[str]], ...]) -> bool:
    for prefix, pattern in matchers:
        if prefix and not path.startswith(prefix):
            continue
        if pattern.match(path) is not None:
            return True
    return False


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False
