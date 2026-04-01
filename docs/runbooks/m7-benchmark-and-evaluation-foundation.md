# M7 Benchmark And Evaluation Foundation

## Purpose

Run the repository-owned verification flow for the first executable M7 benchmark and evaluation foundation:

- typed serving benchmark persistence
- offline packaged evaluation execution
- control-plane evaluation command wiring
- export and submission payload shaping over persisted artifacts

## Preconditions

- `make proto` has completed successfully
- Python dependencies are bootstrapped with `make bootstrap`
- Swift toolchain is available for focused control-plane verification

## Python Verification

Run the benchmark and evaluation foundation Python tests:

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" \
uv run --project services/mlx-worker-python pytest \
  services/mlx-worker-python/tests/test_benchmark_schemas.py \
  services/mlx-worker-python/tests/test_release_gates.py \
  services/mlx-worker-python/tests/test_evaluation_schemas.py \
  services/mlx-worker-python/tests/test_evaluation_store.py \
  services/mlx-worker-python/tests/test_evaluation_core.py \
  services/mlx-worker-python/tests/test_maintenance_service.py \
  services/mlx-worker-python/tests/test_control_plane_bridge_phase5.py
```

Expected outcomes:

- benchmark schema tests pass
- release-gate benchmark evidence remains compatible
- packaged dataset execution is deterministic
- `RunEvaluation` returns typed worker job and result payloads
- `ExportResults` writes a machine-readable bundle to the reported path
- `SubmitResults` returns a typed `melix.submission.v1` payload
- the Python control-plane bridge forwards `run-evaluation`

## Checked-In Offline Dataset

The repository-owned default evaluation fixture lives at:

```bash
services/mlx-worker-python/fixtures/evaluation/mmlu.dev.v1/
```

It contains:

- `manifest.json`
- `samples.jsonl`

When the control-plane or worker `RunEvaluation` path uses `dataset_id = "mmlu.dev.v1"` and omits
`dataset_root`, the worker resolves this checked-in fixture from the repository checkout.

## Swift Verification

Run the focused control-plane benchmark or evaluation command tests using a scratch build path:

```bash
HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" \
swift test --package-path services/control-plane-swift \
  --scratch-path /tmp/melix-control-plane-m7-3-5-test \
  --filter 'ControlPlaneServiceTests/executeHandlesOpsRunEvaluationThroughTheModelOperationsWorker|ControlPlaneServiceTests/executeHandlesOpsExportResultsThroughTheModelOperationsWorker|ControlPlaneServiceTests/executeHandlesOpsSubmitResultsThroughTheModelOperationsWorker'
```

Expected outcomes:

- `ops.run_evaluation` maps to the model-operations worker
- typed `evaluationJob` and `evaluationResults` fields are populated on `OpsReply`
- `ops.export_results` surfaces `exportBundleJson`
- `ops.submit_results` surfaces `submissionJson`

## Export And Submit Semantics

- `ExportResults` reads persisted benchmark artifacts from `model-ops/bench/` and persisted
  evaluation artifacts from `model-ops/evaluation/`, then writes `export-bundle.json` at the
  reported `export_path`.
- `SubmitResults` uses the same persisted artifact roots and returns a typed
  `melix.submission.v1` payload with stable device identity fields under `device`.
- For this M7 closure, operator visibility is via machine-readable control-plane/XPC payloads and
  this runbook rather than a dedicated desktop comparison or submission workflow.

## Coverage

Run changed-line coverage for the touched Python scope:

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" \
uv run --project services/mlx-worker-python coverage erase

PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" \
uv run --project services/mlx-worker-python coverage run \
  --source=services/mlx-worker-python/worker \
  -m pytest \
  services/mlx-worker-python/tests/test_maintenance_service.py \
  services/mlx-worker-python/tests/test_control_plane_bridge_phase5.py \
  services/mlx-worker-python/tests/test_evaluation_core.py

PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" \
uv run --project services/mlx-worker-python coverage json -o /tmp/m7-3-5-task4-coverage.json

python3 scripts/python_changed_line_coverage.py \
  --coverage-json /tmp/m7-3-5-task4-coverage.json \
  services/mlx-worker-python/worker/grpc_server.py \
  services/mlx-worker-python/worker/control_plane_bridge.py \
  services/mlx-worker-python/worker/engine/evaluation_core.py
```

Expected outcome:

- changed-line coverage at or above `95%` for the touched Python scope

## Acceptance Checklist

- serving benchmark jobs persist durable JSON artifacts
- evaluation dataset packages run locally without network fetches
- evaluation jobs and results are persisted and machine-readable
- control-plane evaluation command returns typed payloads
- export and submission payloads are repository-owned and machine-readable
- verification commands are repository-owned and reproducible
