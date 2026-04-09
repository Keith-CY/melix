# Phase 8 CLI-First Acceptance Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close every open and pending bucket in `docs/runbooks/phase-8-product-acceptance.md` by making the `melix` CLI the authoritative Phase 8 workflow contract, then wrapping the Window UI around those same CLI workflows and producing real acceptance evidence for both surfaces.

**Architecture:** Keep the Swift control plane as orchestration truth and the Python worker as execution truth, but move the remaining operator workflows onto CLI-first semantics. Managed download and local import converge on one materialized-model receipt shape, CLI acceptance runs shell out to `melix` in a reproducible order, and the Window UI uses a subprocess-backed CLI bridge in production with runner-backed seams in tests. Live acceptance evidence is written under `MELIX_HOME/acceptance/phase8/` and records the approved model `mlx-community/Qwen3.5-0.8B-OptiQ-4bit`, the training fixture `melix-dev-dataset.v1`, benchmark suites, evaluation suite, job IDs, export paths, and UI screenshots.

**Tech Stack:** Swift 6, Swift Testing, SwiftUI/AppKit, Python 3 with `uv`/`pytest`, coverage.py, existing Melix control-plane and worker model-ops layers, repository-owned release-gate and metrics scripts.

---

## File Structure

### Shared CLI Surface

- Modify: `Sources/MelixCLICore/MelixCLI.swift`
- Test: `tests/MelixCLITests/MelixCLIParserTests.swift`
- Test: `tests/MelixCLITests/MelixCLIRunnerTests.swift`

### Python Worker Model Materialization And Evidence

- Create: `services/mlx-worker-python/worker/model_ops/local_import_pipeline.py`
- Modify: `services/mlx-worker-python/worker/model_ops/download_pipeline.py`
- Modify: `services/mlx-worker-python/worker/engine/maintenance_core.py`
- Create: `services/mlx-worker-python/fixtures/training/melix-dev-dataset.v1/manifest.json`
- Create: `services/mlx-worker-python/fixtures/training/melix-dev-dataset.v1/samples.jsonl`
- Test: `services/mlx-worker-python/tests/test_maintenance_service.py`

### CLI Acceptance Runner And Deterministic E2E

- Create: `scripts/phase8_acceptance_bundle.py`
- Modify: `Makefile`
- Create: `tests/test_phase8_acceptance_bundle.py`
- Create: `tests/integration/test_phase8_cli_acceptance.py`
- Modify: `tests/integration/helpers.py`

### Window UI CLI Shell

- Create: `apps/macos-menubar/Sources/AppMain/CLI/MelixCLIWorkflowRunning.swift`
- Create: `apps/macos-menubar/Sources/AppMain/CLI/MelixCLIProcessExecutor.swift`
- Create: `apps/macos-menubar/Sources/AppMain/CLI/MelixSubprocessCLIWorkflowRunner.swift`
- Create: `apps/macos-menubar/Sources/AppMain/Acceptance/Phase8WindowUIAcceptanceRunner.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/AppMain.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`
- Modify: `apps/macos-menubar/Tests/MenuBarTests/TestSupport.swift`
- Modify: `apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift`
- Create: `apps/macos-menubar/Tests/MenuBarTests/MelixSubprocessCLIWorkflowRunnerTests.swift`

### Final Docs And Transaction Records

- Modify: `docs/runbooks/phase-8-product-acceptance.md`
- Modify: `progress.md`

## Performance Probes And Success Metrics

- Probe `phase8.cli.managed_materialize_ms` for both Hub download and local import receipt paths.
- Probe `phase8.cli.session_rebind_ms` from managed-model receipt to `server start` readiness.
- Probe `phase8.cli.chat_roundtrip_ms` for one base-model chat and one derived-model chat.
- Probe `phase8.cli.acceptance_bundle_write_ms` for the evidence bundle flush.
- Probe `phase8.ui.cli_bridge_ms` for Window UI subprocess round-trips on workflow actions.
- Probe `phase8.ui.snapshot_render_ms` for offscreen Window UI evidence capture.

Success metrics:

- `melix model hub download --json` and `melix model import --json` return machine-readable receipts with `model_id`, `managed_model_path`, `source_kind`, and `source_locator`.
- The remaining acceptance flow works without `MELIX_DEV_TEXT_MODEL_PATH`.
- `melix chat run` can prove one base-model chat and one derived-model chat against the approved model family.
- Every touched Phase 8 workflow has positive unit tests, negative unit tests, and deterministic E2E coverage.
- The CLI acceptance runner and the Window UI acceptance runner both emit real evidence bundles under `MELIX_HOME/acceptance/phase8/`.
- Each stage lands on its own branch, is squash-merged into local `main`, and the next stage starts from refreshed `main`.

