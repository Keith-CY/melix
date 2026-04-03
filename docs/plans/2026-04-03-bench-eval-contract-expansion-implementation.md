# Bench And Eval Contract Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand Melix benchmark and evaluation execution so the implemented product matches the canonical `docs/benchmark-evaluation-contract.md` surface for operator-facing `bench run` and `eval run`.

**Architecture:** Extend the existing shared control-plane request path rather than introducing new side-channel execution paths. The Swift control plane remains the orchestration truth for request normalization, target resolution, and UI or CLI history exposure, while the Python worker remains the execution truth for context sweeps, batch sweeps, score aggregation, and export artifacts. Compatibility aliases stay in place for older benchmark reports, but all new request and export paths write the canonical contract fields.

**Tech Stack:** Swift, SwiftUI, Python, protobuf, pytest, Swift Testing, existing Melix export bundle and productization layers.

---

## File Structure

### Protocol And Generated Outputs

- Modify: `packages/protocol/schema/controlplane/v1/control_plane.proto`
- Modify: `packages/protocol/schema/worker/v1/maintenance.proto`
- Regenerate: `packages/protocol/descriptors/melix.pb`
- Regenerate: `packages/protocol/python/controlplane/v1/control_plane_pb2.py`
- Regenerate: `packages/protocol/python/worker/v1/maintenance_pb2.py`
- Regenerate: `packages/protocol/swift/controlplane/v1/control_plane.pb.swift`
- Regenerate: `packages/protocol/swift/worker/v1/maintenance.pb.swift`

### Swift Control Plane And CLI

- Modify: `Sources/MelixCLICore/MelixCLI.swift`
- Modify: `services/control-plane-swift/Sources/XPCService/ControlPlaneXPCClient.swift`
- Modify: `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`
- Modify: `services/control-plane-swift/Sources/XPCService/BenchmarkExportBundle.swift`
- Test: `tests/MelixCLITests/MelixCLIParserTests.swift`
- Test: `tests/MelixCLITests/MelixCLIRunnerTests.swift`
- Test: `services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift`
- Test: `services/control-plane-swift/Tests/ControlPlaneTests/BenchmarkExportBundleTests.swift`

### Python Worker

- Modify: `services/mlx-worker-python/worker/engine/maintenance_core.py`
- Modify: `services/mlx-worker-python/worker/engine/evaluation_core.py`
- Modify: `services/mlx-worker-python/worker/grpc_server.py`
- Modify: `services/mlx-worker-python/worker/productization/benchmark_schemas.py`
- Modify: `services/mlx-worker-python/worker/productization/benchmark_export.py`
- Modify: `services/mlx-worker-python/worker/productization/evaluation_schemas.py`
- Modify: `services/mlx-worker-python/worker/productization/evaluation_store.py`
- Modify: `services/mlx-worker-python/worker/productization/submission_builder.py`
- Test: `services/mlx-worker-python/tests/test_benchmark_schemas.py`
- Test: `services/mlx-worker-python/tests/test_benchmark_export.py`
- Test: `services/mlx-worker-python/tests/test_maintenance_service.py`
- Test: `services/mlx-worker-python/tests/test_evaluation_core.py`
- Test: `services/mlx-worker-python/tests/test_evaluation_store.py`

### Window UI

- Modify: `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift`
- Test: `apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift`
- Test: `apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift`
- Test: `apps/macos-menubar/Tests/MenuBarTests/ControlPlaneXPCClientTests.swift`

### Documentation And Transaction Records

- Modify: `docs/runbooks/m7-benchmark-and-evaluation-foundation.md`
- Modify: `progress.md`
- Modify: `task_plan.md`

## Performance Probes And Success Metrics

### Bench

- Probe `prefill_tokens_per_second` per context length
- Probe `decode_tokens_per_second` per context length and batch size
- Probe `ttft_ms` per repeat
- Probe `request_p50_ms` and `request_p95_ms` over the repeated run window
- Probe `peak_memory_bytes` per context sweep row
- Probe `speedup_vs_batch_1` for batch rows
- Probe `preprocess_ms` for image-to-text and image-text-to-text tasks
- Probe `artifact_publish_ms` and `output_bytes` for image generation and image editing tasks

Success metrics:

- `bench run` accepts `context_lengths[]`, `generation_length`, `batch_sizes[]`, `repeats`, `cache_profile`, `reasoning_mode`, and `structured_output_mode`
- persisted exports contain canonical metric names and row shapes from `docs/benchmark-evaluation-contract.md`
- benchmark history UI and CLI present the canonical metrics without relying on compatibility alias names

### Eval

