# M7.3-M7.5 Benchmark And Evaluation Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land serving benchmark runners, offline dataset packaging, and the first evaluation execution path so M7 stops at a real executable platform instead of schema-only groundwork.

**Architecture:** Keep execution and persistence in the Python model-operations worker, use the control plane only for orchestration and typed reply shaping, and keep the desktop surface thin. Reuse the newly landed M7.1-M7.2 benchmark and evaluation schema messages rather than inventing a parallel result model.

**Tech Stack:** Python worker productization layer, Swift control-plane XPC service, versioned protobuf schemas, file-backed manifests and JSON artifacts, pytest, Swift Testing.

---

### Task 1: Add Benchmark And Evaluation Persistence Primitives

**Files:**
- Create: `services/mlx-worker-python/worker/productization/evaluation_schemas.py`
- Create: `services/mlx-worker-python/tests/test_evaluation_schemas.py`
- Modify: `services/mlx-worker-python/worker/productization/__init__.py`
- Modify: `services/mlx-worker-python/worker/productization/benchmark_schemas.py`

- [ ] **Step 1: Write the failing schema tests**

```python
from worker.productization.evaluation_schemas import (
    build_dataset_package_manifest,
    build_evaluation_job_record,
    build_evaluation_result_record,
)


def test_build_dataset_package_manifest_preserves_dataset_identity() -> None:
    manifest = build_dataset_package_manifest(
        dataset_id="mmlu-dev",
        suite_id="mmlu",
        version="2026-03-31",
        sample_count=2,
        split="validation",
    )
    payload = manifest.to_dict()

    assert payload["schema_version"] == "melix.evaluation_dataset_package.v1"
    assert payload["dataset_id"] == "mmlu-dev"
    assert payload["suite_id"] == "mmlu"
    assert payload["sample_count"] == 2
    assert payload["split"] == "validation"


def test_build_evaluation_result_record_orders_metrics_stably() -> None:
    result = build_evaluation_result_record(
        job_id="eval-1",
        suite_id="mmlu",
        dataset_id="mmlu-dev",
        sample_size=8,
        metrics={"eval.mmlu.accuracy": 0.75, "eval.mmlu.loss": 0.25},
        report_path="/tmp/mmlu.json",
    )

    assert [row["name"] for row in result.to_dict()["metrics"]] == [
        "eval.mmlu.accuracy",
        "eval.mmlu.loss",
    ]
```

- [ ] **Step 2: Run the schema tests to verify they fail**

Run:

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" \
uv run --project services/mlx-worker-python pytest \
  services/mlx-worker-python/tests/test_evaluation_schemas.py
```

Expected: `ModuleNotFoundError` or missing symbol failures for `evaluation_schemas`.

- [ ] **Step 3: Implement the minimal schema layer**

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class EvaluationDatasetPackageManifest:
    schema_version: str
    dataset_id: str
    suite_id: str
    version: str
    sample_count: int
    split: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "dataset_id": self.dataset_id,
            "suite_id": self.suite_id,
            "version": self.version,
            "sample_count": self.sample_count,
            "split": self.split,
        }


def build_dataset_package_manifest(
    *, dataset_id: str, suite_id: str, version: str, sample_count: int, split: str
) -> EvaluationDatasetPackageManifest:
    return EvaluationDatasetPackageManifest(
        schema_version="melix.evaluation_dataset_package.v1",
        dataset_id=dataset_id,
        suite_id=suite_id,
        version=version,
        sample_count=sample_count,
        split=split,
    )
```

- [ ] **Step 4: Re-export the new schema helpers**

```python
from worker.productization.evaluation_schemas import (
    EvaluationDatasetPackageManifest,
    build_dataset_package_manifest,
    build_evaluation_job_record,
    build_evaluation_result_record,
)
```

- [ ] **Step 5: Run the schema tests to verify they pass**

Run:

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" \
uv run --project services/mlx-worker-python pytest \
  services/mlx-worker-python/tests/test_evaluation_schemas.py
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add \
  services/mlx-worker-python/worker/productization/evaluation_schemas.py \
  services/mlx-worker-python/worker/productization/__init__.py \
  services/mlx-worker-python/tests/test_evaluation_schemas.py