## Stage Branch Discipline

Use these branch names and keep the stage flow explicit:

```bash
git switch main
git pull --rebase origin main || true
git switch -c codex/p8-s1-cli-materialization
```

Stage branches:

- `codex/p8-s1-cli-materialization`
- `codex/p8-s2-cli-chat`
- `codex/p8-s3-cli-acceptance`
- `codex/p8-s4-window-ui-shell`
- `codex/p8-s5-window-ui-evidence`

If `origin/main` is unavailable in the local environment, replace `git pull --rebase origin main || true` with:

```bash
git rev-parse main
git rev-parse HEAD
```

and confirm the next stage starts from local `main` tip instead of a stale detached commit.

## Task 1: Stage 1 Baseline, Training Fixture, And Managed Materialization Closure

**Files:**
- Create: `services/mlx-worker-python/fixtures/training/melix-dev-dataset.v1/manifest.json`
- Create: `services/mlx-worker-python/fixtures/training/melix-dev-dataset.v1/samples.jsonl`
- Create: `services/mlx-worker-python/worker/model_ops/local_import_pipeline.py`
- Modify: `services/mlx-worker-python/worker/model_ops/download_pipeline.py`
- Modify: `services/mlx-worker-python/worker/engine/maintenance_core.py`
- Modify: `Sources/MelixCLICore/MelixCLI.swift`
- Test: `services/mlx-worker-python/tests/test_maintenance_service.py`
- Test: `tests/MelixCLITests/MelixCLIParserTests.swift`
- Test: `tests/MelixCLITests/MelixCLIRunnerTests.swift`

- [ ] **Step 1: Write the missing fixture files and the failing positive/negative tests**

Add the training fixture manifest and samples that the live acceptance run will use:

```json
{
  "schema_version": "melix.training_dataset_manifest.v1",
  "dataset_id": "melix-dev-dataset.v1",
  "task_kind": "chat_sft",
  "format": "jsonl",
  "sample_count": 2,
  "chat_feature": "messages",
  "text_feature": "text"
}
```

```jsonl
{"messages":[{"role":"system","content":"You are Melix acceptance training data."},{"role":"user","content":"Reply with BASE_OK."},{"role":"assistant","content":"BASE_OK"}]}
{"messages":[{"role":"user","content":"Reply with DERIVED_OK."},{"role":"assistant","content":"DERIVED_OK"}]}
```

Add failing tests that expect:

- `melix model import --path /tmp/qwen-local-model --model-id melix-dev-qwen-local --json`
- a negative parser path when `--path` is missing
- a worker-side local import operation that copies a local model directory into managed storage
- a negative worker-side path when the source directory is missing or the manifest is invalid

Run:

```bash
HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --filter 'MelixCLIParserTests|MelixCLIRunnerTests'
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_maintenance_service.py -q
```

Expected:

- new parser, runner, and worker tests fail because `model import` and local import execution do not exist yet

- [ ] **Step 2: Add a first-class local-import command and a shared managed-model receipt shape in the CLI**

Extend `MelixCLI.swift` with a new options type, enum case, usage text, parser branch, and JSON receipt rendering:

```swift
public struct ModelImportOptions: Equatable, Sendable {
    public let path: String
    public let modelID: String
    public let modelKind: String
    public let revision: String
    public let json: Bool
}

public struct ManagedModelReceipt: Codable, Equatable, Sendable {
    public let modelID: String
    public let managedModelPath: String
    public let sourceKind: String
    public let sourceLocator: String
    public let warnings: [String]
}
```

Use the same receipt renderer for both `model hub download --json` and `model import --json` so later stages can rebind a server session without manual rediscovery.

- [ ] **Step 3: Implement Python local import materialization and route it through maintenance core**

Create a dedicated pipeline instead of overloading unrelated conversion behavior:

