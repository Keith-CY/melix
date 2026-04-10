# Phase 1 Benchmark Matrix And Evaluation CLI/UI Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the Phase 1 baseline for `bench`, `bench matrix`, `eval`, and their export flows so the workflows are truthful, CLI-owned, accepted from both the public `melix` CLI and the Window UI diagnostics surfaces, and covered by positive and negative UT plus positive and negative E2E.

**Architecture:** Keep `MelixCLICore` as the single product-behavior source of truth. Tighten the existing CLI parser and runner plus the control-plane and worker live-evidence path first, then refactor the Window UI to depend on one command-running protocol: tests use `MelixCLIRunner` through the shared seam, while production uses a new `melix` subprocess runner that maps back to the same CLI contract.

**Tech Stack:** Swift, SwiftUI, Python, `MelixCLICore`, Swift Testing, pytest, repository integration harnesses under `tests/integration`, `make phase1-metrics`, changed-line coverage scripts under `scripts/`.

---

## Scope Guard

Phase 1 includes only the existing benchmark and evaluation product line:

- public CLI:
  - `melix bench run`
  - `melix bench list`
  - `melix bench export-csv`
  - `melix bench matrix run`
  - `melix bench matrix list`
  - `melix bench matrix export-summary-csv`
  - `melix bench matrix export-requests-csv`
  - `melix eval run`
  - `melix eval list`
  - `melix eval export-summary-csv`
  - `melix eval export-samples-csv`
  - `melix eval export-samples-jsonl`
- Window UI surfaces:
  - `Tools -> Diagnostics -> Benchmark`
  - `Tools -> Diagnostics -> Benchmark Matrix`
  - `Tools -> Diagnostics -> Evaluation`
- acceptance baseline model:
  - `mlx-community/Qwen3.5-0.8B-OptiQ-4bit`

Phase 1 does not add:

- independent comparison UI workflows
- independent release-gate UI workflows
- multimodal evaluation closure beyond existing baseline task-family handling
- executable code evaluation activation
- release-gate productization

## File Structure

### Contracts, Plans, And Runbooks

- Modify: `docs/benchmark-evaluation-contract.md`
- Modify: `docs/runbooks/m7-benchmark-and-evaluation-foundation.md`
- Modify: `docs/runbooks/benchmark-matrix-evaluation-and-lora.md`
- Modify: `docs/plans/2026-04-07-real-mlx-benchmark-and-evaluation.md`
- Modify: `progress.md`
- Modify: `task_plan.md`

### CLI Core

- Modify: `Sources/MelixCLICore/MelixCLI.swift`
- Test: `tests/MelixCLITests/MelixCLIParserTests.swift`
- Test: `tests/MelixCLITests/MelixCLIRunnerTests.swift`

### Swift Control Plane

- Modify: `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`
- Modify: `services/control-plane-swift/Sources/XPCService/ControlPlaneXPCClient.swift`
- Modify: `services/control-plane-swift/Sources/XPCService/BenchmarkExportBundle.swift`
- Test: `services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift`
- Test: `services/control-plane-swift/Tests/ControlPlaneTests/BenchmarkExportBundleTests.swift`

### Python Worker

- Modify: `services/mlx-worker-python/worker/engine/evaluation_core.py`
- Modify: `services/mlx-worker-python/worker/engine/maintenance_core.py`
- Modify: `services/mlx-worker-python/worker/productization/benchmark_export.py`
- Modify: `tests/integration/helpers.py`
- Add: `tests/integration/test_phase1_benchmark_eval_cli.py`
- Test: `services/mlx-worker-python/tests/test_evaluation_core.py`
- Test: `services/mlx-worker-python/tests/test_maintenance_service.py`
- Test: `services/mlx-worker-python/tests/test_benchmark_export.py`

### Window UI

- Add: `apps/macos-menubar/Sources/AppMain/Models/MelixOperatorCommandRunning.swift`
- Add: `apps/macos-menubar/Sources/AppMain/Models/MelixCLIProcessLaunching.swift`
- Add: `apps/macos-menubar/Sources/AppMain/Models/MelixCLISubprocessRunner.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/AppMain.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift`
- Add: `apps/macos-menubar/Tests/MenuBarTests/MelixCLISubprocessRunnerTests.swift`
- Add: `apps/macos-menubar/Tests/MenuBarTests/BenchmarkEvaluationWorkflowSmokeTests.swift`
- Modify: `apps/macos-menubar/Tests/MenuBarTests/AppMainBootstrapTests.swift`
- Modify: `apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift`
- Modify: `apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift`

## Performance Probes And Success Metrics

### Benchmark And Matrix Probes

- `bench.smoke.ttft_ms`
- `bench.smoke.tokens_per_second`
- `bench.latency.p50_ms`
- `bench.latency.p95_ms`
- `bench.summary.job_ms`
- `bench.matrix.summary.ttft_mean_ms`
- `bench.matrix.summary.throughput_requests_per_second`
- `bench.matrix.summary.throughput_tokens_per_second`
- `bench.matrix.summary.queue_wait_p95_ms`
- `bench.matrix.request.queue_wait_ms`
- `bench.matrix.request.peak_memory_bytes`

### Evaluation Probes

- `eval.mmlu.score_value`
- `eval.mmlu.correct_count`
- `eval.mmlu.incorrect_count`
- `eval.mmlu.duration_seconds`
- per-sample `time_s`
- per-sample `parse_status`
- live runtime evidence through loaded model handle and generated answer text

### UI And Operator Probes

- `menu.ops_bench_ms`
- `menu.ops_bench_matrix_ms`
- `menu.ops_eval_ms`
- `menu.bench_history_refresh_ms`
- `menu.bench_export_csv_ms`
- `menu.bench_matrix_history_refresh_ms`
- `menu.bench_matrix_export_summary_csv_ms`
- `menu.bench_matrix_export_requests_csv_ms`
- `menu.eval_history_refresh_ms`
- `menu.eval_export_csv_ms`
- `menu.eval_export_jsonl_ms`