git commit -m "feat: add evaluation schema helpers"
```

### Task 2: Persist Serving Benchmark Jobs And Results From The Worker Runner

**Files:**
- Create: `services/mlx-worker-python/worker/productization/benchmark_store.py`
- Create: `services/mlx-worker-python/tests/test_benchmark_store.py`
- Modify: `services/mlx-worker-python/worker/engine/maintenance_core.py`
- Modify: `services/mlx-worker-python/tests/test_maintenance_service.py`

- [ ] **Step 1: Write the failing persistence test**

```python
def test_run_bench_persists_job_manifest_and_per_suite_results(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    events = list(
        service.RunBench(
            maintenance_pb2.RunBenchRequest(
                model_handle="melix-dev-text::1",
                suites=["smoke", "latency"],
            ),
            context=None,
        )
    )

    report_path = Path(events[-1].completed.report_path)
    job_manifest = report_path.with_name("bench-job.json")
    smoke_result = report_path.with_name("bench-result-smoke.json")
    latency_result = report_path.with_name("bench-result-latency.json")

    assert job_manifest.exists() is True
    assert smoke_result.exists() is True
    assert latency_result.exists() is True
```

- [ ] **Step 2: Run the benchmark persistence test to verify it fails**

Run:

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" \
uv run --project services/mlx-worker-python pytest \
  services/mlx-worker-python/tests/test_maintenance_service.py -k persist
```

Expected: FAIL because the benchmark job and result artifacts are not persisted yet.

- [ ] **Step 3: Add a file-backed benchmark store**

```python
class BenchmarkStore:
    def persist_serving_benchmark(
        self,
        *,
        jobs_root: Path,
        job: ServingBenchmarkJob,
        results: tuple[ServingBenchmarkResult, ...],
    ) -> dict[str, Path]:
        jobs_root.mkdir(parents=True, exist_ok=True)
        job_path = jobs_root / "bench-job.json"
        job_path.write_text(json.dumps(job.to_dict(), indent=2) + "\n", encoding="utf-8")
        result_paths: dict[str, Path] = {}
        for result in results:
            path = jobs_root / f"bench-result-{result.suite}.json"
            path.write_text(json.dumps(result.to_dict(), indent=2) + "\n", encoding="utf-8")
            result_paths[result.suite] = path
        return {"job": job_path, **result_paths}
```

- [ ] **Step 4: Wire `MaintenanceCore.bench_events()` to persist job and results**

```python
job_record = build_serving_benchmark_job(
    job_id=job.job_id,
    model_id=request.model_handle.split("::", 1)[0],
    suites=tuple(suites),
    parameters={},
    status="completed",
    output_dir=str(output_dir),
)
result_records = build_serving_benchmark_results(
    job_id=job.job_id,
    metrics={metric.name: metric.value for metric in metrics},
    units={metric.name: metric.unit for metric in metrics},
    report_path=str(report_path),
    report_markdown=report_path.read_text(encoding="utf-8"),
)
benchmark_store.persist_serving_benchmark(
    jobs_root=output_dir,
    job=job_record,
    results=result_records,
)
```

- [ ] **Step 5: Re-run the worker benchmark tests**

Run:

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" \
uv run --project services/mlx-worker-python pytest \
  services/mlx-worker-python/tests/test_maintenance_service.py \
  services/mlx-worker-python/tests/test_benchmark_store.py
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add \
  services/mlx-worker-python/worker/productization/benchmark_store.py \
  services/mlx-worker-python/tests/test_benchmark_store.py \
  services/mlx-worker-python/worker/engine/maintenance_core.py \
  services/mlx-worker-python/tests/test_maintenance_service.py
git commit -m "feat: persist serving benchmark artifacts"
```

### Task 3: Add Offline Evaluation Dataset Packaging And A Minimal Evaluation Runner

**Files:**
- Create: `services/mlx-worker-python/worker/productization/evaluation_store.py`
- Create: `services/mlx-worker-python/worker/engine/evaluation_core.py`
- Create: `services/mlx-worker-python/tests/test_evaluation_store.py`
- Create: `services/mlx-worker-python/tests/test_evaluation_core.py`
- Modify: `services/mlx-worker-python/worker/grpc_server.py`

- [ ] **Step 1: Write the failing dataset package and runner tests**

```python
def test_evaluation_runner_executes_packaged_dataset_and_persists_result(tmp_path: Path) -> None:
    dataset_root = tmp_path / "datasets" / "mmlu-dev"
    dataset_root.mkdir(parents=True)
    (dataset_root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "melix.evaluation_dataset_package.v1",
                "dataset_id": "mmlu-dev",
                "suite_id": "mmlu",
                "version": "2026-03-31",
                "sample_count": 2,
                "split": "validation",
            }
        ) + "\n",
        encoding="utf-8",
    )
    (dataset_root / "samples.jsonl").write_text(
        "\n".join([
            json.dumps({"prompt": "2+2?", "expected": "4"}),
            json.dumps({"prompt": "3+3?", "expected": "6"}),
        ]) + "\n",
        encoding="utf-8",
    )

    runner = EvaluationCore()
    result = runner.run_local_suite(
        model_id="melix-dev-text",
        suite_id="mmlu",
        dataset_root=dataset_root,
        sample_size=2,
    )

    assert result.metrics["eval.mmlu.accuracy"] == 1.0