```python
@dataclass(frozen=True)
class LocalImportResult:
    output_path: Path
    manifest_json: str


class LocalImportPipeline:
    def run(self, *, source_dir: Path, managed_root: Path, model_id: str, revision: str, model_kind: str) -> LocalImportResult:
        materialized_dir = managed_root / "local" / model_id / revision
        if not source_dir.is_dir():
            raise ModelOperationError(code="invalid_argument", message="local import requires an existing source directory.")
        shutil.copytree(source_dir, materialized_dir, dirs_exist_ok=False)
        manifest_path = materialized_dir / "manifest.json"
        manifest_payload = {
            "schema_version": "melix.model_registry_manifest.v1",
            "model_id": model_id,
            "model_kind": model_kind,
            "revision": revision,
            "provider_id": "local",
            "variant_id": revision,
            "ext": {
                "melix.source_kind": "local_path",
                "melix.source_locator": str(source_dir),
                "melix.model_path": str(materialized_dir),
            },
        }
        manifest_path.write_text(json.dumps(manifest_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return LocalImportResult(output_path=materialized_dir, manifest_json=json.dumps(manifest_payload, sort_keys=True))
```

Wire `maintenance_core.py` so `operation == "local_import"` calls the new pipeline and emits manifest metadata containing:

- `model_id`
- `managed_model_path`
- `source_kind=local_path`
- `source_locator=/tmp/qwen-local-model`

- [ ] **Step 4: Re-run the focused tests and add a deterministic E2E that exercises materialization -> registry visibility**

Create `tests/integration/test_phase8_cli_acceptance.py` with a deterministic materialization path that does not need the live Hugging Face model:

```python
def test_cli_materialization_closes_download_and_local_import_receipts(tmp_path: Path) -> None:
    stack = LiveMelixStack(Path(__file__).resolve().parents[2], environment_overrides={"MELIX_HOME": str(tmp_path / "home")})
    stack.start()
    try:
        result = run_cli_json(["model", "import", "--path", str(tmp_path / "fixture-model"), "--model-id", "melix-dev-qwen-local", "--json"], env={"MELIX_HOME": str(tmp_path / "home")})
        assert result["model_id"] == "melix-dev-qwen-local"
        assert Path(result["managed_model_path"]).is_dir()
    finally:
        stack.stop()
```

Run:

```bash
HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --filter 'MelixCLIParserTests|MelixCLIRunnerTests'
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_maintenance_service.py tests/integration/test_phase8_cli_acceptance.py -q
```

Expected:

- the new parser, runner, worker, and deterministic E2E tests pass

- [ ] **Step 5: Measure Stage 1 coverage**

Run:

```bash
HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --enable-code-coverage --filter MelixCLITests
python3 scripts/swift_changed_line_coverage.py --binary .build/arm64-apple-macosx/debug/melixPackageTests.xctest/Contents/MacOS/melixPackageTests --profdata .build/arm64-apple-macosx/debug/codecov/default.profdata Sources/MelixCLICore/MelixCLI.swift tests/MelixCLITests/MelixCLIParserTests.swift tests/MelixCLITests/MelixCLIRunnerTests.swift
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python --extra mlx coverage run --data-file /tmp/p8_s1_py.coverage --source=services/mlx-worker-python/worker,tests/integration -m pytest services/mlx-worker-python/tests/test_maintenance_service.py tests/integration/test_phase8_cli_acceptance.py -q
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python --extra mlx coverage json --data-file /tmp/p8_s1_py.coverage -o /tmp/p8_s1_py_coverage.json
python3 scripts/python_changed_line_coverage.py --coverage-json /tmp/p8_s1_py_coverage.json services/mlx-worker-python/worker/model_ops/local_import_pipeline.py services/mlx-worker-python/worker/model_ops/download_pipeline.py services/mlx-worker-python/worker/engine/maintenance_core.py services/mlx-worker-python/tests/test_maintenance_service.py tests/integration/test_phase8_cli_acceptance.py
```

Expected:

- changed-line coverage is at or above `95%` for both Swift and Python touched scope

- [ ] **Step 6: Commit Stage 1 and squash it into local `main`**

```bash
git add Sources/MelixCLICore/MelixCLI.swift \
  services/mlx-worker-python/worker/model_ops/local_import_pipeline.py \
  services/mlx-worker-python/worker/model_ops/download_pipeline.py \
  services/mlx-worker-python/worker/engine/maintenance_core.py \
  services/mlx-worker-python/fixtures/training/melix-dev-dataset.v1/manifest.json \
  services/mlx-worker-python/fixtures/training/melix-dev-dataset.v1/samples.jsonl \
  services/mlx-worker-python/tests/test_maintenance_service.py \
  tests/MelixCLITests/MelixCLIParserTests.swift \
  tests/MelixCLITests/MelixCLIRunnerTests.swift \
  tests/integration/test_phase8_cli_acceptance.py
git commit -m "feat: close phase8 cli managed model materialization"
git switch main
git pull --rebase origin main || true
git merge --squash codex/p8-s1-cli-materialization
git commit -m "feat: close phase8 stage 1 cli materialization"
git branch -D codex/p8-s1-cli-materialization
git switch -c codex/p8-s2-cli-chat
```

