from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


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


def test_probe_emits_numeric_passing_metrics() -> None:
    metrics = probe.analyze_artifact(paired_payload())

    assert metrics["status_passed"] == 1.0
    assert metrics["status_failed"] == 0.0
    assert metrics["failure_count"] == 0.0
    assert metrics["sample_count_min"] == 3.0
    assert metrics["mlx_active_peak_delta_reduction_bytes"] == 500.0
    assert all(isinstance(value, float) for value in metrics.values())


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
        "logical_session_bytes": 0.0,
        "mlx_active_peak_delta_reduction_bytes": 0.0,
        "mlx_reported_peak_delta_reduction_bytes": 0.0,
        "model_eval_batch_size": 0.0,
        "paged_mlx_active_peak_delta_bytes": 0.0,
        "paged_tokens_per_second": 0.0,
        "process_resident_peak_delta_reduction_bytes": 0.0,
        "resident_block_bytes": 0.0,
        "sample_count_min": 0.0,
        "session_count": 0.0,
        "status_failed": 0.0,
        "status_passed": 0.0,
        "status_warning": 1.0,
    }