```

- [ ] **Step 2: Run the evaluation tests to verify they fail**

Run:

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" \
uv run --project services/mlx-worker-python pytest \
  services/mlx-worker-python/tests/test_evaluation_store.py \
  services/mlx-worker-python/tests/test_evaluation_core.py
```

Expected: FAIL because the evaluation store and runner do not exist.

- [ ] **Step 3: Implement a minimal deterministic evaluation runner**

```python
class EvaluationCore:
    def run_local_suite(
        self,
        *,
        model_id: str,
        suite_id: str,
        dataset_root: Path,
        sample_size: int,
    ) -> EvaluationResult:
        manifest = json.loads((dataset_root / "manifest.json").read_text(encoding="utf-8"))
        samples = [json.loads(line) for line in (dataset_root / "samples.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        selected = samples[:sample_size]
        correct = sum(1 for sample in selected if self._sample_is_correct(sample))
        accuracy = correct / max(len(selected), 1)
        return build_evaluation_result_record(
            job_id="eval-local",
            suite_id=suite_id,
            dataset_id=manifest["dataset_id"],
            sample_size=len(selected),
            metrics={"eval.mmlu.accuracy": round(accuracy, 2)},
            report_path=str(dataset_root / "result.json"),
        )
```

- [ ] **Step 4: Persist the evaluation job and result**

```python
class EvaluationStore:
    def persist_result(
        self,
        *,
        jobs_root: Path,
        job: EvaluationJob,
        result: EvaluationResult,
    ) -> dict[str, Path]:
        jobs_root.mkdir(parents=True, exist_ok=True)
        job_path = jobs_root / "evaluation-job.json"
        result_path = jobs_root / "evaluation-result.json"
        job_path.write_text(json.dumps(job.to_dict(), indent=2) + "\n", encoding="utf-8")
        result_path.write_text(json.dumps(result.to_dict(), indent=2) + "\n", encoding="utf-8")
        return {"job": job_path, "result": result_path}
```

- [ ] **Step 5: Re-run the evaluation tests**

Run:

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" \
uv run --project services/mlx-worker-python pytest \
  services/mlx-worker-python/tests/test_evaluation_store.py \
  services/mlx-worker-python/tests/test_evaluation_core.py
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add \
  services/mlx-worker-python/worker/productization/evaluation_store.py \
  services/mlx-worker-python/worker/engine/evaluation_core.py \
  services/mlx-worker-python/tests/test_evaluation_store.py \
  services/mlx-worker-python/tests/test_evaluation_core.py \
  services/mlx-worker-python/worker/grpc_server.py