## Task 2: Stage 2 CLI Session Rebinding And Base Chat Closure

**Files:**
- Modify: `Sources/MelixCLICore/MelixCLI.swift`
- Test: `tests/MelixCLITests/MelixCLIParserTests.swift`
- Test: `tests/MelixCLITests/MelixCLIRunnerTests.swift`
- Modify: `tests/integration/test_phase8_cli_acceptance.py`

- [ ] **Step 1: Write failing parser, runner, and E2E tests for `melix chat run` and rebinding flow**

Add tests that expect:

- `melix chat run --model-id MODEL_ID --message TEXT [--system TEXT] [--server-session-id ID] [--json]`
- one negative parser path when `--message` is missing
- one runner path that collects streamed assistant text and returns machine-readable JSON
- one deterministic E2E path that uses the Stage 1 managed-model receipt to update, select, and start the primary server session before chatting

Run:

```bash
HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --filter 'MelixCLIParserTests|MelixCLIRunnerTests'
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python --extra mlx pytest tests/integration/test_phase8_cli_acceptance.py -q
```

Expected:

- the new chat parser and runner tests fail because the `chat` command family does not exist yet

- [ ] **Step 2: Add `chat run` to the CLI and collect typed chat transcripts**

Extend `MelixCLI.swift` with:

```swift
public struct ChatRunOptions: Equatable, Sendable {
    public let modelID: String
    public let message: String
    public let systemPrompt: String
    public let serverSessionID: String
    public let json: Bool
}

public struct ChatRunReceipt: Codable, Equatable, Sendable {
    public let modelID: String
    public let serverSessionID: String
    public let assistantText: String
    public let finishReason: String
    public let requestID: String
}
```

Implement the runner so it uses the existing control-plane client:

```swift
let execution = try await client.startChat(
    ControlPlaneChatRequest(
        modelID: options.modelID,
        messages: buildChatMessages(options: options)
    )
)
```

and drains the stream into `assistantText`, `finishReason`, and `requestID`.

- [ ] **Step 3: Close the rebinding workflow using existing server-session commands instead of a second source of truth**

Do not add a new app-owned bind path. Use the managed receipt from Stage 1 and compose the existing commands in deterministic order:

```bash
melix model roots rescan --json
melix server session update --server-session-id server-session-1 --model-id "$MODEL_ID" --json
melix server session select --server-session-id server-session-1 --json
melix server start --server-session-id server-session-1 --json
melix chat run --model-id "$MODEL_ID" --message "Reply with BASE_OK" --json
```

The Stage 2 E2E must assert that the flow succeeds without `MELIX_DEV_TEXT_MODEL_PATH`.

- [ ] **Step 4: Re-run focused tests and record Stage 2 coverage**

Run:

```bash
HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --enable-code-coverage --filter MelixCLITests
python3 scripts/swift_changed_line_coverage.py --binary .build/arm64-apple-macosx/debug/melixPackageTests.xctest/Contents/MacOS/melixPackageTests --profdata .build/arm64-apple-macosx/debug/codecov/default.profdata Sources/MelixCLICore/MelixCLI.swift tests/MelixCLITests/MelixCLIParserTests.swift tests/MelixCLITests/MelixCLIRunnerTests.swift
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python --extra mlx coverage run --data-file /tmp/p8_s2_py.coverage --source=tests/integration -m pytest tests/integration/test_phase8_cli_acceptance.py -q
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python --extra mlx coverage json --data-file /tmp/p8_s2_py.coverage -o /tmp/p8_s2_py_coverage.json
python3 scripts/python_changed_line_coverage.py --coverage-json /tmp/p8_s2_py_coverage.json tests/integration/test_phase8_cli_acceptance.py
```

Expected:

- chat parser, chat runner, and deterministic session-rebind E2E all pass
- changed-line coverage stays at or above `95%`

- [ ] **Step 5: Commit Stage 2 and squash it into local `main`**

```bash
git add Sources/MelixCLICore/MelixCLI.swift \
  tests/MelixCLITests/MelixCLIParserTests.swift \
  tests/MelixCLITests/MelixCLIRunnerTests.swift \
  tests/integration/test_phase8_cli_acceptance.py
git commit -m "feat: close phase8 cli session rebind and base chat"
git switch main
git pull --rebase origin main || true
git merge --squash codex/p8-s2-cli-chat
git commit -m "feat: close phase8 stage 2 cli chat"
git branch -D codex/p8-s2-cli-chat
git switch -c codex/p8-s3-cli-acceptance
```