### Phase Success Metrics

- standard benchmark, matrix benchmark, and evaluation runs persist live MLX-backed evidence instead of deterministic-only evidence where the product claims live execution
- CLI command parsing, normalization, rendering, and exports stay canonical across positive and negative cases
- the Window UI diagnostics surfaces no longer own a separate benchmark or evaluation behavior layer
- production UI launches the public `melix` executable as a subprocess for benchmark and evaluation operations
- tests use the same CLI workflow through the shared runner seam rather than a second ad-hoc path
- aggregate changed-line coverage for the touched executable scope is at least `95%`
- `make phase1-metrics PHASE1_METRICS_ARGS='--json'` completes and the phase handoff records the resulting report

## Task 1: Freeze The Phase 1 Contract, Acceptance Commands, And Phase Boundary

**Files:**
- Modify: `docs/benchmark-evaluation-contract.md`
- Modify: `docs/runbooks/m7-benchmark-and-evaluation-foundation.md`
- Modify: `docs/runbooks/benchmark-matrix-evaluation-and-lora.md`
- Modify: `docs/plans/2026-04-07-real-mlx-benchmark-and-evaluation.md`

- [ ] **Step 1: Record the designated text acceptance baseline and the exact Phase 1 UI surface boundary**

Add text equivalent to:

```md
Phase 1 acceptance model: `mlx-community/Qwen3.5-0.8B-OptiQ-4bit`
Phase 1 Window UI scope: `Tools -> Diagnostics -> Benchmark`, `Tools -> Diagnostics -> Benchmark Matrix`, and `Tools -> Diagnostics -> Evaluation`
Phase 1 excludes independent comparison and release-gate windows
```

- [ ] **Step 2: Record the canonical CLI acceptance commands in the runbooks**

Record `docs/runbooks/m7-benchmark-and-evaluation-foundation.md` as the single source of truth
for the exact positive command suite by referencing section
`Phase 1 Canonical CLI Acceptance Suite` instead of duplicating the command block.

- [ ] **Step 3: Record the negative acceptance commands in the runbooks**

Record `docs/runbooks/m7-benchmark-and-evaluation-foundation.md` as the single source of truth
for the exact negative command suite by referencing section
`Phase 1 Canonical CLI Acceptance Suite` instead of duplicating the command block.

- [ ] **Step 4: Verify the docs mention the designated baseline and reference the canonical acceptance-suite home**

Run:

```bash
rg -n "mlx-community/Qwen3.5-0.8B-OptiQ-4bit|Tools -> Diagnostics|Phase 1 Canonical CLI Acceptance Suite|docs/runbooks/m7-benchmark-and-evaluation-foundation.md" docs/benchmark-evaluation-contract.md docs/runbooks/m7-benchmark-and-evaluation-foundation.md docs/runbooks/benchmark-matrix-evaluation-and-lora.md docs/plans/2026-04-07-real-mlx-benchmark-and-evaluation.md
```

Expected:

- all four files contain the accepted baseline model
- cross-references to `Phase 1 Canonical CLI Acceptance Suite` and/or `docs/runbooks/m7-benchmark-and-evaluation-foundation.md` are present where commands are referenced
- only `docs/runbooks/m7-benchmark-and-evaluation-foundation.md` contains the exact positive/negative Phase 1 command suite

- [ ] **Step 5: Checkpoint commit**

```bash
git add docs/benchmark-evaluation-contract.md docs/runbooks/m7-benchmark-and-evaluation-foundation.md docs/runbooks/benchmark-matrix-evaluation-and-lora.md docs/plans/2026-04-07-real-mlx-benchmark-and-evaluation.md
git commit -m "docs: freeze phase1 bench eval acceptance contract"
```

## Task 2: Finish CLI Parser, Runner, And Export-Negative Coverage For The Existing Surface

**Files:**
- Modify: `Sources/MelixCLICore/MelixCLI.swift`
- Test: `tests/MelixCLITests/MelixCLIParserTests.swift`
- Test: `tests/MelixCLITests/MelixCLIRunnerTests.swift`
- Test: `services/control-plane-swift/Tests/ControlPlaneTests/BenchmarkExportBundleTests.swift`

- [ ] **Step 1: Add the missing positive CLI UT that lock the exact normalized contract**

Extend the parser and runner tests with cases shaped like:

```swift
@Test("bench run direct repo uses the designated acceptance model and canonical defaults")
func benchRunDirectRepoUsesAcceptanceModel() throws {
    let command = try MelixCLIParser.parse([
        "bench",
        "run",
        "--repo-id", "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
        "--suite", "smoke",
        "--json",
    ])

    guard case .benchRun(let options) = command else {
        Issue.record("Expected benchRun command")
        return
    }

    #expect(options.modelID.isEmpty)
    #expect(options.hfRepoID == "mlx-community/Qwen3.5-0.8B-OptiQ-4bit")
    #expect(options.suites == ["smoke"])
    #expect(options.json)
}

@Test("eval export-samples-jsonl returns plain-text path for the selected job")
func evalExportSamplesJSONLReturnsPath() async throws {
    let client = StubControlPlaneXPCClient()
    await client.setExportResult(.init(exportBundleJSON: makeBenchmarkExportBundleJSON()))
    let outputURL = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("phase1-eval-samples.jsonl")

    let output = try await MelixCLIRunner(client: client).run(
        .evalExportSamplesJSONL(.init(jobID: "eval-1", outputPath: outputURL.path))
    )

    #expect(output == outputURL.path + "\n")
}
```

Run:

```bash
HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --filter 'MelixCLIParserTests|MelixCLIRunnerTests'
```

Expected:

- the new tests fail before the implementation changes land

- [ ] **Step 2: Add the missing negative CLI UT for malformed export bundles and unavailable jobs**

Add failures shaped like:

