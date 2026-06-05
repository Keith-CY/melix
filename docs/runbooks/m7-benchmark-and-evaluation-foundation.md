# M7 Benchmark And Evaluation Foundation

## Purpose

Run the repository-owned verification flow for the first executable M7 benchmark and evaluation foundation:

- typed serving benchmark persistence
- experimental `bench matrix` persistence and export
- offline packaged evaluation execution
- control-plane evaluation command wiring
- export and submission payload shaping over persisted artifacts
- operator-visible benchmark history, matrix history, visualization, and CSV export through the Window UI and `melix` CLI

## Preconditions

- `make proto` has completed successfully
- Python dependencies are bootstrapped with `make bootstrap`
- Swift toolchain is available for focused control-plane verification

## Operator Window And CLI

The canonical benchmark and evaluation workflows are now available from both the native operator
window and the public `melix` CLI.

Use the native operator window when you need:

- explicit benchmark target model selection
- a `Standard / Matrix` split between product benchmarks and research-style performance matrices
- curated suite multi-select
- benchmark context-length, batch-size, repeat, cache-profile, reasoning-mode, and structured-output controls
- matrix generation-length, concurrency, and request-vs-duration load-budget controls
- evaluation sample-size, batch-factor, few-shot, seed, scoring-mode, and code-exec-policy controls
- persisted history review, metric cards, chart visualization, and CSV export

Use the CLI for deterministic shell-driven execution:

```bash
swift run melix bench run \
  --model-id melix-dev-text::1 \
  --suite smoke \
  --suite latency \
  --context-length 1024 \
  --context-length 4096 \
  --batch-size 2 \
  --batch-size 4 \
  --repeats 3 \
  --cache-profile partial_prefix \
  --reasoning-mode enabled \
  --structured-output-mode json_schema \
  --sample-size 2 \
  --batch-factor 1

swift run melix bench list --json

swift run melix bench export-summary-csv \
  --job-id <benchmark-job-id> \
  --output /tmp/melix-benchmark.csv

swift run melix bench matrix run \
  --model-id melix-dev-text::1 \
  --suite smoke \
  --context-length 1024 \
  --generation-length 128 \
  --generation-length 256 \
  --batch-size 1 \
  --batch-size 2 \
  --cache-profile warm \
  --reasoning-mode disabled \
  --structured-output-mode plain_text \
  --concurrency 1 \
  --concurrency 2 \
  --repeats 2 \
  --requests 4

swift run melix bench matrix list --json

swift run melix bench matrix export-summary-csv \
  --job-id <matrix-job-id> \
  --output /tmp/melix-benchmark-matrix-summary.csv

swift run melix bench matrix export-requests-csv \
  --job-id <matrix-job-id> \
  --output /tmp/melix-benchmark-matrix-requests.csv

swift run melix eval run \
  --model-id melix-dev-text::1 \
  --suite mmlu \
  --sample-size 12 \
  --batch-factor 2 \
  --few-shot 4 \
  --seed 9 \
  --scoring-mode multiple_choice_accuracy \
  --code-exec-policy sandboxed

swift run melix eval list --json

swift run melix eval export-summary-csv \
  --job-id <evaluation-job-id> \
  --output /tmp/melix-evaluation-summary.csv

swift run melix eval export-samples-csv \
  --job-id <evaluation-job-id> \
  --output /tmp/melix-evaluation-samples.csv

swift run melix eval export-samples-jsonl \
  --job-id <evaluation-job-id> \
  --output /tmp/melix-evaluation-samples.jsonl
```

Each benchmark run is persisted under `<jobs_root>/bench/runs/<job_id>/`. The shared export
bundle used by both the native operator window and CLI also records dataset provenance, suite
metadata, canonical benchmark sweep rows, evaluation summary rows, and cache-hit state for the
curated Hugging Face suite inputs.

Each matrix run is persisted under `<jobs_root>/bench/matrix-runs/<job_id>/` with job JSON,
summary JSON and CSV, plus request-row JSONL and CSV artifacts.

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
- `ExportResultsStream` streams bounded export chunks for large bundles
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
  --filter 'ControlPlaneServiceTests|BenchmarkExportBundleTests'
```

Expected outcomes:

- canonical benchmark fields are validated and forwarded to the worker request
- `ops.run_evaluation` maps to the model-operations worker
- typed `evaluationJob` and `evaluationResults` fields are populated on `OpsReply`
- `ops.export_results` reconstructs the streamed export bundle and surfaces `exportBundleJson`
- `ops.submit_results` surfaces `submissionJson`
- canonical evaluation summary rows decode and export correctly from the shared bundle

## Export And Submit Semantics

- `ExportResults` reads persisted benchmark artifacts from `model-ops/bench/` and persisted
  evaluation artifacts from `model-ops/evaluation/`, then writes `export-bundle.json` at the
  reported `export_path`.
- `ExportResultsStream` uses the same bundle writer as `ExportResults`, then emits a
  `started` event, ordered raw-byte `chunk` events, and a terminal `completed` event with total
  bytes, chunk count, and SHA-256. The Swift control plane must prefer this streaming RPC for
  `ops.export_results`, validate chunk order and byte counts, and reconstruct the same
  `exportBundleJson` surface consumed by CLI, Window UI, benchmark, evaluation, and LoRA flows.
  The worker must publish `export-bundle.json` through an atomic same-directory replacement before
  streaming, so a concurrent export does not rewrite the file descriptor held by an active reader.
  The unary `ExportResults` RPC remains available only as a compatibility path for older clients
  and test doubles.
- `melix bench export-summary-csv` writes canonical benchmark summary rows. The shared export
  bundle also preserves context-sweep and batch-sweep rows for the Window UI and future lab-style
  analysis.
- `melix bench matrix export-summary-csv` writes matrix summary rows, and
  `melix bench matrix export-requests-csv` writes the request-level observation table for one
  persisted matrix run.
- `melix eval export-summary-csv` writes canonical evaluation summary rows.
- `melix eval export-samples-csv` and `melix eval export-samples-jsonl` export per-sample evidence
  with `id`, `correct`, `expected`, `predicted`, `question`, `raw_response`, `time_s`, and
  `parse_status`.
- `SubmitResults` uses the same persisted artifact roots and returns a typed
  `melix.submission.v1` payload with stable device identity fields under `device`.
- For this M7 closure, operator visibility includes the dedicated benchmark controls in the native
  operator window together with `melix bench list`, `melix bench export-summary-csv`, `melix eval
  list`, and the evaluation export commands.

## Coverage

Run changed-line coverage for the touched executable scope:

```bash
HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" \
swift test --enable-code-coverage --filter MelixCLITests