## Task 3: Stage 3 CLI LoRA, Bench, Eval, Export, And Real Evidence Bundle

**Files:**
- Create: `scripts/phase8_acceptance_bundle.py`
- Modify: `Makefile`
- Create: `tests/test_phase8_acceptance_bundle.py`
- Modify: `tests/integration/test_phase8_cli_acceptance.py`

- [ ] **Step 1: Write failing unit and deterministic integration tests for the acceptance bundle runner**

Add a unit test that expects the runner to call the CLI in this order:

```python
[
    ["melix", "model", "hub", "download", "--repo-id", "mlx-community/Qwen3.5-0.8B-OptiQ-4bit", "--json"],
    ["melix", "model", "roots", "rescan", "--json"],
    ["melix", "server", "session", "update", "--server-session-id", "server-session-1", "--model-id", "mlx-community/Qwen3.5-0.8B-OptiQ-4bit", "--json"],
    ["melix", "server", "start", "--server-session-id", "server-session-1", "--json"],
    ["melix", "chat", "run", "--model-id", "mlx-community/Qwen3.5-0.8B-OptiQ-4bit", "--message", "Reply with BASE_OK", "--json"],
    ["melix", "lora", "train", "--model-id", "mlx-community/Qwen3.5-0.8B-OptiQ-4bit", "--dataset-uri", "services/mlx-worker-python/fixtures/training/melix-dev-dataset.v1", "--adapter-name", "phase8-acceptance", "--json"],
]
```

Add negative tests for:

- CLI command failure bubbling up with a non-zero exit status
- missing evaluation export paths
- malformed JSON from a subprocess call

Run:

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python --extra mlx pytest tests/test_phase8_acceptance_bundle.py tests/integration/test_phase8_cli_acceptance.py -q
```

Expected:

- the new acceptance bundle tests fail because the script and `make` target do not exist yet

- [ ] **Step 2: Implement the repository-owned acceptance bundle runner and target**

Create `scripts/phase8_acceptance_bundle.py` so it shells out to `melix`, collects JSON receipts, and writes:

```python
bundle = {
    "schema_version": "melix.phase8.acceptance_bundle.v1",
    "model": {
        "model_id": managed_receipt["model_id"],
        "source_kind": managed_receipt["source_kind"],
        "source_locator": managed_receipt["source_locator"],
    },
    "datasets": {
        "training_fixture": "melix-dev-dataset.v1",
        "evaluation_dataset": "mmlu.dev.v1",
    },
    "suites": {
        "bench": ["smoke", "latency"],
        "matrix": ["smoke"],
        "evaluation": ["mmlu"],
    },
    "jobs": {
        "lora_train_job_id": lora_train["job_id"],
        "bench_job_id": bench["job_id"],
        "bench_matrix_job_id": matrix["job_id"],
        "evaluation_job_id": evaluation["job_id"],
    },
    "exports": {
        "bench_csv": bench_csv_path,
        "matrix_summary_csv": matrix_summary_csv_path,
        "evaluation_summary_csv": evaluation_summary_csv_path,
        "evaluation_samples_jsonl": evaluation_samples_jsonl_path,
    },
    "metrics": timings,
}
```

Write the bundle under:

```text
MELIX_HOME/acceptance/phase8/cli/2026-04-09T120000Z/bundle.json
```

Add a `Makefile` target:

```make
phase8-acceptance:
	PYTHONPATH="$(ROOT):$(ROOT)/services/mlx-worker-python" UV_CACHE_DIR="$(UV_CACHE_DIR)" uv run --project services/mlx-worker-python --extra mlx python scripts/phase8_acceptance_bundle.py $(PHASE8_ACCEPTANCE_ARGS)
```

- [ ] **Step 3: Extend the deterministic E2E to validate LoRA, derived chat, bench, matrix bench, eval, and export output paths**

The deterministic E2E should assert:

- derived model alias is present in registry or export history
- `melix chat run` works once against the base model and once against the derived model
- bench, matrix bench, and eval receipts carry `job_id` and output directories
- export paths written into the bundle exist

Run:

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python --extra mlx pytest tests/test_phase8_acceptance_bundle.py tests/integration/test_phase8_cli_acceptance.py -q
```

Expected:

- the acceptance runner tests and deterministic E2E pass

- [ ] **Step 4: Run the live CLI acceptance and preserve real evidence**

Run:

