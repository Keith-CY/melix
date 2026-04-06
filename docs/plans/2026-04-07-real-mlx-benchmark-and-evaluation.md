# Real MLX Benchmark And Evaluation Recovery

## Goal

Replace the current deterministic-only benchmark and evaluation execution path with repository-owned real MLX inference for the local benchmark runner and the worker evaluation flow.

## Scope

- switch the temporary benchmark runner to start the Python worker with the real MLX backend
- verify that benchmark runs for the selected shared and cached models produce live runtime timings rather than deterministic stub timings
- update worker-side evaluation execution to use a loaded model handle and live runtime generation instead of `_deterministic_answer`
- preserve serial execution and explicit model unload between models so benchmark and evaluation runs do not interfere with one another
- emit fresh benchmark, matrix, evaluation, and summary reports into a new isolated temporary directory

## Non-Goals

- redesign the benchmark or evaluation artifact schema
- add remote datasets or cloud evaluation infrastructure
- broaden the checked-in evaluation fixture beyond the existing repository-owned package in this transaction
- remove deterministic backends from unrelated capability families

## Performance Probes

### Benchmark

- `bench.*.ttft_ms`
- `bench.*.prefill_tokens_per_second`
- `bench.*.decode_tokens_per_second`
- `bench.*.request_p50_ms`
- `bench.*.request_p95_ms`
- `bench.matrix.*.ttft_mean_ms`
- `bench.matrix.*.throughput_requests_per_second`
- `bench.matrix.*.throughput_tokens_per_second`
- `bench.*.peak_memory_bytes`

### Evaluation

- `eval.*.score_value`
- `eval.*.correct_count`
- `eval.*.incorrect_count`
- `eval.*.duration_seconds`
- per-sample `time_s`
- per-sample `parse_status`
- worker runtime selection evidence through the loaded model handle and runtime kind

## Success Metrics

- benchmark runs no longer boot the Python worker with `--backend-mode deterministic`
- benchmark `ttft_ms` and throughput values are derived from live runtime generation events
- Gemma 4 registry models can be exercised through the real MLX runtime path without being rejected as an unsupported family for prompt-only benchmark and evaluation inputs
- evaluation sample rows are produced from live runtime output, not repository-local arithmetic matching
- the runner executes one model at a time and unloads or tears down runtime state before starting the next model
- a fresh temporary report root contains CSV and Markdown summaries together with per-model benchmark, matrix, and evaluation artifacts

## Execution Plan

### 1. Real Benchmark Backend Recovery

- update `/tmp/melix_cli_bench_eval_runner.py` so the Python worker starts with `--backend-mode auto`
- keep the runner serial and ensure runtime directories are reset between models
- smoke-test one model first to confirm the live MLX path loads and returns plausible timings
- rerun the full four-model benchmark and matrix sequence only after the smoke path is real

### 2. Real Evaluation Execution

- add failing worker tests that prove evaluation calls the loaded runtime instead of `_deterministic_answer`
- update `services/mlx-worker-python/worker/engine/evaluation_core.py` to:
  - resolve the loaded model from `model_handle`
  - render the prompt through the runtime
  - execute live generation
  - parse the resulting assistant text into the persisted sample record
- wire `WorkerMaintenanceService.RunEvaluation` to pass the registry-backed execution context into `EvaluationCore`
- keep the existing artifact schema and export surfaces intact

### 3. Verification And Evidence

- run focused Python tests for benchmark or evaluation worker paths
- run focused Swift control-plane tests for registry synchronization and benchmark or evaluation routing where touched
- rebuild `melix` in release mode before the final real benchmark and evaluation run
- capture a metrics report for the touched scope and record any explicit `N/A` gaps if changed-line coverage cannot be measured for the temporary runner

## Verification

- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_evaluation_core.py services/mlx-worker-python/tests/test_maintenance_service.py services/mlx-worker-python/tests/test_mlx_vlm_runtime.py`
- `swift test --package-path services/control-plane-swift --filter ControlPlaneServiceTests/executeSyncsRegistryModelsBeforeRunBenchResolution`
- `swift test --package-path services/control-plane-swift --filter ControlPlaneServiceTests/executeSyncsRegistryModelsBeforeWorkerBackedModelLoad`
- `swift build -c release --product melix`

## Acceptance

- the benchmark runner emits a new temporary report directory backed by real MLX generation rather than deterministic stub output
- the worker evaluation flow persists real runtime sample predictions and summary metrics
- the four target models complete serial benchmark, matrix, and evaluation runs with isolated runtime cleanup between models
- the final handoff includes the new result directory, verification command outcomes, and any residual limits