git commit -m "feat: add offline evaluation runner foundation"
```

### Task 4: Add A Minimal Control-Plane Evaluation Command And Typed Reply Surface

**Files:**
- Modify: `packages/protocol/schema/controlplane/v1/control_plane.proto`
- Regenerate: `packages/protocol/swift/controlplane/v1/control_plane.pb.swift`
- Regenerate: `packages/protocol/python/controlplane/v1/control_plane_pb2.py`
- Regenerate: `packages/protocol/descriptors/melix.pb`
- Modify: `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`
- Modify: `services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift`

- [ ] **Step 1: Write the failing Swift control-plane test**

```swift
@Test("execute handles ops.run_evaluation through the model-operations worker")
func executeHandlesOpsRunEvaluationThroughTheModelOperationsWorker() async throws {
    let service = ControlPlaneService(
        modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()),
        workerRegistry: WorkerRegistry(
            defaultTextClient: NullWorkerClient(),
            modelOperationsClient: modelOpsClient
        )
    )

    let response = try await service.execute(makeRunEvaluationRequest())

    #expect(response.ok)
    #expect(response.ops.evaluationJob.schemaVersion == "melix.evaluation_job.v1")
    #expect(response.ops.evaluationResults.count == 1)
}
```

- [ ] **Step 2: Run the Swift test to verify it fails**

Run:

```bash
make proto
HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" \
swift test --package-path services/control-plane-swift \
  --scratch-path /tmp/melix-control-plane-m7-3-5-test \
  --filter 'ControlPlaneServiceTests/executeHandlesOpsRunEvaluationThroughTheModelOperationsWorker'
```

Expected: FAIL because the control-plane command and reply fields do not exist yet.

- [ ] **Step 3: Add the minimal protocol messages and command shape**

```proto
message RunEvaluation {
  string suite_id = 1;
  string dataset_id = 2;
  uint32 sample_size = 3;
  map<string, string> parameters = 4;
}
```

```proto
message OpsCommand {
  oneof kind {
    TailLogs tail_logs = 1;
    RunDoctor run_doctor = 2;
    RunBench run_bench = 3;
    RunEvaluation run_evaluation = 4;
    ExportDiagnostics export_bundle = 5;
    GetMetricsSnapshot get_metrics = 6;
    CancelRequest cancel_request = 7;
  }
}
```

- [ ] **Step 4: Add the minimal control-plane translation path**

```swift
case .runEvaluation(let runEvaluation):
    return await handleRunEvaluation(request: request, command: runEvaluation)
```

```swift
private func handleRunEvaluation(
    request: Melix_Controlplane_V1_ControlPlaneRequest,
    command: Melix_Controlplane_V1_RunEvaluation
) async -> Melix_Controlplane_V1_ControlPlaneResponse {
    guard let workerClient = modelOperationsClient() else {
        return errorResponse(for: request, code: "unavailable", message: "Model operations worker is unavailable.")
    }

    var workerRequest = Melix_Worker_V1_RunEvaluationRequest()
    workerRequest.suiteID = command.suiteID
    workerRequest.datasetID = command.datasetID
    workerRequest.sampleSize = command.sampleSize
    workerRequest.parameters = command.parameters

    do {
        let workerResponse = try await workerClient.runEvaluation(request: workerRequest)
        var reply = Melix_Controlplane_V1_OpsReply()
        reply.evaluationJob = makeEvaluationJobSummary(from: workerResponse.job)
        reply.evaluationResults = workerResponse.results.map(makeEvaluationResultSummary)
        return okResponse(for: request, ops: reply)
    } catch {
        return errorResponse(for: request, code: "unavailable", message: "Evaluation worker request failed: \\(error)")
    }
}
```

- [ ] **Step 5: Re-run the proto and Swift tests**

Run:

```bash
make proto
HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" \
swift test --package-path services/control-plane-swift \
  --scratch-path /tmp/melix-control-plane-m7-3-5-test \
  --filter 'ControlPlaneServiceTests/executeHandlesOpsRunEvaluationThroughTheModelOperationsWorker'
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add \
  packages/protocol/schema/controlplane/v1/control_plane.proto \
  packages/protocol/swift/controlplane/v1/control_plane.pb.swift \
  packages/protocol/python/controlplane/v1/control_plane_pb2.py \
  packages/protocol/descriptors/melix.pb \
  services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift \
  services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift
