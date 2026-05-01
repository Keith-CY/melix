# Model Registry Config-Payload Reuse Optimization Plan

## Goal

Avoid redundant `_load_model_config_payload(...)` helper calls during model-registry scans by threading the already loaded `config.json` payload from the discovery pass into `_raw_model_spec(...)` for both plain local models and Hugging Face cache snapshots.

## Linux Constraint

This slice is Python-only and will be verified locally on Linux. No macOS-only runtime behavior is required for acceptance.

## Touched Files

- `services/mlx-worker-python/worker/model_registry/catalog.py`
- `services/mlx-worker-python/tests/test_model_registry_catalog.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`
- `docs/plans/2026-05-01-model-registry-config-payload-reuse.md`

## Probe Definition

Probe id: `model-registry-config-payload-reuse`

The probe will:
1. build a synthetic registry root with many plain local model directories (`2000` in the current probe)
2. monkeypatch `worker.model_registry.catalog._load_model_config_payload` to count helper invocations while still delegating to the real implementation
3. run repeated `WorkerModelCatalog.registry_snapshot(rescan=True)` scans (`8` measured rescans in the current probe)
4. emit JSON metrics with concrete elapsed time, model count, and mean config-load helper call count

## Success Metrics

- Preserve discovered model ids and metadata behavior exactly.
- Changed executable scope coverage must be `>=95%`.
- Probe must run on both `origin/main` and the branch via the PR-scoped performance harness.
- Head branch should reduce `config_load_calls_mean` relative to `origin/main`, with corresponding elapsed-time improvement on the synthetic scan.

## Verification Commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q \
  services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_plain_local_models_pass_config_payload_into_raw_model_spec \
  services/mlx-worker-python/tests/test_model_registry_catalog.py::test_raw_model_spec_loads_config_payload_when_not_provided \
  services/mlx-worker-python/tests/test_model_registry_catalog.py::test_scan_huggingface_cache_models_passes_config_payload_into_raw_model_spec \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_model_registry_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q \
  services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_plain_local_models_pass_config_payload_into_raw_model_spec \
  services/mlx-worker-python/tests/test_model_registry_catalog.py::test_raw_model_spec_loads_config_payload_when_not_provided \
  services/mlx-worker-python/tests/test_model_registry_catalog.py::test_scan_huggingface_cache_models_passes_config_payload_into_raw_model_spec \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_model_registry_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json \
  services/mlx-worker-python/worker/model_registry/catalog.py \
  services/mlx-worker-python/tests/test_model_registry_catalog.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python bash -lc 'python3 - <<"PY"
import json
import os
import shutil
import statistics
import sys
import tempfile
import time
from pathlib import Path

repo_root = Path.cwd()
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "services/mlx-worker-python"))

from worker.model_registry import catalog as catalog_module
from worker.model_registry.catalog import WorkerModelCatalog


def seed_model(root: Path, name: str) -> None:
    model_dir = root / name
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "config.json").write_text(
        json.dumps({"model_type": "qwen3", "architectures": ["Qwen3ForCausalLM"], "library_name": "mlx"}) + "\n",
        encoding="utf-8",
    )
    (model_dir / "model.safetensors").write_bytes(b"weights")

with tempfile.TemporaryDirectory(prefix="melix-model-registry-probe-") as temp_dir:
    root = Path(temp_dir) / "root"
    for index in range(2000):
        seed_model(root, f"model-{index:04d}")

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": os.fspath(root)})
    original = catalog_module._load_model_config_payload
    call_counts = []
    elapsed_samples = []
    model_counts = []

    def tracking(model_dir: Path, *, json_cache=None):
        call_counts[-1] += 1
        return original(model_dir, json_cache=json_cache)

    catalog_module._load_model_config_payload = tracking
    try:
        for _ in range(8):
            call_counts.append(0)
            started = time.perf_counter()
            snapshot = catalog.registry_snapshot(rescan=True)
            elapsed_samples.append((time.perf_counter() - started) * 1000.0)
            model_counts.append(float(len(snapshot.models)))
    finally:
        catalog_module._load_model_config_payload = original

print(json.dumps({
    "elapsed_ms_mean": round(statistics.fmean(elapsed_samples), 6),
    "config_load_calls_mean": round(statistics.fmean(call_counts), 3),
    "model_count_mean": round(statistics.fmean(model_counts), 3),
    "sample_count": float(len(elapsed_samples)),
}, sort_keys=True))
PY'
```

## Notes

This is a small behavior-preserving optimization slice. No protocol or lockfile changes are expected.