- Probe `score_value` per suite
- Probe `correct_count` and `incorrect_count`
- Probe `duration_seconds`
- Probe `parse_status` per sample row
- Probe code-execution outcome mapping for `humaneval` and `mbpp`

Success metrics:

- `eval run` accepts `few_shot`, `seed`, `scoring_mode`, and `code_exec_policy`
- summary exports contain canonical suite-level fields
- sample exports contain canonical CSV and JSONL fields, including `parse_status`

## Task 1: Extend Protocol Surfaces For Canonical Bench And Eval Inputs

**Files:**
- Modify: `packages/protocol/schema/controlplane/v1/control_plane.proto`
- Modify: `packages/protocol/schema/worker/v1/maintenance.proto`
- Regenerate: `packages/protocol/descriptors/melix.pb`
- Regenerate: `packages/protocol/python/controlplane/v1/control_plane_pb2.py`
- Regenerate: `packages/protocol/python/worker/v1/maintenance_pb2.py`
- Regenerate: `packages/protocol/swift/controlplane/v1/control_plane.pb.swift`
- Regenerate: `packages/protocol/swift/worker/v1/maintenance.pb.swift`
- Test: `tests/MelixCLITests/MelixCLIParserTests.swift`
- Test: `services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift`

- [ ] **Step 1: Write failing parser and service tests for the new request fields**

Add parser and control-plane tests that expect:

- `bench run` to accept repeated `--context-length` and `--batch-size`
- `bench run` to accept `--repeats`, `--cache-profile`, `--reasoning-mode`, and `--structured-output-mode`
- `eval run` to accept `--few-shot`, `--seed`, `--scoring-mode`, and `--code-exec-policy`
- request structs to carry the normalized values

Run:

```bash
swift test --filter 'MelixCLIParserTests|ControlPlaneServiceTests'
```

Expected:

- parser and service tests fail because the new fields are not yet present

- [ ] **Step 2: Update protobuf schemas with canonical request fields**

Add these fields to the control-plane and worker request shapes:

```proto
repeated uint32 context_lengths = ...;
uint32 generation_length = ...;
repeated uint32 batch_sizes = ...;
uint32 repeats = ...;
string cache_profile = ...;
string reasoning_mode = ...;
string structured_output_mode = ...;
uint32 few_shot = ...;
uint64 seed = ...;
string scoring_mode = ...;
string code_exec_policy = ...;
```

Keep numbering stable and additive.

- [ ] **Step 3: Regenerate protocol outputs**

Run:

```bash
make proto
```

Expected:

- generated Python, Swift, and descriptor outputs update in the same change

- [ ] **Step 4: Re-run the focused failing tests**

Run:

```bash
swift test --filter 'MelixCLIParserTests|ControlPlaneServiceTests'
```

Expected:

- parser-level shape failures move from missing-field failures to implementation failures

- [ ] **Step 5: Commit**

```bash
git add packages/protocol/schema/controlplane/v1/control_plane.proto \
  packages/protocol/schema/worker/v1/maintenance.proto \
  packages/protocol/descriptors/melix.pb \
  packages/protocol/python/controlplane/v1/control_plane_pb2.py \
  packages/protocol/python/worker/v1/maintenance_pb2.py \
  packages/protocol/swift/controlplane/v1/control_plane.pb.swift \
  packages/protocol/swift/worker/v1/maintenance.pb.swift \
  tests/MelixCLITests/MelixCLIParserTests.swift \
  services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift
git commit -m "feat: extend bench and eval protocol inputs"
```

## Task 2: Implement Canonical Bench Request Normalization In CLI And Control Plane

**Files:**
- Modify: `Sources/MelixCLICore/MelixCLI.swift`
- Modify: `services/control-plane-swift/Sources/XPCService/ControlPlaneXPCClient.swift`
- Modify: `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`
- Test: `tests/MelixCLITests/MelixCLIParserTests.swift`
- Test: `tests/MelixCLITests/MelixCLIRunnerTests.swift`
- Test: `services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift`

- [ ] **Step 1: Write or extend failing CLI and service tests for canonical bench normalization**

Add test coverage for:

- repeated `--context-length` normalization and sorted request output
- repeated `--batch-size` normalization and sorted request output
- defaulting `repeats` to `1`
- rejecting invalid `cache_profile`
- forwarding `reasoning_mode` and `structured_output_mode`

Run:

```bash
swift test --enable-code-coverage --filter MelixCLITests
swift test --package-path services/control-plane-swift --enable-code-coverage --filter ControlPlaneServiceTests
```

Expected:

- new bench request normalization tests fail