git commit -m "feat: add control-plane evaluation command"
```

### Task 5: Add Runbooks And End-To-End Verification For M7.3-M7.5

**Files:**
- Create: `docs/runbooks/m7-benchmark-and-evaluation-foundation.md`
- Modify: `docs/runbooks/README.md`
- Modify: `docs/README.md`

- [ ] **Step 1: Write the failing documentation-aware tests if the repo has them**

If no documentation tests exist, skip this step and proceed directly to the runbook content.

- [ ] **Step 2: Write the runbook with exact commands**

```markdown
# M7 Benchmark And Evaluation Foundation

## Commands

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" \
uv run --project services/mlx-worker-python pytest \
  services/mlx-worker-python/tests/test_benchmark_schemas.py \
  services/mlx-worker-python/tests/test_release_gates.py \
  services/mlx-worker-python/tests/test_evaluation_schemas.py \
  services/mlx-worker-python/tests/test_evaluation_core.py
```
```

- [ ] **Step 3: Run the final touched-scope verification**

Run:

```bash
make proto
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" \
uv run --project services/mlx-worker-python pytest \
  services/mlx-worker-python/tests/test_benchmark_schemas.py \
  services/mlx-worker-python/tests/test_benchmark_store.py \
  services/mlx-worker-python/tests/test_release_gates.py \
  services/mlx-worker-python/tests/test_evaluation_schemas.py \
  services/mlx-worker-python/tests/test_evaluation_core.py \
  services/mlx-worker-python/tests/test_maintenance_service.py
```

Expected: PASS

- [ ] **Step 4: Record touched-scope coverage**

Run:

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" \
uv run --project services/mlx-worker-python coverage erase
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" \
uv run --project services/mlx-worker-python coverage run \
  --source=services/mlx-worker-python/worker,scripts \
  -m pytest \
  services/mlx-worker-python/tests/test_benchmark_schemas.py \
  services/mlx-worker-python/tests/test_benchmark_store.py \
  services/mlx-worker-python/tests/test_release_gates.py \
  services/mlx-worker-python/tests/test_evaluation_schemas.py \
  services/mlx-worker-python/tests/test_evaluation_core.py \
  services/mlx-worker-python/tests/test_maintenance_service.py
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" \
uv run --project services/mlx-worker-python coverage json -o /tmp/m7-3-5-coverage.json
python3 scripts/python_changed_line_coverage.py \
  --coverage-json /tmp/m7-3-5-coverage.json \
  services/mlx-worker-python/worker/productization/benchmark_schemas.py \
  services/mlx-worker-python/worker/productization/benchmark_store.py \
  services/mlx-worker-python/worker/productization/release_gates.py \
  services/mlx-worker-python/worker/productization/evaluation_schemas.py \
  services/mlx-worker-python/worker/productization/evaluation_store.py \
  services/mlx-worker-python/worker/engine/evaluation_core.py \
  services/mlx-worker-python/worker/engine/maintenance_core.py
```

Expected: changed-line coverage at or above `95%` for the touched Python scope.

- [ ] **Step 5: Commit**

```bash
git add \
  docs/runbooks/m7-benchmark-and-evaluation-foundation.md \
  docs/runbooks/README.md \
  docs/README.md
git commit -m "docs: add m7 benchmark and evaluation runbook"
```

## Spec Coverage Check

- Serving benchmark runners: covered by Task 2.
- Offline dataset packaging: covered by Task 3.
- Evaluation-suite coverage: covered by Task 3 and Task 4.
- Control-plane visibility: covered by Task 4.
- Runbook and verification closure: covered by Task 5.

## Notes

- Keep the first evaluation suite intentionally narrow and deterministic.
- Do not add queueing, comparison tables, VLM-specific benchmark modes, or community submission in this plan.