```swift
@Test("bench list surfaces malformed export bundle decoding")
func benchListFailsForMalformedExportBundle() async throws {
    let client = StubControlPlaneXPCClient()
    await client.setExportResult(.init(exportBundleJSON: "{"))

    do {
        _ = try await MelixCLIRunner(client: client).run(.benchList(.init()))
        Issue.record("Expected malformed export bundle failure.")
    } catch let error as MelixCLIError {
        #expect(error.errorDescription?.contains("Malformed benchmark export bundle") == true)
    }
}

@Test("eval export-samples-jsonl fails when the requested job is missing")
func evalExportSamplesJSONLFailsForMissingJob() async throws {
    let client = StubControlPlaneXPCClient()
    await client.setExportResult(.init(exportBundleJSON: makeBenchmarkExportBundleJSON()))

    do {
        _ = try await MelixCLIRunner(client: client).run(
            .evalExportSamplesJSONL(.init(jobID: "eval-missing", outputPath: "/tmp/eval-missing.jsonl"))
        )
        Issue.record("Expected missing evaluation job failure.")
    } catch let error as MelixCLIError {
        #expect(error == .runtime("No evaluation rows were found for job eval-missing."))
    }
}
```

And extend export-bundle decoding coverage with a malformed matrix or evaluation payload case:

```swift
@Test("decode rejects malformed benchmark matrix export payloads")
func decodeRejectsMalformedBenchmarkMatrixExportPayloads() throws {
    #expect(throws: Error.self) {
        _ = try ControlPlaneBenchmarkExportBundle.decode(
            json: #"{"export_schema_version":"melix.benchmark_export.v1","benchmark_matrix_jobs":[{"job_id":"broken"}]}"#
        )
    }
}
```

- [ ] **Step 3: Update `MelixCLI.swift` so the public usage text, option parsing, and error mapping match the canonical surface**

Keep the CLI surface aligned with the tested contract:

```swift
melix eval run (--model-id MODEL_ID | --repo-id HF_REPO) [repeatable --suite SUITE] [--dataset-id DATASET_ID] [--dataset-root PATH] [--sample-size N] [--batch-factor N] [--seed N] [--few-shot N] [--scoring-mode MODE] [--code-exec-policy POLICY] [--json]
```

Make the runner error cases explicit:

```swift
throw MelixCLIError.runtime("No evaluation rows were found for job \(options.jobID).")
throw MelixCLIError.runtime("Malformed benchmark export bundle: \(error)")
```

- [ ] **Step 4: Re-run the focused CLI and export-bundle suites**

Run:

```bash
HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --filter 'MelixCLIParserTests|MelixCLIRunnerTests'
HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter BenchmarkExportBundleTests
```

Expected:

- parser and runner suites pass
- export bundle decoding suite passes

- [ ] **Step 5: Measure CLI changed-line coverage**

Run:

```bash
HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --enable-code-coverage --filter 'MelixCLIParserTests|MelixCLIRunnerTests'
CLI_TEST_BINARY="$(find .build -path '*PackageTests.xctest/Contents/MacOS/*PackageTests' | rg 'melix.*PackageTests$' -m 1)"
python3 scripts/swift_changed_line_coverage.py --binary "$CLI_TEST_BINARY" --profdata .build/arm64-apple-macosx/debug/codecov/default.profdata Sources/MelixCLICore/MelixCLI.swift tests/MelixCLITests/MelixCLIParserTests.swift tests/MelixCLITests/MelixCLIRunnerTests.swift
```

Expected:

- changed-line coverage for the touched CLI scope is at least `95%`

- [ ] **Step 6: Checkpoint commit**

```bash
git add Sources/MelixCLICore/MelixCLI.swift tests/MelixCLITests/MelixCLIParserTests.swift tests/MelixCLITests/MelixCLIRunnerTests.swift services/control-plane-swift/Tests/ControlPlaneTests/BenchmarkExportBundleTests.swift
git commit -m "test: close phase1 cli bench eval coverage"
```

## Task 3: Make The Control Plane And Worker Truthful For Live Benchmark, Matrix, And Evaluation Evidence

**Files:**
- Modify: `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`
- Modify: `services/control-plane-swift/Sources/XPCService/ControlPlaneXPCClient.swift`
- Modify: `services/mlx-worker-python/worker/engine/evaluation_core.py`
- Modify: `services/mlx-worker-python/worker/engine/maintenance_core.py`
- Modify: `services/mlx-worker-python/worker/productization/benchmark_export.py`
- Test: `services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift`
- Test: `apps/macos-menubar/Tests/MenuBarTests/ControlPlaneXPCClientTests.swift`
- Test: `services/mlx-worker-python/tests/test_evaluation_core.py`
- Test: `services/mlx-worker-python/tests/test_maintenance_service.py`
- Test: `services/mlx-worker-python/tests/test_benchmark_export.py`

- [ ] **Step 1: Add the failing positive and negative control-plane tests for direct repo resolution, live execution, and worker failure surfacing**

Add tests shaped like:

```swift
@Test("execute runs phase1 benchmark and evaluation requests through live worker-backed paths")
func executeRunsWorkerBackedPhase1Paths() async throws {
    let service = makeService()
    let benchResponse = try await execute(
        service,
        request: makeRunBenchRequest(hfRepoID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit")
    )
    let evaluationResponse = try await execute(
        service,
        request: makeRunEvaluationRequest(hfRepoID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit")
    )

    #expect(benchResponse.ops.benchmarkJob.jobID.isEmpty == false)
    #expect(evaluationResponse.ops.evaluationJob.jobID.isEmpty == false)
}

@Test("execute surfaces unsupported evaluation targets and worker failures for phase1")
func executeSurfacesPhase1EvaluationFailures() async throws {
    let service = makeService()
    let response = try await execute(
        service,
        request: makeRunEvaluationRequest(hfRepoID: "openai/non-mlx-model")
    )

    #expect(response.error.message.isEmpty == false)
}
```

Run:

```bash
HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter 'ControlPlaneServiceTests|ControlPlaneXPCClientTests'
```

Expected:

- the new service or client cases fail before the implementation changes land

- [ ] **Step 2: Add the failing positive and negative worker tests for live generation and honest export behavior**