- [ ] **Step 2: Implement the new CLI parser and runner options**

Add the new options in `MelixCLI.swift` and normalize them into the shared request model:

```swift
--context-length 1024 --context-length 4096
--batch-size 2 --batch-size 4
--repeats 3
--cache-profile partial_prefix
--reasoning-mode enabled
--structured-output-mode json_schema
```

- [ ] **Step 3: Extend the shared control-plane client request structs**

Update the shared request structs so `ControlPlaneXPCClient` and the CLI both use one normalized representation with:

- `contextLengths`
- `generationLength`
- `batchSizes`
- `repeats`
- `cacheProfile`
- `reasoningMode`
- `structuredOutputMode`

- [ ] **Step 4: Update `ControlPlaneService` request mapping**

Map the normalized request into the control-plane worker command path and validate:

- at least one suite
- at least one context length
- `repeats >= 1`
- `cache_profile` belongs to `cold|warm|partial_prefix`

- [ ] **Step 5: Re-run focused Swift tests**

Run:

```bash
swift test --enable-code-coverage --filter MelixCLITests
swift test --package-path services/control-plane-swift --enable-code-coverage --filter ControlPlaneServiceTests
```

Expected:

- focused Swift tests pass

- [ ] **Step 6: Commit**

```bash
git add Sources/MelixCLICore/MelixCLI.swift \
  services/control-plane-swift/Sources/XPCService/ControlPlaneXPCClient.swift \
  services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift \
  tests/MelixCLITests/MelixCLIParserTests.swift \
  tests/MelixCLITests/MelixCLIRunnerTests.swift \
  services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift
git commit -m "feat: normalize canonical bench requests"
```

## Task 3: Implement Canonical Bench Metrics, Sweeps, And Exports In The Python Worker

**Files:**
- Modify: `services/mlx-worker-python/worker/engine/maintenance_core.py`
- Modify: `services/mlx-worker-python/worker/productization/benchmark_schemas.py`
- Modify: `services/mlx-worker-python/worker/productization/benchmark_export.py`
- Modify: `services/mlx-worker-python/worker/productization/submission_builder.py`
- Test: `services/mlx-worker-python/tests/test_maintenance_service.py`
- Test: `services/mlx-worker-python/tests/test_benchmark_schemas.py`
- Test: `services/mlx-worker-python/tests/test_benchmark_export.py`

- [ ] **Step 1: Write failing worker tests for context sweep and batch sweep persistence**

Add tests that expect persisted rows to contain:

- `context_length`
- `generation_length`
- `cache_profile`
- `repeat_index`
- canonical metric names
- `speedup_vs_batch_1` on batch rows

Run:

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" \
uv run --project services/mlx-worker-python pytest \
  services/mlx-worker-python/tests/test_maintenance_service.py \
  services/mlx-worker-python/tests/test_benchmark_schemas.py \
  services/mlx-worker-python/tests/test_benchmark_export.py -q
```

Expected:

- new benchmark shape assertions fail

- [ ] **Step 2: Implement canonical single-request and batch-row metric schemas**

Update the benchmark schema helpers so the persisted data model distinguishes:

- run summary
- context-sweep rows
- batch-sweep rows

Required fields:

```python
context_length
generation_length
batch_size
repeat_index
prefill_tokens_per_second
decode_tokens_per_second
ttft_ms
request_latency_ms
peak_memory_bytes
speedup_vs_batch_1
```

- [ ] **Step 3: Implement repeated-run measurement and percentile aggregation**

Update the runtime benchmark path so:

- each context length can run `repeats` times
- raw per-repeat request latency is captured
- `request_p50_ms` and `request_p95_ms` are persisted in the run summary

- [ ] **Step 4: Implement cache-profile-aware request shaping**

Add explicit execution behavior for:

- `cold`
- `warm`
- `partial_prefix`

Do not silently map `partial_prefix` to `warm`.

- [ ] **Step 5: Update CSV export and compatibility aliases**

`bench export-summary-csv` must emit canonical rows while preserving legacy aliases only as compatibility fields in the raw export bundle.

- [ ] **Step 6: Re-run focused Python tests**

Run:

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" \
uv run --project services/mlx-worker-python pytest \
  services/mlx-worker-python/tests/test_maintenance_service.py \
  services/mlx-worker-python/tests/test_benchmark_schemas.py \
  services/mlx-worker-python/tests/test_benchmark_export.py -q
```

Expected:

- focused Python tests pass

- [ ] **Step 7: Commit**

