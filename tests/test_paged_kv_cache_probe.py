from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON_WORKER_ROOT = REPO_ROOT / "services/mlx-worker-python"
sys.path.insert(0, str(PYTHON_WORKER_ROOT))

from worker.productization.pr_scoped_performance import (  # noqa: E402
    build_scope_report,
    load_probe_registry,
)


MODULE_PATH = REPO_ROOT / "scripts/paged_kv_cache_probe.py"
MODULE_SPEC = importlib.util.spec_from_file_location("paged_kv_cache_probe", MODULE_PATH)
assert MODULE_SPEC and MODULE_SPEC.loader
probe = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(probe)
REGISTRY_PATH = REPO_ROOT / "infra/perf/pr_scoped_probes.json"


def paired_payload() -> dict[str, object]:
    return {
        "status": "passed",
        "session_count": 4,
        "acceptance": {
            "owner_leak_count": 0,
            "cache_correctness_mismatch_count": 0,
            "fallback_second_prefill_count": 0,
            "batch_row_cache_identity_mismatch_count": 0,
            "scope_cross_hit_count": 0,
            "stream_owner_fallback_count": 1,
            "leased_entry_eviction_count": 0,
            "trimmed_shared_block_resident_bytes": 0,
            "tightest_budget_violation_count": 0,
        },
        "contiguous": {
            "sample_count": 4,
            "output_token_count": 8,
        },
        "paged": {
            "sample_count": 3,
            "output_token_count": 8,
            "model_eval_batch_size": 4,
            "mlx_active_peak_delta_bytes": 100,
            "tokens_per_second": 20,
        },
        "comparison": {
            "logical_session_bytes": 1_000,
            "resident_block_bytes": 250,
            "mlx_active_peak_delta_reduction_bytes": 500,
            "mlx_reported_peak_delta_reduction_bytes": 450,
            "process_resident_peak_delta_reduction_bytes": 400,
        },
    }


def test_scope_selects_dedicated_paged_kv_probe_for_core_pool() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=[
            "services/mlx-text-worker-swift/Sources/Core/Runtime/PagedKVCache.swift"
        ],
    )

    selected = {entry["id"] for entry in scope["selected_probes"]}
    assert "paged-kv-cache-ownership-memory" in selected


def test_scope_selects_dedicated_paged_kv_probe_for_disk_cache_identity() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-text-worker-swift/Sources/Core/DiskCacheStore.swift"],
    )

    selected = {entry["id"] for entry in scope["selected_probes"]}
    assert "paged-kv-cache-ownership-memory" in selected


def test_versioned_acceptance_artifact_passes_the_default_probe() -> None:
    artifact = json.loads((REPO_ROOT / probe.DEFAULT_ARTIFACT).read_text(encoding="utf-8"))

    metrics = probe.analyze_artifact(artifact)

    assert metrics["status_passed"] == 1.0
    assert metrics["failure_count"] == 0.0


def test_versioned_acceptance_artifact_cites_every_required_regression() -> None:
    artifact = json.loads((REPO_ROOT / probe.DEFAULT_ARTIFACT).read_text(encoding="utf-8"))
    acceptance_source = artifact["acceptance_source"]
    required_tests = {
        test_name
        for test_names in probe.ACCEPTANCE_TESTS.values()
        for test_name in test_names
    }

    assert acceptance_source["kind"] == "swift-test-log-focused-gate-v1"
    assert set(acceptance_source["passing_tests"]) == required_tests


def test_probe_emits_numeric_passing_metrics() -> None:
    metrics = probe.analyze_artifact(paired_payload())

    assert metrics["status_passed"] == 1.0
    assert metrics["status_failed"] == 0.0
    assert metrics["failure_count"] == 0.0
    assert metrics["sample_count_min"] == 3.0
    assert metrics["mlx_active_peak_delta_reduction_bytes"] == 500.0
    assert metrics["stream_owner_fallback_count"] == 1.0
    assert metrics["owner_leak_count"] == 0.0
    assert all(isinstance(value, float) for value in metrics.values())


def test_probe_fails_closed_when_behavioral_acceptance_regresses() -> None:
    payload = paired_payload()
    acceptance = payload["acceptance"]
    assert isinstance(acceptance, dict)
    acceptance["scope_cross_hit_count"] = 1

    metrics = probe.analyze_artifact(payload)

    assert metrics["status_passed"] == 0.0
    assert metrics["status_failed"] == 1.0
    assert metrics["failure_count"] == 1.0


def test_probe_fails_closed_when_paired_sampling_is_insufficient() -> None:
    payload = paired_payload()
    paged = payload["paged"]
    assert isinstance(paged, dict)
    paged["sample_count"] = 1

    metrics = probe.analyze_artifact(payload)

    assert metrics["sample_count_min"] == 1.0
    assert metrics["status_passed"] == 0.0
    assert metrics["status_failed"] == 1.0
    assert metrics["failure_count"] == 1.0