Add Python coverage shaped like:

```python
def test_run_evaluation_uses_loaded_runtime_handle_and_generated_answer(tmp_path: Path) -> None:
    core = make_evaluation_core(tmp_path)
    result = core.run_evaluation(make_execution_context(tmp_path), make_evaluation_request())
    assert result["job"]["job_id"]
    assert result["results"][0]["samples"][0]["raw_response"]

def test_run_evaluation_raises_when_no_loaded_target_is_available(tmp_path: Path) -> None:
    core = make_evaluation_core(tmp_path)
    with pytest.raises(RuntimeError, match="No loaded evaluation target"):
        core.run_evaluation(make_missing_handle_context(tmp_path), make_evaluation_request())

def test_export_bundle_surfaces_missing_phase1_job_rows(tmp_path: Path) -> None:
    bundle = build_phase1_export_bundle(tmp_path)
    with pytest.raises(ValueError, match="No benchmark matrix summary rows were found"):
        bundle.benchmark_matrix_summary_csv(job_id="bench-matrix-missing")
```

Run:

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_evaluation_core.py services/mlx-worker-python/tests/test_maintenance_service.py services/mlx-worker-python/tests/test_benchmark_export.py -q
```

Expected:

- the new worker cases fail before the implementation changes land

- [ ] **Step 3: Update the control plane and worker so the product path uses live model handles, keeps direct repo resolution truthful, and preserves export semantics**

Keep the control-plane request path explicit:

```swift
let request = ControlPlaneEvaluationRequest(
    modelID: resolvedModelID,
    hfRepoID: resolvedRepoID,
    suiteID: suiteID,
    datasetID: datasetID,
    sampleSize: sampleSize,
    parameters: parameters
)
```

Make the worker execution path load from the execution context instead of a deterministic answer helper:

```python
prediction = self._runtime.generate_text(
    model_handle=execution_context.model_handle,
    prompt=rendered_prompt,
    parameters=parameters,
)
```

Keep export errors explicit rather than silent empty success:

```python
raise ValueError(f"No benchmark matrix summary rows were found for job {job_id}.")
```

- [ ] **Step 4: Re-run focused Swift and Python verification**

Run:

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_evaluation_core.py services/mlx-worker-python/tests/test_maintenance_service.py services/mlx-worker-python/tests/test_benchmark_export.py -q
HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter 'ControlPlaneServiceTests|BenchmarkExportBundleTests'
HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --filter ControlPlaneXPCClientTests
```

Expected:

- focused Swift and Python suites pass

- [ ] **Step 5: Measure Swift and Python changed-line coverage for the touched execution scope**

Run:

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" COVERAGE_FILE=/tmp/phase1_worker.coverage uv run --project services/mlx-worker-python coverage run -m pytest services/mlx-worker-python/tests/test_evaluation_core.py services/mlx-worker-python/tests/test_maintenance_service.py services/mlx-worker-python/tests/test_benchmark_export.py -q
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" COVERAGE_FILE=/tmp/phase1_worker.coverage uv run --project services/mlx-worker-python coverage json -o /tmp/phase1_worker_coverage.json
python3 scripts/python_changed_line_coverage.py --coverage-json /tmp/phase1_worker_coverage.json services/mlx-worker-python/worker/engine/evaluation_core.py services/mlx-worker-python/worker/engine/maintenance_core.py services/mlx-worker-python/worker/productization/benchmark_export.py services/mlx-worker-python/tests/test_evaluation_core.py services/mlx-worker-python/tests/test_maintenance_service.py services/mlx-worker-python/tests/test_benchmark_export.py
HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --enable-code-coverage --filter 'ControlPlaneServiceTests|BenchmarkExportBundleTests'
python3 scripts/swift_changed_line_coverage.py --binary services/control-plane-swift/.build/arm64-apple-macosx/debug/MelixControlPlanePackageTests.xctest/Contents/MacOS/MelixControlPlanePackageTests --profdata services/control-plane-swift/.build/arm64-apple-macosx/debug/codecov/default.profdata services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift services/control-plane-swift/Sources/XPCService/ControlPlaneXPCClient.swift services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift
```

Expected:

- Python touched-scope changed-line coverage is at least `95%`
- Swift control-plane touched-scope changed-line coverage is at least `95%`

- [ ] **Step 6: Checkpoint commit**

```bash
git add services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift services/control-plane-swift/Sources/XPCService/ControlPlaneXPCClient.swift services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift services/mlx-worker-python/worker/engine/evaluation_core.py services/mlx-worker-python/worker/engine/maintenance_core.py services/mlx-worker-python/worker/productization/benchmark_export.py services/mlx-worker-python/tests/test_evaluation_core.py services/mlx-worker-python/tests/test_maintenance_service.py services/mlx-worker-python/tests/test_benchmark_export.py apps/macos-menubar/Tests/MenuBarTests/ControlPlaneXPCClientTests.swift
git commit -m "feat: restore live phase1 bench eval evidence"
```

## Task 4: Add CLI Positive And Negative E2E Against The Live Local Stack

**Files:**
- Modify: `tests/integration/helpers.py`
- Add: `tests/integration/test_phase1_benchmark_eval_cli.py`
- Modify: `docs/runbooks/m7-benchmark-and-evaluation-foundation.md`

- [ ] **Step 1: Add CLI helper support to launch the built `melix` binary against `LiveMelixStack`**

Add helpers shaped like:

```python
def resolve_cli_binary(repo_root: Path) -> Path:
    return resolve_swift_product_binary(repo_root, package_path=Path("."), product_name="melix")