python3 scripts/swift_changed_line_coverage.py \
  --binary .build/arm64-apple-macosx/debug/melixPackageTests.xctest/Contents/MacOS/melixPackageTests \
  --profdata .build/arm64-apple-macosx/debug/codecov/default.profdata \
  --diff-from d1ceaba \
  Sources/MelixCLICore/MelixCLI.swift \
  tests/MelixCLITests/MelixCLIParserTests.swift \
  tests/MelixCLITests/MelixCLIRunnerTests.swift

HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/services/control-plane-swift/.build/ModuleCache.noindex" \
swift test --package-path services/control-plane-swift --enable-code-coverage \
  --filter 'ControlPlaneServiceTests|BenchmarkExportBundleTests'

python3 scripts/swift_changed_line_coverage.py \
  --binary services/control-plane-swift/.build/arm64-apple-macosx/debug/MelixControlPlanePackageTests.xctest/Contents/MacOS/MelixControlPlanePackageTests \
  --profdata services/control-plane-swift/.build/arm64-apple-macosx/debug/codecov/default.profdata \
  --diff-from d1ceaba \
  services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift \
  services/control-plane-swift/Sources/XPCService/BenchmarkExportBundle.swift \
  services/control-plane-swift/Sources/XPCService/ControlPlaneXPCClient.swift \
  services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift \
  services/control-plane-swift/Tests/ControlPlaneTests/BenchmarkExportBundleTests.swift

HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/apps/macos-menubar/.build/ModuleCache.noindex" \
swift test --package-path apps/macos-menubar --enable-code-coverage \
  --filter 'RuntimeViewModelTests|DesktopFoundationViewTests|ControlPlaneXPCClientTests'

python3 scripts/swift_changed_line_coverage.py \
  --binary apps/macos-menubar/.build/arm64-apple-macosx/debug/MelixMacOSMenubarPackageTests.xctest/Contents/MacOS/MelixMacOSMenubarPackageTests \
  --profdata apps/macos-menubar/.build/arm64-apple-macosx/debug/codecov/default.profdata \
  --diff-from d1ceaba \
  apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift \
  apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift \
  apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift \
  apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift \
  apps/macos-menubar/Tests/MenuBarTests/ControlPlaneXPCClientTests.swift

PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage erase

PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run \
  --source=services/mlx-worker-python/worker \
  -m pytest \
  services/mlx-worker-python/tests/test_maintenance_service.py \
  services/mlx-worker-python/tests/test_benchmark_schemas.py \
  services/mlx-worker-python/tests/test_benchmark_export.py \
  services/mlx-worker-python/tests/test_evaluation_core.py \
  services/mlx-worker-python/tests/test_evaluation_store.py \
  services/mlx-worker-python/tests/test_submission_builder.py \
  services/mlx-worker-python/tests/test_release_gates.py -q

PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json \
  -o /tmp/melix-coverage/bench-eval-contract-expansion-python.json

python3 scripts/python_changed_line_coverage.py \
  --coverage-json /tmp/melix-coverage/bench-eval-contract-expansion-python.json \
  --diff-from d1ceaba \
  services/mlx-worker-python/worker/engine/maintenance_core.py \
  services/mlx-worker-python/worker/productization/benchmark_schemas.py \
  services/mlx-worker-python/worker/productization/benchmark_export.py \
  services/mlx-worker-python/worker/productization/submission_builder.py \
  services/mlx-worker-python/worker/engine/evaluation_core.py \
  services/mlx-worker-python/worker/grpc_server.py \
  services/mlx-worker-python/worker/productization/evaluation_schemas.py \
  services/mlx-worker-python/worker/productization/evaluation_store.py
```

Expected outcome:

- changed-line coverage at or above `95%` for the touched executable scope in each package slice

## Acceptance Checklist

- serving benchmark jobs persist durable JSON artifacts
- matrix benchmark jobs persist durable JSON, CSV, and request-level observation artifacts
- evaluation dataset packages run locally without network fetches
- evaluation jobs and results are persisted and machine-readable
- control-plane evaluation command returns typed payloads
- export and submission payloads are repository-owned and machine-readable
- Window UI exposes the canonical benchmark, matrix benchmark, and evaluation operator controls
- CLI exposes canonical benchmark, matrix benchmark, and evaluation run plus export commands
- verification commands are repository-owned and reproducible