```bash
make phase8-acceptance PHASE8_ACCEPTANCE_ARGS="--live --model-id mlx-community/Qwen3.5-0.8B-OptiQ-4bit --training-fixture services/mlx-worker-python/fixtures/training/melix-dev-dataset.v1 --bench-suite smoke --bench-suite latency --matrix-suite smoke --evaluation-suite mmlu --evaluation-dataset mmlu.dev.v1 --json"
```

Expected:

- a real CLI evidence bundle exists under `MELIX_HOME/acceptance/phase8/cli/2026-04-09T120000Z/`
- the bundle records one base-model chat, one derived-model chat, LoRA job ID, matrix benchmark job ID, evaluation job ID, and export artifact paths

- [ ] **Step 5: Measure Stage 3 coverage and commit**

Run:

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python --extra mlx coverage run --data-file /tmp/p8_s3_py.coverage --source=scripts,tests/integration -m pytest tests/test_phase8_acceptance_bundle.py tests/integration/test_phase8_cli_acceptance.py -q
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python --extra mlx coverage json --data-file /tmp/p8_s3_py.coverage -o /tmp/p8_s3_py_coverage.json
python3 scripts/python_changed_line_coverage.py --coverage-json /tmp/p8_s3_py_coverage.json scripts/phase8_acceptance_bundle.py tests/test_phase8_acceptance_bundle.py tests/integration/test_phase8_cli_acceptance.py
git add Makefile \
  scripts/phase8_acceptance_bundle.py \
  tests/test_phase8_acceptance_bundle.py \
  tests/integration/test_phase8_cli_acceptance.py \
  Sources/MelixCLICore/MelixCLI.swift
git commit -m "feat: add phase8 cli acceptance bundle"
git switch main
git pull --rebase origin main || true
git merge --squash codex/p8-s3-cli-acceptance
git commit -m "feat: close phase8 stage 3 cli acceptance"
git branch -D codex/p8-s3-cli-acceptance
git switch -c codex/p8-s4-window-ui-shell
```

## Task 4: Stage 4 Window UI As A Subprocess-Backed CLI Shell

**Files:**
- Create: `apps/macos-menubar/Sources/AppMain/CLI/MelixCLIWorkflowRunning.swift`
- Create: `apps/macos-menubar/Sources/AppMain/CLI/MelixCLIProcessExecutor.swift`
- Create: `apps/macos-menubar/Sources/AppMain/CLI/MelixSubprocessCLIWorkflowRunner.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/AppMain.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`
- Modify: `apps/macos-menubar/Tests/MenuBarTests/TestSupport.swift`
- Modify: `apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift`
- Create: `apps/macos-menubar/Tests/MenuBarTests/MelixSubprocessCLIWorkflowRunnerTests.swift`

- [ ] **Step 1: Write failing Window UI tests for the subprocess CLI bridge**

Add tests that expect:

- production bootstrap injects a subprocess-backed CLI workflow runner instead of a direct `MelixCLIRunner`
- Window UI workflow actions use CLI JSON output for Hub download, local import, server session update/start, LoRA train/activate, bench, matrix bench, eval, and export
- negative subprocess paths surface typed failure state into `RuntimeViewModel`

Run:

```bash
HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/apps/macos-menubar/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --filter 'RuntimeViewModelTests|AppMainBootstrapTests|MelixSubprocessCLIWorkflowRunnerTests'
```

Expected:

- new app tests fail because the subprocess workflow bridge does not exist yet

- [ ] **Step 2: Introduce a protocol boundary that both `MelixCLIRunner` and the subprocess runner can satisfy**

Create a narrow shared protocol instead of hard-coding the app to one actor type:

```swift
public protocol MelixCLIWorkflowRunning: Sendable {
    func run(_ command: MelixCLICommand) async throws -> String
    func searchHubModels(query: String, pageSize: UInt32, cursor: String, mlxOnly: Bool) async throws -> Melix_Controlplane_V1_HubSearchResult
    func getHubModelCard(repoID: String) async throws -> Melix_Controlplane_V1_HubModelCard
    func downloadHubModel(repoID: String, revision: String) async throws -> ManagedModelReceipt
    func importModel(path: String, modelID: String, modelKind: String, revision: String) async throws -> ManagedModelReceipt
}
```

Keep this protocol in `AppMain` and add an app-side extension that adapts imported `MelixCLIRunner` to it, so the core package does not need an inverse dependency on the menubar app.

- [ ] **Step 3: Implement the subprocess-backed production runner and switch the app bootstrap to it**

Create a process executor abstraction so tests never launch a real subprocess:

```swift
public protocol MelixCLIProcessExecuting: Sendable {
    func run(arguments: [String], environment: [String: String]) async throws -> String
}
```

Then implement `MelixSubprocessCLIWorkflowRunner` so production shell-outs to the bundled `melix` executable with `--json` and decodes the result back into typed UI state. Update `AppMain.swift` so the default bootstrap path uses the subprocess runner, while tests still pass a fake or `MelixCLIRunner`.

- [ ] **Step 4: Re-run the focused app tests and capture Stage 4 coverage**

Run:

```bash
HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/apps/macos-menubar/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --enable-code-coverage --filter 'RuntimeViewModelTests|AppMainBootstrapTests|MelixSubprocessCLIWorkflowRunnerTests'
python3 scripts/swift_changed_line_coverage.py --binary apps/macos-menubar/.build/arm64-apple-macosx/debug/MelixMacOSMenubarPackageTests.xctest/Contents/MacOS/MelixMacOSMenubarPackageTests --profdata apps/macos-menubar/.build/arm64-apple-macosx/debug/codecov/default.profdata apps/macos-menubar/Sources/AppMain/CLI/MelixCLIWorkflowRunning.swift apps/macos-menubar/Sources/AppMain/CLI/MelixCLIProcessExecutor.swift apps/macos-menubar/Sources/AppMain/CLI/MelixSubprocessCLIWorkflowRunner.swift apps/macos-menubar/Sources/AppMain/AppMain.swift apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift apps/macos-menubar/Tests/MenuBarTests/TestSupport.swift apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift apps/macos-menubar/Tests/MenuBarTests/MelixSubprocessCLIWorkflowRunnerTests.swift
```

Expected:

- the app package tests pass
- changed-line coverage is at or above `95%`

- [ ] **Step 5: Commit Stage 4 and squash it into local `main`**

```bash
git add apps/macos-menubar/Sources/AppMain/CLI/MelixCLIWorkflowRunning.swift \
  apps/macos-menubar/Sources/AppMain/CLI/MelixCLIProcessExecutor.swift \
  apps/macos-menubar/Sources/AppMain/CLI/MelixSubprocessCLIWorkflowRunner.swift \
  apps/macos-menubar/Sources/AppMain/AppMain.swift \
  apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift \
  apps/macos-menubar/Tests/MenuBarTests/TestSupport.swift \
  apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift \
  apps/macos-menubar/Tests/MenuBarTests/MelixSubprocessCLIWorkflowRunnerTests.swift \
  Sources/MelixCLICore/MelixCLI.swift