```bash
git add services/mlx-worker-python/worker/engine/maintenance_core.py \
  services/mlx-worker-python/worker/productization/benchmark_schemas.py \
  services/mlx-worker-python/worker/productization/benchmark_export.py \
  services/mlx-worker-python/worker/productization/submission_builder.py \
  services/mlx-worker-python/tests/test_maintenance_service.py \
  services/mlx-worker-python/tests/test_benchmark_schemas.py \
  services/mlx-worker-python/tests/test_benchmark_export.py
git commit -m "feat: expand canonical benchmark sweeps and exports"
```

## Task 4: Implement Canonical Eval Controls And Sample Exports

**Files:**
- Modify: `Sources/MelixCLICore/MelixCLI.swift`
- Modify: `services/control-plane-swift/Sources/XPCService/ControlPlaneXPCClient.swift`
- Modify: `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`
- Modify: `services/mlx-worker-python/worker/engine/evaluation_core.py`
- Modify: `services/mlx-worker-python/worker/grpc_server.py`
- Modify: `services/mlx-worker-python/worker/productization/evaluation_schemas.py`
- Modify: `services/mlx-worker-python/worker/productization/evaluation_store.py`
- Modify: `services/mlx-worker-python/worker/productization/benchmark_export.py`
- Test: `tests/MelixCLITests/MelixCLIParserTests.swift`
- Test: `tests/MelixCLITests/MelixCLIRunnerTests.swift`
- Test: `services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift`
- Test: `services/mlx-worker-python/tests/test_evaluation_core.py`
- Test: `services/mlx-worker-python/tests/test_evaluation_store.py`

- [ ] **Step 1: Write failing tests for canonical eval control fields**

Add tests that expect:

- CLI parsing for `--few-shot`, `--seed`, `--scoring-mode`, and `--code-exec-policy`
- worker persistence of these fields in evaluation job metadata
- sample exports to include `parse_status`

Run:

```bash
swift test --enable-code-coverage --filter MelixCLITests
swift test --package-path services/control-plane-swift --enable-code-coverage --filter ControlPlaneServiceTests
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" \
uv run --project services/mlx-worker-python pytest \
  services/mlx-worker-python/tests/test_evaluation_core.py \
  services/mlx-worker-python/tests/test_evaluation_store.py -q
```

Expected:

- new eval normalization and export tests fail

- [ ] **Step 2: Implement CLI and shared-client eval option forwarding**

Add parser and runner support for:

```bash
--few-shot 5
--seed 42
--scoring-mode exact_match
--code-exec-policy sandboxed
```

- [ ] **Step 3: Extend evaluation persistence schemas**

Persist the canonical job and sample fields:

```python
few_shot
seed
scoring_mode
code_exec_policy
parse_status
incorrect_count
duration_seconds
```

- [ ] **Step 4: Implement score-mode and parse-status wiring in `evaluation_core.py`**

Ensure the worker:

- records the selected scorer mode in result metadata
- records answer extraction success or fallback in `parse_status`
- records code-eval execution policy for `humaneval` and `mbpp`

- [ ] **Step 5: Update evaluation export bundle decoding and CSV generation**

Summary CSV and sample CSV or JSONL must match `docs/benchmark-evaluation-contract.md`.

- [ ] **Step 6: Re-run focused tests**

Run:

```bash
swift test --enable-code-coverage --filter MelixCLITests
swift test --package-path services/control-plane-swift --enable-code-coverage --filter ControlPlaneServiceTests
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" \
uv run --project services/mlx-worker-python pytest \
  services/mlx-worker-python/tests/test_evaluation_core.py \
  services/mlx-worker-python/tests/test_evaluation_store.py \
  services/mlx-worker-python/tests/test_benchmark_export.py -q
```

Expected:

- focused Swift and Python tests pass

- [ ] **Step 7: Commit**

```bash
git add Sources/MelixCLICore/MelixCLI.swift \
  services/control-plane-swift/Sources/XPCService/ControlPlaneXPCClient.swift \
  services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift \
  services/mlx-worker-python/worker/engine/evaluation_core.py \
  services/mlx-worker-python/worker/grpc_server.py \
  services/mlx-worker-python/worker/productization/evaluation_schemas.py \
  services/mlx-worker-python/worker/productization/evaluation_store.py \
  services/mlx-worker-python/worker/productization/benchmark_export.py \
  tests/MelixCLITests/MelixCLIParserTests.swift \
  tests/MelixCLITests/MelixCLIRunnerTests.swift \
  services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift \
  services/mlx-worker-python/tests/test_evaluation_core.py \
  services/mlx-worker-python/tests/test_evaluation_store.py
git commit -m "feat: extend canonical evaluation controls and exports"
```

