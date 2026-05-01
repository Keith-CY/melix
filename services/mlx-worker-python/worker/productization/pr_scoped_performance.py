from __future__ import annotations

from dataclasses import dataclass
import fnmatch
import gc
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import tracemalloc
from typing import Any

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

    def to_scope_dict(self) -> dict[str, object]:
        return {
            "id": self.probe_id,
            "name": self.name,
            "runner": self.runner,
            "watch_globs": list(self.watch_globs),
            "test_command": self.test_command,
            "coverage_command": self.coverage_command,
            "probe_command": self.probe_command,
            "metrics": [metric.to_dict() for metric in self.metrics],
        }


def load_probe_registry(path: str | Path) -> tuple[ProbeDefinition, ...]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
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
            )
        )
    return tuple(probes)


def build_scope_report(
    *,
    registry_path: str | Path,
    changed_files: list[str],
) -> dict[str, object]:
    probes = load_probe_registry(registry_path)
    changed_paths = tuple(sorted({path for path in changed_files if path}))
    force_all = any(_matches_any_glob(path, _FORCE_ALL_GLOBS) for path in changed_paths)
    if force_all:
        selected = probes
    else:
        selected = tuple(
            probe
            for probe in probes
            if any(_matches_any_glob(path, probe.watch_globs) for path in changed_paths)
        )
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


def write_report_outputs(report: dict[str, object], output_dir: str | Path) -> dict[str, Path]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / "report.json"
    markdown_path = root / "report.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown_report(report), encoding="utf-8")
    return {"json": json_path, "markdown": markdown_path}


def _run_head_verification(*, probe: ProbeDefinition, repo_root: Path) -> dict[str, object]:
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
    if probe.probe_impl == "closure_audit":
        return _probe_closure_audit(repo_root)
    if probe.probe_impl == "evaluation_job_id":
        return _probe_evaluation_job_id(repo_root)
    if probe.probe_impl == "training_dataset_token_percentiles":
        return _probe_training_dataset_token_percentiles(repo_root)
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
    samples = _build_large_training_dataset_samples()
    elapsed_samples: list[float] = []
    prompt_p95 = 0.0
    total_p95 = 0.0
    sample_count = 0.0
    for _ in range(3):
        gc.collect()
        started = time.perf_counter()
        token_stats = module._build_token_stats(samples, "prompt_completion")
        elapsed_samples.append((time.perf_counter() - started) * 1000.0)
        prompt_p95 = float(token_stats["prompt_tokens_p95"])
        total_p95 = float(token_stats["total_tokens_p95"])
        sample_count = float(token_stats["sample_count"])
    return {
        "elapsed_ms_mean": round(sum(elapsed_samples) / len(elapsed_samples), 3),
        "sample_count": sample_count,
        "prompt_tokens_p95": prompt_p95,
        "total_tokens_p95": total_p95,
    }


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


def _matches_any_glob(path: str, globs: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatch(path, glob) for glob in globs)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False