def _write_swift_test_log(
    path: Path,
    test_names: list[str],
    *,
    failing: str | None = None,
) -> None:
    lines = [
        (
            "Test Case '-[MelixTextWorkerCoreTests.WorkerScaffoldTests "
            f"{test_name}]' {'failed' if test_name == failing else 'passed'} (0.001 seconds)."
        )
        for test_name in test_names
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_focused_gate_log_generates_reproducible_acceptance(tmp_path: Path) -> None:
    payload = paired_payload()
    payload.pop("acceptance")
    required = sorted(
        {test_name for tests in probe.ACCEPTANCE_TESTS.values() for test_name in tests}
    )
    log_path = tmp_path / "swift.log"
    _write_swift_test_log(log_path, required)

    probe.add_focused_gate_acceptance(payload, [log_path])

    acceptance = payload["acceptance"]
    assert isinstance(acceptance, dict)
    assert acceptance["owner_leak_count"] == 0
    assert acceptance["stream_owner_fallback_count"] == 3
    source = payload["acceptance_source"]
    assert isinstance(source, dict)
    assert source["kind"] == "swift-test-log-focused-gate-v1"
    assert source["passing_tests"] == required


def test_focused_gate_log_rejects_failed_or_missing_evidence(tmp_path: Path) -> None:
    required = sorted(
        {test_name for tests in probe.ACCEPTANCE_TESTS.values() for test_name in tests}
    )
    log_path = tmp_path / "swift.log"
    _write_swift_test_log(log_path, required, failing=required[0])

    with pytest.raises(ValueError, match="focused gate is missing passing tests"):
        probe.add_focused_gate_acceptance(paired_payload(), [log_path])


def test_registry_probe_command_has_explicit_base_fallback(tmp_path: Path) -> None:
    registry_probe = next(
        entry
        for entry in load_probe_registry(REGISTRY_PATH)
        if entry.probe_id == "paged-kv-cache-ownership-memory"
    )
    completed = subprocess.run(
        registry_probe.probe_command,
        cwd=tmp_path,
        shell=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    metrics = json.loads(completed.stdout)
    assert metrics == {
        "failure_count": 0.0,
        "batch_row_cache_identity_mismatch_count": 0.0,
        "cache_correctness_mismatch_count": 0.0,
        "fallback_second_prefill_count": 0.0,
        "leased_entry_eviction_count": 0.0,
        "logical_session_bytes": 0.0,
        "mlx_active_peak_delta_reduction_bytes": 0.0,
        "mlx_reported_peak_delta_reduction_bytes": 0.0,
        "model_eval_batch_size": 0.0,
        "owner_leak_count": 0.0,
        "paged_mlx_active_peak_delta_bytes": 0.0,
        "paged_tokens_per_second": 0.0,
        "process_resident_peak_delta_reduction_bytes": 0.0,
        "resident_block_bytes": 0.0,
        "sample_count_min": 0.0,
        "scope_cross_hit_count": 0.0,
        "session_count": 0.0,
        "status_failed": 0.0,
        "status_passed": 0.0,
        "status_warning": 1.0,
        "stream_owner_fallback_count": 0.0,
        "tightest_budget_violation_count": 0.0,
        "trimmed_shared_block_resident_bytes": 0.0,
    }


def test_registry_focused_gate_provisions_locked_mlx_extra() -> None:
    registry_probe = next(
        entry
        for entry in load_probe_registry(REGISTRY_PATH)
        if entry.probe_id == "paged-kv-cache-ownership-memory"
    )

    mlx_install = (
        "uv run --frozen --project services/mlx-worker-python --extra mlx pytest"
    )
    assert mlx_install in registry_probe.test_command
    assert registry_probe.test_command.index(mlx_install) < registry_probe.test_command.index(
        "xcrun swift test"
    )


def test_registry_treats_raw_sample_count_as_informational() -> None:
    registry_probe = next(
        entry
        for entry in load_probe_registry(REGISTRY_PATH)
        if entry.probe_id == "paged-kv-cache-ownership-memory"
    )
    metrics = {metric.key: metric for metric in registry_probe.metrics}

    assert metrics["sample_count_min"].direction == "informational"


def test_coverage_gate_requires_ninety_five_percent() -> None:
    coverage_script = (REPO_ROOT / "scripts/paged_kv_cache_coverage.sh").read_text()

    assert "minimum_coverage_pct=95" in coverage_script
    assert 'MELIX_PAGED_KV_COVERAGE_DIFF_FROM:-origin/main' in coverage_script
    assert 'Paged KV changed-line coverage %.2f%% is below %.2f%%.' in coverage_script


def test_latency_gate_excludes_instrumented_and_github_hosted_measurements() -> None:
    coverage_script = (REPO_ROOT / "scripts/paged_kv_cache_coverage.sh").read_text()
    worker_tests = (
        REPO_ROOT
        / "services/mlx-text-worker-swift/Tests/CoreTests/WorkerScaffoldTests.swift"
    ).read_text()

    marker = "MELIX_PAGED_KV_INSTRUMENTED_COVERAGE"
    assert f"{marker}=1" in coverage_script
    assert f'environment["{marker}"] != "1"' in worker_tests
    assert 'environment["RUNNER_ENVIRONMENT"] != "github-hosted"' in worker_tests
    assert "XCTAssertLessThan(results.2, 1_000)" in worker_tests
    assert "XCTAssertLessThan(results.3, 1_000)" in worker_tests


def test_pr_scoped_workflow_passes_exact_base_to_paged_kv_coverage() -> None:
    workflow = (REPO_ROOT / ".github/workflows/pr-scoped-performance.yml").read_text()

    assert (
        "MELIX_PAGED_KV_COVERAGE_DIFF_FROM: "
        "${{ github.event.pull_request.base.sha }}"
    ) in workflow


def test_coverage_gate_only_accepts_zero_lines_for_scoped_runs() -> None:
    coverage_script = (REPO_ROOT / "scripts/paged_kv_cache_coverage.sh").read_text()

    assert "MELIX_CHANGED_SCOPE_COVERAGE_PATHS_JSON" in coverage_script
    assert '"${scope_mode}" != "unfiltered"' in coverage_script
    assert "$'TOTAL\\t100.00%\\t0/0'" in coverage_script