git commit -m "feat: route phase8 window ui workflows through cli subprocesses"
git switch main
git pull --rebase origin main || true
git merge --squash codex/p8-s4-window-ui-shell
git commit -m "feat: close phase8 stage 4 window ui cli shell"
git branch -D codex/p8-s4-window-ui-shell
git switch -c codex/p8-s5-window-ui-evidence
```

## Task 5: Stage 5 Window UI Live Acceptance, Real Screenshots, And Runbook Closure

**Files:**
- Create: `apps/macos-menubar/Sources/AppMain/Acceptance/Phase8WindowUIAcceptanceRunner.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/AppMain.swift`
- Create: `tests/integration/test_phase8_window_ui_acceptance.py`
- Modify: `docs/runbooks/phase-8-product-acceptance.md`
- Modify: `progress.md`

- [ ] **Step 1: Write failing deterministic tests for the Window UI acceptance runner**

Add a deterministic integration test that expects the acceptance runner to:

- boot the app-side view model with the subprocess CLI bridge
- drive the same workflow actions as the CLI acceptance bundle
- refresh the desktop foundation
- render a Window UI screenshot path and a machine-readable evidence bundle path

Run:

```bash
HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/apps/macos-menubar/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --filter 'RuntimeViewModelTests|DesktopFoundationViewTests'
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python --extra mlx pytest tests/integration/test_phase8_window_ui_acceptance.py -q
```

Expected:

- the new Window UI acceptance tests fail because the acceptance runner and screenshot capture do not exist yet

- [ ] **Step 2: Implement an offscreen Window UI acceptance runner that produces real screenshots**

Create `Phase8WindowUIAcceptanceRunner.swift` so it drives the real `RuntimeViewModel`, then renders a real UI image:

```swift
let renderer = ImageRenderer(
    content: DesktopFoundationRootView(viewModel: viewModel)
        .frame(width: 1440, height: 960)
)
if let image = renderer.nsImage {
    try writePNG(image: image, to: screenshotURL)
}
```

Write:

- `MELIX_HOME/acceptance/phase8/window-ui/2026-04-09T120000Z/bundle.json`
- `MELIX_HOME/acceptance/phase8/window-ui/2026-04-09T120000Z/window-ui.png`

The bundle must reference the CLI evidence bundle that the UI path relied on, so the evidence chain stays explicit.

- [ ] **Step 3: Run deterministic Window UI E2E, then run live Window UI acceptance**

Run:

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python --extra mlx pytest tests/integration/test_phase8_window_ui_acceptance.py -q
MELIX_PHASE8_WINDOW_UI_ACCEPTANCE=1 swift run --package-path apps/macos-menubar melix-menubar
```