def run_melix_cli(repo_root: Path, args: list[str], environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
    cli_binary = resolve_cli_binary(repo_root)
    merged_env = os.environ.copy()
    merged_env.update(environment)
    return subprocess.run(
        [os.fspath(cli_binary), *args],
        cwd=repo_root,
        env=merged_env,
        text=True,
        capture_output=True,
        check=False,
    )
```

- [ ] **Step 2: Add positive CLI E2E coverage for benchmark, matrix, evaluation, and export**

Add a smoke test shaped like:

```python
def test_phase1_cli_smoke_covers_bench_matrix_eval_and_exports(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    stack = LiveMelixStack(repo_root, swift_backend_mode="auto", python_backend_mode="auto")
    try:
        stack.start()
        environment = stack.cli_environment(repo_root)

        # Resolve canonical positive vectors from the runbook reference, not this plan.
        bench = run_phase1_canonical_cli(repo_root, environment, case_id="bench_run_positive")
        matrix = run_phase1_canonical_cli(repo_root, environment, case_id="bench_matrix_run_positive")
        evaluation = run_phase1_canonical_cli(repo_root, environment, case_id="eval_run_positive")

        bench_history = json.loads(run_melix_cli(repo_root, ["bench", "list", "--json"], environment).stdout)
        matrix_history = json.loads(run_melix_cli(repo_root, ["bench", "matrix", "list", "--json"], environment).stdout)
        eval_history = json.loads(run_melix_cli(repo_root, ["eval", "list", "--json"], environment).stdout)

        bench_job_id = bench_history[0]["job_id"]
        matrix_job_id = matrix_history[0]["job_id"]
        eval_job_id = eval_history[0]["job_id"]

        bench_export = run_melix_cli(repo_root, ["bench", "export-csv", "--job-id", bench_job_id, "--output", os.fspath(tmp_path / "bench.csv"), "--json"], environment)
        matrix_export = run_melix_cli(repo_root, ["bench", "matrix", "export-summary-csv", "--job-id", matrix_job_id, "--output", os.fspath(tmp_path / "bench-matrix-summary.csv"), "--json"], environment)
        eval_export = run_melix_cli(repo_root, ["eval", "export-samples-jsonl", "--job-id", eval_job_id, "--output", os.fspath(tmp_path / "eval-samples.jsonl"), "--json"], environment)

        assert bench.returncode == 0
        assert matrix.returncode == 0
        assert evaluation.returncode == 0
        assert bench_export.returncode == 0
        assert matrix_export.returncode == 0
        assert eval_export.returncode == 0
    finally:
        stack.stop()
```

Use the canonical semantics defined by `docs/runbooks/m7-benchmark-and-evaluation-foundation.md`
under `Phase 1 Canonical CLI Acceptance Suite` for `bench run`, `bench matrix run`, and
`eval run`, then execute the list and export flows shown in the test body.
Do not inline the exact Phase 1 command vectors in this plan or test doc snippet.

- [ ] **Step 3: Add negative CLI E2E coverage for invalid load budget, unsupported targets, missing jobs, and worker failure surfacing**

Add tests shaped like:

```python
def test_phase1_cli_rejects_conflicting_matrix_load_budget(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    stack = LiveMelixStack(repo_root)
    try:
        stack.start()
        # Resolve canonical negative vector from the runbook reference, not this plan.
        result = run_phase1_canonical_cli(
            repo_root,
            stack.cli_environment(repo_root),
            case_id="bench_matrix_conflicting_load_budget_negative",
        )
        assert result.returncode != 0
        assert "Exactly one of --requests or --duration-seconds" in result.stderr + result.stdout
    finally:
        stack.stop()

def test_phase1_cli_surfaces_unsupported_evaluation_target(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    stack = LiveMelixStack(repo_root)
    try:
        stack.start()
        result = run_phase1_canonical_cli(
            repo_root,
            stack.cli_environment(repo_root),
            case_id="eval_run_unsupported_repo_negative",
        )
        assert result.returncode != 0
        assert "unsupported" in (result.stderr + result.stdout).lower()
    finally:
        stack.stop()

def test_phase1_cli_export_fails_for_missing_job(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    stack = LiveMelixStack(repo_root)
    try:
        stack.start()
        result = run_melix_cli(repo_root, ["eval", "export-summary-csv", "--job-id", "eval-missing", "--output", os.fspath(tmp_path / "missing.csv")], stack.cli_environment(repo_root))
        assert result.returncode != 0
        assert "No evaluation rows were found for job eval-missing." in result.stderr + result.stdout
    finally:
        stack.stop()
```

Use negative CLI commands aligned with the canonical suite in
`docs/runbooks/m7-benchmark-and-evaluation-foundation.md` under
`Phase 1 Canonical CLI Acceptance Suite` for invalid load budget and unsupported repo checks, plus
the missing-job export command shown in the test body.

- [ ] **Step 4: Run the new CLI E2E slice**

Run:

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python pytest tests/integration/test_phase1_benchmark_eval_cli.py -q
```

Expected:

- one positive smoke case passes
- negative cases fail for the right reasons before implementation and pass after implementation

- [ ] **Step 5: Build the release CLI and run the documented acceptance commands**

Run:

```bash
HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift build -c release --product melix
```

Then execute the exact positive commands from
`docs/runbooks/m7-benchmark-and-evaluation-foundation.md` under
`Phase 1 Canonical CLI Acceptance Suite`.

Expected:

- all three commands complete successfully
- each command prints JSON with a job ID or report payload

- [ ] **Step 6: Checkpoint commit**

```bash
git add tests/integration/helpers.py tests/integration/test_phase1_benchmark_eval_cli.py docs/runbooks/m7-benchmark-and-evaluation-foundation.md
git commit -m "test: add phase1 cli bench eval e2e coverage"
```

## Task 5: Introduce A Shared UI Command Protocol And A Production `melix` Subprocess Runner

**Files:**
- Add: `apps/macos-menubar/Sources/AppMain/Models/MelixOperatorCommandRunning.swift`
- Add: `apps/macos-menubar/Sources/AppMain/Models/MelixCLIProcessLaunching.swift`
- Add: `apps/macos-menubar/Sources/AppMain/Models/MelixCLISubprocessRunner.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/AppMain.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`
- Add: `apps/macos-menubar/Tests/MenuBarTests/MelixCLISubprocessRunnerTests.swift`
- Modify: `apps/macos-menubar/Tests/MenuBarTests/AppMainBootstrapTests.swift`

- [ ] **Step 1: Add the failing subprocess-runner UT for positive and negative process behavior**

Add tests shaped like:

```swift
@Test("subprocess runner maps benchmark commands to melix arguments and decodes JSON output")
func subprocessRunnerMapsBenchmarkCommands() async throws {
    let launcher = RecordingMelixCLIProcessLauncher(
        stdout: #"{"report_path":"/tmp/bench-report.md","report_markdown":"# Bench","metrics":{"bench.smoke.ttft_ms":24.45}}"#,
        stderr: "",
        exitStatus: 0
    )
    let runner = MelixCLISubprocessRunner(environment: ["MELIX_HOME": "/tmp/melix-home"], launcher: launcher)

    let result = try await runner.runBenchmark(
        .init(hfRepoID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit", suites: ["smoke"])
    )

    #expect(result.reportPath == "/tmp/bench-report.md")
    #expect(launcher.recordedArguments == phase1CanonicalCLIArguments(caseID: "bench_run_positive"))
}

@Test("subprocess runner surfaces non-zero exit status and stderr")
func subprocessRunnerSurfacesProcessFailure() async throws {
    let launcher = RecordingMelixCLIProcessLauncher(stdout: "", stderr: "benchmark exploded", exitStatus: 1)
    let runner = MelixCLISubprocessRunner(environment: [:], launcher: launcher)

    await #expect(throws: Error.self) {
        _ = try await runner.runBenchmark(
            .init(hfRepoID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit", suites: ["smoke"])
        )
    }
}
```

Run:

```bash
HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --filter 'MelixCLISubprocessRunnerTests|AppMainBootstrapTests'
```

Expected:

- the new tests fail before the new abstraction exists

- [ ] **Step 2: Add a protocol that both the seam runner and the subprocess runner can satisfy**

Create `MelixOperatorCommandRunning.swift` with a contract shaped like:

```swift
public protocol MelixOperatorCommandRunning: Sendable {
    func run(_ command: MelixCLICommand) async throws -> String
    func runBenchmark(_ options: BenchRunOptions) async throws -> ControlPlaneBenchResult
    func runBenchmarkMatrix(_ options: BenchMatrixRunOptions) async throws -> ControlPlaneBenchMatrixResult
    func runEvaluations(_ options: EvalRunOptions) async throws -> [ControlPlaneEvaluationResult]
    func fetchBenchmarkExportBundle(outputDir: String) async throws -> ControlPlaneBenchmarkExportBundle
}
```

- [ ] **Step 3: Add a process-launch abstraction and implement `MelixCLISubprocessRunner`**

Create the process-launch bridge with an injectable test double:

```swift
public protocol MelixCLIProcessLaunching: Sendable {
    func run(executable: String, arguments: [String], environment: [String: String]) async throws -> MelixCLIProcessResult
}
```

Map high-level UI calls into real CLI invocations:

```swift
["bench", "run", "--repo-id", repoID, "--suite", "smoke", "--json"]
["bench", "matrix", "export-summary-csv", "--job-id", jobID, "--output", outputPath, "--json"]
["eval", "export-samples-jsonl", "--job-id", jobID, "--output", outputPath, "--json"]
```

- [ ] **Step 4: Change `RuntimeViewModel` and `AppMain` to depend on the protocol, not directly on `MelixCLIRunner`**

Change the injected dependency shape to:

```swift
private let operatorCommandRunner: (any MelixOperatorCommandRunning)?
```

Make live bootstrap use the subprocess runner by default:

```swift
let resolvedOperatorCommandRunner = operatorCommandRunner ?? MelixCLISubprocessRunner(
    environment: ProcessInfo.processInfo.environment
)
```

Keep tests on the seam:

```swift
let runner = MelixCLIRunner(
    client: runnerClient,
    environment: ["MELIX_HOME": temporaryRoot.path],
    operatorSessionStore: MelixOperatorSessionStore(
        melixHome: MelixHome(environment: ["MELIX_HOME": temporaryRoot.path])
    )
)
```

- [ ] **Step 5: Re-run the focused subprocess and bootstrap suites**

Run:

```bash
HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --filter 'MelixCLISubprocessRunnerTests|AppMainBootstrapTests|RuntimeViewModelTests'
```

Expected:

- the new subprocess runner tests pass
- `AppMainBootstrapTests` proves live bootstrap now chooses the subprocess runner path by default

- [ ] **Step 6: Checkpoint commit**

```bash
git add apps/macos-menubar/Sources/AppMain/Models/MelixOperatorCommandRunning.swift apps/macos-menubar/Sources/AppMain/Models/MelixCLIProcessLaunching.swift apps/macos-menubar/Sources/AppMain/Models/MelixCLISubprocessRunner.swift apps/macos-menubar/Sources/AppMain/AppMain.swift apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift apps/macos-menubar/Tests/MenuBarTests/MelixCLISubprocessRunnerTests.swift apps/macos-menubar/Tests/MenuBarTests/AppMainBootstrapTests.swift
git commit -m "feat: route menubar bench eval through melix subprocess"
```

## Task 6: Close Window UI Positive And Negative UT, Seam-Backed E2E, And Production Subprocess Proof

**Files:**
- Modify: `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift`
- Modify: `apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift`
- Modify: `apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift`
- Add: `apps/macos-menubar/Tests/MenuBarTests/BenchmarkEvaluationWorkflowSmokeTests.swift`
- Modify: `docs/runbooks/benchmark-matrix-evaluation-and-lora.md`

- [ ] **Step 1: Add the missing positive and negative RuntimeViewModel UT for subprocess failures and malformed CLI output**

Add tests shaped like:

```swift
@Test("benchmark evaluation diagnostics rebuild state from subprocess-backed cli output")
func diagnosticsRebuildStateFromSubprocessOutput() async throws {
    let runner = makeRecordingSubprocessRunnerSuccess()
    let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient(), operatorCommandRunner: runner)
    await viewModel.start()
    await viewModel.runBench()
    await viewModel.runBenchMatrix()
    await viewModel.runEvaluation()
    #expect(viewModel.lastBenchReport != nil)
    #expect(viewModel.benchmarkMatrixHistory.isEmpty == false)
    #expect(viewModel.evaluationHistory.isEmpty == false)
}

@Test("benchmark evaluation diagnostics surface subprocess launch and decode failures")
func diagnosticsSurfaceSubprocessFailures() async throws {
    let runner = makeRecordingSubprocessRunnerFailure(message: "benchmark exploded")
    let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient(), operatorCommandRunner: runner)
    await viewModel.start()
    await viewModel.runBench()
    #expect(viewModel.lastError?.contains("benchmark exploded") == true)
}
```

Run:

```bash
HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --filter RuntimeViewModelTests
```

Expected:

- the new positive and negative cases fail before the view-model adjustments land

- [ ] **Step 2: Add the missing positive and negative view-render UT for Diagnostics benchmark and evaluation controls**

Add tests shaped like:

```swift
@Test("workspace diagnostics renders phase1 benchmark matrix and evaluation subprocess states")
func workspaceDiagnosticsRendersPhase1States() async throws {
    let viewModel = makeBenchmarkEvalDiagnosticsViewModel()
    let view = hostView(DesktopWorkspaceShellView(viewModel: viewModel))
    let renderedTexts = renderedTextValues(in: view)
    #expect(view.subviews.isEmpty == false)
    #expect(renderedTexts.contains("Tools -> Diagnostics -> Benchmark"))
    #expect(renderedTexts.contains("Tools -> Diagnostics -> Benchmark Matrix"))
    #expect(renderedTexts.contains("Tools -> Diagnostics -> Evaluation"))
}

@Test("workspace diagnostics renders phase1 benchmark and evaluation failure banners")
func workspaceDiagnosticsRendersPhase1Failures() async throws {
    let viewModel = makeBenchmarkEvalFailureViewModel()
    let view = hostView(DesktopWorkspaceShellView(viewModel: viewModel))
    let renderedTexts = renderedTextValues(in: view)
    #expect(view.subviews.isEmpty == false)
    #expect(renderedTexts.contains("benchmark exploded"))
}
```

- [ ] **Step 3: Add a seam-backed UI E2E smoke suite that drives the real diagnostics workflow from the hosted Window UI**

Create `BenchmarkEvaluationWorkflowSmokeTests.swift` with one positive and one negative flow shaped like:

```swift
@Suite("Benchmark Evaluation Workflow Smoke", .serialized)
struct BenchmarkEvaluationWorkflowSmokeTests {
    @Test("diagnostics benchmark matrix evaluation workflow succeeds through the shared cli seam")
    @MainActor
    func diagnosticsWorkflowSucceeds() async throws {
        let viewModel = makeBenchmarkEvalWorkflowViewModel()
        await viewModel.start()
        viewModel.selectSurface(.tools)
        viewModel.selectToolSection(.diagnostics)
        await viewModel.runBench()
        await viewModel.runBenchMatrix()
        await viewModel.runEvaluation()
        await viewModel.exportSelectedBenchmarkCSV()
        await viewModel.exportSelectedBenchmarkMatrixSummaryCSV()
        await viewModel.exportSelectedEvaluationSamplesJSONL()
        #expect(viewModel.lastBenchmarkCSVExport != nil)
        #expect(viewModel.lastBenchmarkMatrixExport != nil)
        #expect(viewModel.lastEvaluationExport != nil)
    }

    @Test("diagnostics benchmark matrix evaluation workflow renders negative cli states")
    @MainActor
    func diagnosticsWorkflowRendersFailures() async throws {
        let viewModel = makeBenchmarkEvalFailureWorkflowViewModel()
        await viewModel.start()
        viewModel.selectSurface(.tools)
        viewModel.selectToolSection(.diagnostics)
        await viewModel.runBenchMatrix()
        await viewModel.exportSelectedEvaluationSamplesJSONL()
        #expect(viewModel.lastError?.isEmpty == false)
    }
}
```

The positive flow must:

- host `DesktopWorkspaceShellView`
- select `Tools -> Diagnostics -> Benchmark`
- run `Tools -> Diagnostics -> Benchmark`
- run `Tools -> Diagnostics -> Benchmark Matrix`
- run `Tools -> Diagnostics -> Evaluation`
- export benchmark CSV
- export matrix summary CSV
- export evaluation samples JSONL
- assert history, charts, sample previews, and written files

The negative flow must:

- block an invalid matrix load-budget combination
- inject a CLI failure
- inject a malformed export or decode failure
- assert the failure text is visible in the diagnostics surface

- [ ] **Step 4: Add one production-mode subprocess proof**

Add a test that uses `MelixCLISubprocessRunner` with a recording process launcher and asserts:

```swift
#expect(recordedArguments == phase1CanonicalCLIArguments(caseID: "bench_run_positive"))
#expect(viewModel.lastError == "melix subprocess failed: benchmark exploded")
```

This proof must cover:

- one successful subprocess invocation
- one failing subprocess invocation with non-zero exit

- [ ] **Step 5: Run the focused Window UI suites**

Run:

```bash
HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --filter 'RuntimeViewModelTests|DesktopFoundationViewTests|BenchmarkEvaluationWorkflowSmokeTests|MelixCLISubprocessRunnerTests|AppMainBootstrapTests'
```

Expected:

- positive UT pass
- negative UT pass
- seam-backed positive and negative Window UI E2E pass
- subprocess proof passes

- [ ] **Step 6: Measure Window UI changed-line coverage**

Run:

```bash
HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --enable-code-coverage --filter 'RuntimeViewModelTests|DesktopFoundationViewTests|BenchmarkEvaluationWorkflowSmokeTests|MelixCLISubprocessRunnerTests|AppMainBootstrapTests'
python3 scripts/swift_changed_line_coverage.py --binary apps/macos-menubar/.build/arm64-apple-macosx/debug/MelixMacOSMenubarPackageTests.xctest/Contents/MacOS/MelixMacOSMenubarPackageTests --profdata apps/macos-menubar/.build/arm64-apple-macosx/debug/codecov/default.profdata apps/macos-menubar/Sources/AppMain/AppMain.swift apps/macos-menubar/Sources/AppMain/Models/MelixOperatorCommandRunning.swift apps/macos-menubar/Sources/AppMain/Models/MelixCLIProcessLaunching.swift apps/macos-menubar/Sources/AppMain/Models/MelixCLISubprocessRunner.swift apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift apps/macos-menubar/Tests/MenuBarTests/AppMainBootstrapTests.swift apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift apps/macos-menubar/Tests/MenuBarTests/MelixCLISubprocessRunnerTests.swift apps/macos-menubar/Tests/MenuBarTests/BenchmarkEvaluationWorkflowSmokeTests.swift
```

Expected:

- Window UI touched-scope changed-line coverage is at least `95%`

- [ ] **Step 7: Run Window UI acceptance on the documented diagnostics workflow**

Run:

```bash
HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift build --package-path apps/macos-menubar
```

Then validate the diagnostics workflow recorded in the runbook:

- open the Window UI
- navigate to `Tools -> Diagnostics -> Benchmark`
- run `Tools -> Diagnostics -> Benchmark` against `mlx-community/Qwen3.5-0.8B-OptiQ-4bit`
- run `Tools -> Diagnostics -> Benchmark Matrix` against `mlx-community/Qwen3.5-0.8B-OptiQ-4bit`
- run `Tools -> Diagnostics -> Evaluation` against `mlx-community/Qwen3.5-0.8B-OptiQ-4bit`
- export benchmark CSV, matrix summary CSV, and evaluation samples JSONL
- verify one failing matrix command and one failing export state render a visible error

- [ ] **Step 8: Checkpoint commit**

```bash
git add apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift apps/macos-menubar/Tests/MenuBarTests/BenchmarkEvaluationWorkflowSmokeTests.swift docs/runbooks/benchmark-matrix-evaluation-and-lora.md
git commit -m "test: add phase1 window bench eval acceptance coverage"
```

## Task 7: Final Verification, Metrics, Progress Recording, And Phase Handoff

**Files:**
- Modify: `progress.md`
- Modify: `task_plan.md`

- [ ] **Step 1: Run the full focused verification stack for Phase 1**

Run:

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_evaluation_core.py services/mlx-worker-python/tests/test_maintenance_service.py services/mlx-worker-python/tests/test_benchmark_export.py tests/integration/test_phase1_benchmark_eval_cli.py -q
HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --filter 'MelixCLIParserTests|MelixCLIRunnerTests'
HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter 'ControlPlaneServiceTests|BenchmarkExportBundleTests'
HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --filter 'RuntimeViewModelTests|DesktopFoundationViewTests|BenchmarkEvaluationWorkflowSmokeTests|MelixCLISubprocessRunnerTests|AppMainBootstrapTests|ControlPlaneXPCClientTests'
make integration-test
```

Expected:

- all focused phase tests pass
- `make integration-test` passes or any pre-existing unrelated failure is recorded explicitly in `progress.md`

- [ ] **Step 2: Run the repository metrics report for Phase 1**

Run:

```bash
bash scripts/dev_up.sh
make phase1-metrics PHASE1_METRICS_ARGS='--json'
```

Expected:

- `bash scripts/dev_up.sh` materializes the runtime env file consumed by the metrics script
- the JSON report includes direct worker and HTTP path measurements for the running Phase 1 stack

- [ ] **Step 3: Record verification, acceptance, coverage, and metrics in `progress.md` and `task_plan.md`**

Record at minimum:

- CLI positive UT status
- CLI negative UT status
- CLI positive E2E status
- CLI negative E2E status
- Window UI positive UT status
- Window UI negative UT status
- Window UI positive E2E status
- Window UI negative E2E status
- CLI acceptance command results
- Window UI acceptance results
- changed-line coverage percentages for CLI, control-plane, worker, and Window UI scope
- `make phase1-metrics` output or the exact path to the captured JSON payload

- [ ] **Step 4: Confirm the phase gate is closed**

Run:

```bash
git diff --check
git status --short
```

Expected:

- no whitespace or merge-marker issues
- only intended phase files remain changed

- [ ] **Step 5: Squash merge the phase into local `main` and refresh the base**

Run:

```bash
git switch main
git merge --squash codex/phase1-benchmark-matrix-eval-closure
git commit -m "feat: close phase1 benchmark matrix evaluation cli ui"
git status --short
git rev-parse --abbrev-ref HEAD
git rebase main
```

Expected:

- local `main` contains one squash-merged Phase 1 commit
- the next phase starts from refreshed local `main`

- [ ] **Step 6: Open the next-phase preparation note**

Add a short handoff note to `task_plan.md` with:

```md
Phase 1 closed on local `main` via squash merge.
Next base: refreshed local `main`.
Next implementation entry point: Phase 2 multimodal evaluation and VLM benchmark closure.
```

## Final Acceptance Checklist

- [ ] CLI positive UT passed
- [ ] CLI negative UT passed
- [ ] CLI positive E2E passed
- [ ] CLI negative E2E passed
- [ ] Window UI positive UT passed
- [ ] Window UI negative UT passed
- [ ] Window UI positive E2E passed
- [ ] Window UI negative E2E passed
- [ ] CLI acceptance passed against `mlx-community/Qwen3.5-0.8B-OptiQ-4bit`
- [ ] Window UI acceptance passed on the diagnostics benchmark, matrix, and evaluation surfaces
- [ ] `make phase1-metrics PHASE1_METRICS_ARGS='--json'` captured and recorded
- [ ] aggregate changed-line coverage for touched executable scope is at least `95%`
- [ ] phase changes recorded in `progress.md`
- [ ] phase changes squash-merged into local `main`