## Task 5: Productize Window UI For Canonical Bench And Eval Controls

**Files:**
- Modify: `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift`
- Test: `apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift`
- Test: `apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift`
- Test: `apps/macos-menubar/Tests/MenuBarTests/ControlPlaneXPCClientTests.swift`

- [ ] **Step 1: Write failing UI-state tests for canonical controls**

Add tests that expect:

- multiple context-length selections
- multiple batch-size selections
- cache-profile picker
- reasoning-mode picker
- structured-output picker
- eval few-shot, seed, scoring-mode, and code-exec-policy controls

Run:

```bash
swift test --package-path apps/macos-menubar --enable-code-coverage --filter 'RuntimeViewModelTests|DesktopFoundationViewTests|ControlPlaneXPCClientTests'
```

Expected:

- new UI-state tests fail because the state and request forwarding are not yet implemented

- [ ] **Step 2: Extend `RuntimeViewModel` bench and eval state**

Add state and normalization helpers for:

- `selectedBenchContextLengths`
- `selectedBenchBatchSizes`
- `benchRepeats`
- `benchCacheProfile`
- `benchReasoningMode`
- `benchStructuredOutputMode`
- `evaluationFewShot`
- `evaluationSeed`
- `evaluationScoringMode`
- `evaluationCodeExecPolicy`

- [ ] **Step 3: Extend `DesktopWorkspaceShellView` controls and history presentation**

Add operator-facing controls for the new request fields while keeping the performance and evaluation sections visually separate.

- [ ] **Step 4: Re-run focused menubar tests**

Run:

```bash
swift test --package-path apps/macos-menubar --enable-code-coverage --filter 'RuntimeViewModelTests|DesktopFoundationViewTests|ControlPlaneXPCClientTests'
```

Expected:

- focused Window UI tests pass

- [ ] **Step 5: Commit**

```bash
git add apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift \
  apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift \
  apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift \
  apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift \
  apps/macos-menubar/Tests/MenuBarTests/ControlPlaneXPCClientTests.swift
git commit -m "feat: productize canonical bench and eval controls"
```

## Task 6: Documentation, Coverage, And Final Verification

**Files:**
- Modify: `docs/runbooks/m7-benchmark-and-evaluation-foundation.md`
- Modify: `progress.md`
- Modify: `task_plan.md`

- [ ] **Step 1: Update runbooks for the canonical request and export contract**

Document the final operator and CLI flows for:

- `melix bench run`
- `melix bench export-summary-csv`
- `melix eval run`
- `melix eval export-summary-csv`
- `melix eval export-samples-csv`
- `melix eval export-samples-jsonl`

- [ ] **Step 2: Run targeted changed-line coverage commands**

Run:

```bash
python3 scripts/swift_changed_line_coverage.py ...
python3 scripts/python_changed_line_coverage.py ...
```

Expected:

- every touched executable scope is `>=95%`

- [ ] **Step 3: Run repository verification**

Run:

```bash
make proto
make py-test
make swift-test
make integration-test
```

Expected:

- repository verification passes, or any failure outside the touched scope is explicitly recorded with evidence in `progress.md`

- [ ] **Step 4: Record metrics and outcomes**

Update `progress.md` with:

- verification commands
- pass or fail outcomes
- changed-line coverage for touched executable scope
- explicit `N/A` reasons for any docs-only sub-slices

- [ ] **Step 5: Commit**

```bash
git add docs/runbooks/m7-benchmark-and-evaluation-foundation.md progress.md task_plan.md
git commit -m "docs: close canonical bench and eval expansion"
```

## Self-Review

### Spec Coverage

This plan covers:

- canonical bench input fields
- canonical eval input fields
- benchmark and evaluation export rows
- Window UI and CLI parity
- task-aware performance probes

Deferred by design:

- VLM intelligence suites
- combined one-command benchmark plus evaluation runs
- research-only performance matrix workflows

### Placeholder Scan

No `TODO`, `TBD`, or implied follow-up placeholders remain in the task steps. Each task names exact files, commands, and commit boundaries.

### Type Consistency

The same canonical field names are used across tasks:

- `context_lengths`
- `generation_length`
- `batch_sizes`
- `repeats`
- `cache_profile`
- `reasoning_mode`
- `structured_output_mode`
- `few_shot`
- `seed`
- `scoring_mode`
- `code_exec_policy`

The same output field names are used across tasks:

- `prefill_tokens_per_second`
- `decode_tokens_per_second`
- `request_p50_ms`
- `request_p95_ms`
- `speedup_vs_batch_1`
- `score_value`
- `incorrect_count`
- `parse_status`