Expected:

- deterministic Window UI acceptance passes
- a real screenshot and Window UI evidence bundle exist under `MELIX_HOME/acceptance/phase8/window-ui/2026-04-09T120000Z/`

- [ ] **Step 4: Update the runbook buckets, final commands, and real evidence references**

Update `docs/runbooks/phase-8-product-acceptance.md` so Bucket 2 and Bucket 3 are closed and the final operator instructions point at:

```bash
make phase8-acceptance PHASE8_ACCEPTANCE_ARGS="--live --json"
MELIX_PHASE8_WINDOW_UI_ACCEPTANCE=1 swift run --package-path apps/macos-menubar melix-menubar
make phase8-release-gate PHASE8_RELEASE_GATE_ARGS="--json"
make phase8-metrics PHASE8_METRICS_ARGS="--json"
```

Also add the exact evidence bundle path conventions and the approved model ID `mlx-community/Qwen3.5-0.8B-OptiQ-4bit`.

- [ ] **Step 5: Run final repository verification, coverage, release gate, and metrics**

Run:

```bash
make proto
make py-test
make swift-test
make integration-test
make phase8-release-gate PHASE8_RELEASE_GATE_ARGS="--json"
make phase8-metrics PHASE8_METRICS_ARGS="--json"
```

If the final stage touches executable code after the earlier coverage runs, repeat the relevant changed-line coverage command from Stages 3 and 4 before committing.

- [ ] **Step 6: Commit Stage 5 and squash it into local `main`**

```bash
git add apps/macos-menubar/Sources/AppMain/Acceptance/Phase8WindowUIAcceptanceRunner.swift \
  apps/macos-menubar/Sources/AppMain/AppMain.swift \
  tests/integration/test_phase8_window_ui_acceptance.py \
  docs/runbooks/phase-8-product-acceptance.md \
  progress.md
git commit -m "feat: close phase8 window ui acceptance evidence"
git switch main
git pull --rebase origin main || true
git merge --squash codex/p8-s5-window-ui-evidence
git commit -m "feat: close phase8 stage 5 window ui evidence"
git branch -D codex/p8-s5-window-ui-evidence
```

## Safe Exit

- Keep all new CLI additions additive. Do not break existing `model`, `server`, `lora`, `bench`, or `eval` command behavior that current tests already cover.
- Do not introduce a second server-session binding truth in the Window UI. The app may present workflow state, but binding semantics stay on the CLI and control-plane path.
- Keep the deterministic acceptance tests independent from the live acceptance flag so CI never depends on live network model fetches.
- If live acceptance is blocked by a local environment issue, keep the deterministic tests and evidence-bundle writer green, record the blocker in `progress.md`, and stop before claiming the runbook is closed.

## Self-Review

### Spec Coverage

- Managed Hugging Face download and first-class local import converge in Task 1.
- Server-session rebinding without `MELIX_DEV_TEXT_MODEL_PATH` and base chat closure land in Task 2.
- LoRA, benchmark, evaluation, export, and machine-readable CLI evidence land in Task 3.
- Window UI as a CLI subprocess shell lands in Task 4.
- Real Window UI evidence, screenshots, and runbook closure land in Task 5.

### Placeholder Scan

- No `TODO`, `TBD`, or “implement later” placeholders remain.
- Every stage includes exact files, concrete commands, named branches, and explicit verification commands.
- Every stage includes unit, negative, and deterministic E2E expectations plus coverage measurement.

### Type Consistency

- The plan uses `ManagedModelReceipt` for both `model hub download` and `model import`.
- The Window UI shell uses `MelixCLIWorkflowRunning` as the shared interface instead of tying the app to one concrete runner.
- The acceptance bundle always references `melix-dev-dataset.v1`, `mmlu.dev.v1`, and `mlx-community/Qwen3.5-0.8B-OptiQ-4bit` consistently across CLI and Window UI flows.
