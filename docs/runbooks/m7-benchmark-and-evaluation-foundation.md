# M7 Benchmark And Evaluation Foundation

## Purpose

Run the repository-owned verification flow for the first executable M7 benchmark and evaluation foundation:

- typed serving benchmark persistence
- offline packaged evaluation execution
- control-plane evaluation command wiring

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
- the Python control-plane bridge forwards `run-evaluation`

## Swift Verification

Run the focused control-plane evaluation command test using a scratch build path:

```bash
HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" \
swift test --package-path services/control-plane-swift \
  --scratch-path /tmp/melix-control-plane-m7-3-5-test \
  --filter 'ControlPlaneServiceTests/executeHandlesOpsRunEvaluationThroughTheModelOperationsWorker'
```

Expected outcomes:

- `ops.run_evaluation` maps to the model-operations worker
- typed `evaluationJob` and `evaluationResults` fields are populated on `OpsReply`

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
- verification commands are repository-owned and reproducible
