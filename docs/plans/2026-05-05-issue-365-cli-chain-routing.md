# Issue 365 CLI Chain Routing Slice

## Goal

Continue the implementation path for
https://github.com/Keith-CY/melix/issues/365 by making `melix pipeline run`
able to describe the post-training CLI chain in one machine-readable workflow:
adapter training, alignment training, export/publish, quantization, activation,
local chat smoke, and evaluation/benchmark evidence.

Issue 365 is still not complete after this slice. This work adds pipeline
routing and fast dry-run chain coverage; it does not replace the remaining real
local runtime acceptance requirements.

## Scope

### Included

- Add `alignment.train` support to the pipeline command builder so DPO, ORPO,
  CPO, GRPO, and RLHF alignment runs are addressable outside `lora.train`.
- Add post-training model operation routing for `lora.publish`, `quantize`,
  `convert`, and `upload` pipeline steps.
- Preserve existing pipeline behavior for `lora.train`, `lora.activate`,
  `chat.run`, bench, and eval steps.
- Add dry-run coverage proving a post-training chain can be planned with
  step-to-step artifact references across:
  - `lora.train`
  - `alignment.train`
  - `lora.publish`
  - `quantize`
  - `lora.activate`
  - `chat.run`
  - eval or bench evidence steps
- Keep screenshot cleanup scoped to temporary generated screenshot artifacts
  only. Tracked app branding images, evaluation fixtures, docs, and source
  files are not cleanup targets.
- Add an Issue 365 CLI acceptance bundle harness that writes a machine-readable
  matrix for every required CLI chain and separates planning, deterministic
  dry-run, and real-local-runtime evidence.
- Add real-local-runtime preflight evidence to the acceptance bundle so `real`
  mode records missing CLI, dataset, calibration, and reward-model prerequisites
  as machine-readable blockers before launching long-running pipeline cases.
- Add `--case-id` selection for the acceptance bundle so operators can run a
  real local runtime subset without requiring unused business-line inputs.
- Add a local-filesystem publish backend for real local acceptance runs so
  `lora.publish` can produce publish receipts without requiring networked
  Hugging Face credentials.
- Preserve real-runtime adapter activation by activating the trained or aligned
  adapter manifest directly, while still publishing a receipt as evidence.
- Normalize successful pipeline result envelopes so downstream steps can refer
  to `result.output_path` even when a command reports an artifact-specific path
  such as `artifact_path`, `bundle_path`, `managed_model_path`, or `report_path`.
- Fix MLX text runtime stop handling so stop sequences are only forwarded to
  `mlx_lm.utils.stream_generate` when the callable declares the specific stop
  keyword. This avoids passing unsupported `stop` kwargs through a variadic
  wrapper to installed `mlx-lm` versions whose generation step rejects them.
- Add preference batch sharding support for MLX-LM trainer comm groups so
  single-process DPO, ORPO, and CPO real-runtime runs do not fail when the
  upstream trainer passes `mx.distributed.init()` into the custom preference
  batch iterator.
- Add public `melix quantize` and pipeline routing for
  `--local-inference-smoke-mode` and `--local-inference-smoke-prompt` so PTQ
  and QAT acceptance can request the quantization pipeline's own typed
  `runtime_generate` local inference evidence.
- Add public `melix quantize` and pipeline routing for `--quantization-backend`
  plus the MLX-LM quantization knobs, and route the PTQ acceptance case through
  a fused merged export with `quantization_backend=mlx_lm_convert` instead of
  exercising only the manifest-only quantization path.
- Publish the PTQ fused derived model from
  `lora.activate.result.derived_model_path` via `merged_model_path` so the real
  pipeline uses the activation result field that the runtime actually returns.
- Route PTQ/QAT acceptance through the quantized bundle manifest's
  `local_inference_smoke` and `release_gate.local_inference_smoke_result`
  checks instead of treating `quantized_model_bundle` directories as generic
  `chat.run` targets.

### Excluded

- Real local runtime acceptance for every business line. This slice can preflight
  and run real-mode cases, but it does not provide the required local model,
  dataset, reward-model, or runtime evidence bundle for all cases.
- GRPO candidate generation from a live policy runtime.
- RLHF reward-model integration from issue 366.
- QAT trainer/export implementation.
- Native Window UI acceptance.
- Closing issue 365.

## Performance And Metrics

This slice changes command construction, acceptance planning, and real-mode
preflight only. It should not add model execution in plan/dry-run mode,
background polling, or broad file-system scans beyond checking the explicit CLI
and input paths that the operator passes to the acceptance bundle.

Success metrics:

- Pipeline command construction keeps using typed Swift options rather than
  shell string concatenation.
- Pipeline dry-run receipts include stable command IDs for the new post-training
  steps.
- Existing pipeline resume, check, and reference behavior remains unchanged.
- The Issue 365 acceptance bundle must mark plan-only and dry-run evidence as
  not release-ready even when every planned pipeline case is covered.
- The Issue 365 acceptance bundle must mark real-mode cases as `blocked` when
  required local prerequisites are missing, and must record the blocker codes in
  the bundle rather than invoking long-running pipelines that cannot succeed.
- Real-mode subset runs must only preflight the selected case inputs, so a LoRA
  subset can run without requiring unused RLHF reward-model or quantization
  calibration artifacts.
- Changed-line coverage for the touched Swift/doc scope is at least 95 percent.
- Changed-line coverage for the touched Python scope is at least 95 percent.
- Real local LoRA, QLoRA, DoRA, DPO, ORPO, and CPO subset evidence proves the
  fixed chain can complete: training, local publish receipt, direct adapter
  activation, chat smoke, and eval smoke.
- Quantized PTQ/QAT real-mode subsets must not be marked successful unless the
  quantize step reports `local_runtime_generate` smoke evidence with
  `status=passed` and `release_gate.local_inference_smoke_result=passed`.

## Verification

Targeted commands:

```bash
swift test --filter MelixCLIRunnerTests
swift test --filter MelixCLIParserTests
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="$PWD/.uv-cache" uv run --project services/mlx-worker-python pytest -q tests/integration/test_issue365_acceptance_bundle.py
git diff --check
```

Coverage and metrics:

```bash
swift test --enable-code-coverage --filter 'MelixCLIRunnerTests|MelixCLIParserTests'
python3 scripts/swift_changed_line_coverage.py \
  --binary .build/arm64-apple-macosx/debug/MelixPackageTests.xctest/Contents/MacOS/MelixPackageTests \
  --profdata .build/arm64-apple-macosx/debug/codecov/default.profdata \
  --diff-from origin/main \
  Sources/MelixCLICore/MelixPipelineRunner.swift \
  tests/MelixCLITests/MelixCLIRunnerTests.swift \
  tests/MelixCLITests/MelixCLIParserTests.swift \
  docs/plans/2026-05-05-issue-365-cli-chain-routing.md
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="$PWD/.uv-cache" uv run --project services/mlx-worker-python coverage run -m pytest -q tests/integration/test_issue365_acceptance_bundle.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="$PWD/.uv-cache" uv run --project services/mlx-worker-python coverage json -o /tmp/issue365-cli-acceptance-bundle-coverage.json
python3 scripts/python_changed_line_coverage.py \
  --coverage-json /tmp/issue365-cli-acceptance-bundle-coverage.json \
  --diff-from origin/main \
  scripts/issue365_acceptance_bundle.py \
  tests/integration/test_issue365_acceptance_bundle.py \
  docs/plans/2026-05-05-issue-365-cli-chain-routing.md
```

Expected changed-line coverage target: at least 95 percent for the changed
Swift scope. Documentation-only lines are reported as N/A when the coverage
tool does not map them to executable statements.

Results on 2026-05-06 after adding real-mode preflight and case selection:

- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="$PWD/.uv-cache" uv run --project services/mlx-worker-python pytest -q tests/integration/test_issue365_acceptance_bundle.py`:
  13 passed.
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="$PWD/.uv-cache" uv run --project services/mlx-worker-python coverage run -m pytest -q tests/integration/test_issue365_acceptance_bundle.py`:
  13 passed.
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="$PWD/.uv-cache" uv run --project services/mlx-worker-python coverage json -o /tmp/issue365-cli-acceptance-bundle-coverage.json`:
  wrote JSON coverage.
- `python3 scripts/python_changed_line_coverage.py --coverage-json /tmp/issue365-cli-acceptance-bundle-coverage.json --diff-from origin/main scripts/issue365_acceptance_bundle.py tests/integration/test_issue365_acceptance_bundle.py docs/plans/2026-05-05-issue-365-cli-chain-routing.md`:
  97.30 percent total changed-line coverage, 469/482 executable lines.
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="$PWD/.uv-cache" uv run --project services/mlx-worker-python python -m compileall -q scripts/issue365_acceptance_bundle.py tests/integration/test_issue365_acceptance_bundle.py`:
  passed.
- `python3 scripts/issue365_acceptance_bundle.py --execution-mode plan --output-dir .runtime/issue365/acceptance-smoke --timestamp 2026-05-06T010000Z --json`:
  wrote a plan bundle with 10 planned cases, 0 blocked cases, and
  `release_ready=false`.
- `python3 scripts/issue365_acceptance_bundle.py --execution-mode dry-run --melix-cli .build/arm64-apple-macosx/debug/melix --output-dir .runtime/issue365/acceptance-dry-run --timestamp 2026-05-06T010000Z`:
  wrote a dry-run bundle with 10 succeeded cases, 0 failed cases, 0 blocked
  cases, and `release_ready=false`.
- `swift test --filter 'MelixCLIRunnerTests|MelixCLIParserTests'`:
  212 tests passed in 3 suites.

Results on 2026-05-06 after adding local publish, pipeline output-path
normalization, direct adapter activation, and the MLX stop-kwarg fix:

- `swift test --filter 'MelixCLIRunnerTests|MelixCLIParserTests'`:
  213 tests passed in 3 suites.
- `swift test --enable-code-coverage --filter 'MelixCLIRunnerTests|MelixCLIParserTests'`:
  213 tests passed in 3 suites and wrote Swift coverage data.
- `python3 scripts/swift_changed_line_coverage.py --binary .build/arm64-apple-macosx/debug/MelixPackageTests.xctest/Contents/MacOS/MelixPackageTests --profdata .build/arm64-apple-macosx/debug/codecov/default.profdata --diff-from origin/main Sources/MelixCLICore/MelixCLI.swift Sources/MelixCLICore/MelixCLICommandCodec.swift Sources/MelixCLICore/MelixPipelineRunner.swift tests/MelixCLITests/MelixCLIParserTests.swift tests/MelixCLITests/MelixCLIRunnerTests.swift docs/plans/2026-05-05-issue-365-cli-chain-routing.md`:
  99.44 percent total changed-line coverage, 880/885 executable lines.
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="$PWD/.uv-cache" uv run --project services/mlx-worker-python pytest -q tests/integration/test_issue365_acceptance_bundle.py`:
  13 passed.
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="$PWD/.uv-cache" uv run --project services/mlx-worker-python coverage run -m pytest -q tests/integration/test_issue365_acceptance_bundle.py services/mlx-worker-python/tests/test_maintenance_service.py services/mlx-worker-python/tests/test_mlx_backend.py`:
  196 passed.
- `python3 scripts/python_changed_line_coverage.py --coverage-json /tmp/issue365-cli-chain-routing-python-coverage.json --diff-from origin/main scripts/issue365_acceptance_bundle.py services/mlx-worker-python/worker/model_ops/upload_receipt_pipeline.py services/mlx-worker-python/worker/runtime/mlx_text_runtime.py services/mlx-worker-python/tests/test_maintenance_service.py services/mlx-worker-python/tests/test_mlx_backend.py tests/integration/test_issue365_acceptance_bundle.py docs/plans/2026-05-05-issue-365-cli-chain-routing.md`:
  97.65 percent total changed-line coverage, 582/596 executable lines.
- `MELIX_SERVICE_INSTANCE_NAME=issue365-real MELIX_HTTP_PORT=12465 MELIX_RUNTIME_DIR="$PWD/.runtime/sidecars/issue365-real" MELIX_HOME="$PWD/.runtime/home-issue365-real" MELIX_WORKER_SOCKET_PATH="/tmp/mx365-real-python.sock" MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH="/tmp/mx365-real-swift.sock" bash scripts/dev_up.sh --prefer-built`:
  started a named real local runtime stack.
- `MELIX_HOME="$PWD/.runtime/home-issue365-real" MELIX_WORKER_SOCKET_PATH="/tmp/mx365-real-python.sock" MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH="/tmp/mx365-real-swift.sock" MELIX_HTTP_PORT=12465 python3 scripts/issue365_acceptance_bundle.py --execution-mode real --case-id lora_export_inference --melix-cli "$PWD/.build/arm64-apple-macosx/debug/melix" --sft-dataset-uri "$PWD/services/mlx-worker-python/fixtures/training/melix-dev-dataset.v1" --output-dir .runtime/issue365/real-lora-final-probe --timestamp 2026-05-06T133000Z --json`:
  selected real case passed with `release_ready=true`; evidence bundle written
  to `.runtime/issue365/real-lora-final-probe/bundle.json`.
- The selected real local chain proved:
  `lora.train -> lora.publish(local_filesystem) -> lora.activate -> chat.run -> eval.run`.
- `MELIX_RUNTIME_DIR="$PWD/.runtime/sidecars/issue365-real" MELIX_WORKER_SOCKET_PATH="/tmp/mx365-real-python.sock" MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH="/tmp/mx365-real-swift.sock" bash scripts/dev_down.sh`:
  stopped the named real local runtime stack.
- `python3 scripts/issue365_acceptance_bundle.py --execution-mode dry-run --melix-cli .build/arm64-apple-macosx/debug/melix --output-dir .runtime/issue365/acceptance-dry-run-final --timestamp 2026-05-06T140000Z --json`:
  wrote a dry-run bundle with 10 succeeded cases, 0 failed cases, 0 blocked
  cases, and `release_ready=false`.
- `MELIX_SERVICE_INSTANCE_NAME=issue365-real-qlora MELIX_HTTP_PORT=12466 MELIX_RUNTIME_DIR="$PWD/.runtime/sidecars/issue365-real-qlora" MELIX_HOME="$PWD/.runtime/home-issue365-real-qlora" MELIX_WORKER_SOCKET_PATH="/tmp/mx365-real-qlora-python.sock" MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH="/tmp/mx365-real-qlora-swift.sock" bash scripts/dev_up.sh --prefer-built`:
  started a named real local runtime stack for the QLoRA subset.
- `MELIX_HOME="$PWD/.runtime/home-issue365-real-qlora" MELIX_WORKER_SOCKET_PATH="/tmp/mx365-real-qlora-python.sock" MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH="/tmp/mx365-real-qlora-swift.sock" MELIX_HTTP_PORT=12466 python3 scripts/issue365_acceptance_bundle.py --execution-mode real --case-id qlora_export_inference --melix-cli "$PWD/.build/arm64-apple-macosx/debug/melix" --sft-dataset-uri "$PWD/services/mlx-worker-python/fixtures/training/melix-dev-dataset.v1" --output-dir .runtime/issue365/real-qlora-probe --timestamp 2026-05-06T143000Z --json`:
  selected real QLoRA case passed with `release_ready=true`; evidence bundle
  written to `.runtime/issue365/real-qlora-probe/bundle.json`.
- The selected real local QLoRA chain proved:
  `lora.train -> lora.publish(local_filesystem) -> lora.activate -> chat.run -> eval.run`.
- `MELIX_RUNTIME_DIR="$PWD/.runtime/sidecars/issue365-real-qlora" MELIX_WORKER_SOCKET_PATH="/tmp/mx365-real-qlora-python.sock" MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH="/tmp/mx365-real-qlora-swift.sock" bash scripts/dev_down.sh`:
  stopped the named real local QLoRA runtime stack.
- `git diff --check`: passed.

Results on 2026-05-06 after adding preference batch comm-group sharding and
running the remaining supervised/preference real-mode subsets:

- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="$PWD/.uv-cache" uv run --project services/mlx-worker-python pytest -q tests/integration/test_issue365_acceptance_bundle.py services/mlx-worker-python/tests/test_maintenance_service.py services/mlx-worker-python/tests/test_mlx_backend.py services/mlx-worker-python/tests/test_lora_model_ops_unit.py`:
  273 passed with 2 warnings from MLX SWIG types.
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="$PWD/.uv-cache" uv run --project services/mlx-worker-python coverage run -m pytest -q tests/integration/test_issue365_acceptance_bundle.py services/mlx-worker-python/tests/test_maintenance_service.py services/mlx-worker-python/tests/test_mlx_backend.py services/mlx-worker-python/tests/test_lora_model_ops_unit.py`:
  273 passed with 2 warnings from MLX SWIG types.
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="$PWD/.uv-cache" uv run --project services/mlx-worker-python coverage json -o /tmp/issue365-cli-chain-routing-python-coverage.json`:
  wrote JSON coverage.
- `python3 scripts/python_changed_line_coverage.py --coverage-json /tmp/issue365-cli-chain-routing-python-coverage.json --diff-from origin/main scripts/issue365_acceptance_bundle.py services/mlx-worker-python/worker/model_ops/upload_receipt_pipeline.py services/mlx-worker-python/worker/runtime/mlx_text_runtime.py services/mlx-worker-python/worker/model_ops/preference_training.py services/mlx-worker-python/tests/test_maintenance_service.py services/mlx-worker-python/tests/test_mlx_backend.py services/mlx-worker-python/tests/test_lora_model_ops_unit.py tests/integration/test_issue365_acceptance_bundle.py docs/plans/2026-05-05-issue-365-cli-chain-routing.md`:
  97.74 percent total changed-line coverage, 605/619 executable lines.
- `MELIX_SERVICE_INSTANCE_NAME=issue365-real-dora MELIX_HTTP_PORT=12467 MELIX_RUNTIME_DIR="$PWD/.runtime/sidecars/issue365-real-dora" MELIX_HOME="$PWD/.runtime/home-issue365-real-dora" MELIX_WORKER_SOCKET_PATH="/tmp/mx365-real-dora-python.sock" MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH="/tmp/mx365-real-dora-swift.sock" bash scripts/dev_up.sh --prefer-built`:
  started a named real local runtime stack for the DoRA subset.
- `MELIX_HOME="$PWD/.runtime/home-issue365-real-dora" MELIX_WORKER_SOCKET_PATH="/tmp/mx365-real-dora-python.sock" MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH="/tmp/mx365-real-dora-swift.sock" MELIX_HTTP_PORT=12467 python3 scripts/issue365_acceptance_bundle.py --execution-mode real --case-id dora_export_inference --melix-cli "$PWD/.build/arm64-apple-macosx/debug/melix" --sft-dataset-uri "$PWD/services/mlx-worker-python/fixtures/training/melix-dev-dataset.v1" --output-dir .runtime/issue365/real-dora-probe --timestamp 2026-05-06T150000Z --json`:
  selected real DoRA case passed with `release_ready=true`; evidence bundle
  written to `.runtime/issue365/real-dora-probe/bundle.json`.
- `MELIX_RUNTIME_DIR="$PWD/.runtime/sidecars/issue365-real-dora" MELIX_WORKER_SOCKET_PATH="/tmp/mx365-real-dora-python.sock" MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH="/tmp/mx365-real-dora-swift.sock" bash scripts/dev_down.sh`:
  stopped the named real local DoRA runtime stack.
- `MELIX_SERVICE_INSTANCE_NAME=issue365-real-dpo MELIX_HTTP_PORT=12469 MELIX_RUNTIME_DIR="$PWD/.runtime/sidecars/issue365-real-dpo" MELIX_HOME="$PWD/.runtime/home-issue365-real-dpo" MELIX_WORKER_SOCKET_PATH="/tmp/mx365-real-dpo-python.sock" MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH="/tmp/mx365-real-dpo-swift.sock" bash scripts/dev_up.sh --prefer-built`:
  started a named real local runtime stack for preference alignment subsets.
- `MELIX_HOME="$PWD/.runtime/home-issue365-real-dpo" MELIX_WORKER_SOCKET_PATH="/tmp/mx365-real-dpo-python.sock" MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH="/tmp/mx365-real-dpo-swift.sock" MELIX_HTTP_PORT=12469 python3 scripts/issue365_acceptance_bundle.py --execution-mode real --case-id lora_dpo_export_inference --melix-cli "$PWD/.build/arm64-apple-macosx/debug/melix" --sft-dataset-uri "$PWD/services/mlx-worker-python/fixtures/training/melix-dev-dataset.v1" --preference-dataset-uri "$PWD/.runtime/issue365/input-datasets/preference_pair" --output-dir .runtime/issue365/real-dpo-probe-pass2 --timestamp 2026-05-06T153500Z --json`:
  selected real DPO case passed with `release_ready=true`; evidence bundle
  written to `.runtime/issue365/real-dpo-probe-pass2/bundle.json`.
- `MELIX_HOME="$PWD/.runtime/home-issue365-real-dpo" MELIX_WORKER_SOCKET_PATH="/tmp/mx365-real-dpo-python.sock" MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH="/tmp/mx365-real-dpo-swift.sock" MELIX_HTTP_PORT=12469 python3 scripts/issue365_acceptance_bundle.py --execution-mode real --case-id lora_orpo_export_inference --melix-cli "$PWD/.build/arm64-apple-macosx/debug/melix" --sft-dataset-uri "$PWD/services/mlx-worker-python/fixtures/training/melix-dev-dataset.v1" --preference-dataset-uri "$PWD/.runtime/issue365/input-datasets/preference_pair" --output-dir .runtime/issue365/real-orpo-probe --timestamp 2026-05-06T154500Z --json`:
  selected real ORPO case passed with `release_ready=true`; evidence bundle
  written to `.runtime/issue365/real-orpo-probe/bundle.json`.
- `MELIX_HOME="$PWD/.runtime/home-issue365-real-dpo" MELIX_WORKER_SOCKET_PATH="/tmp/mx365-real-dpo-python.sock" MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH="/tmp/mx365-real-dpo-swift.sock" MELIX_HTTP_PORT=12469 python3 scripts/issue365_acceptance_bundle.py --execution-mode real --case-id lora_cpo_export_inference --melix-cli "$PWD/.build/arm64-apple-macosx/debug/melix" --sft-dataset-uri "$PWD/services/mlx-worker-python/fixtures/training/melix-dev-dataset.v1" --preference-dataset-uri "$PWD/.runtime/issue365/input-datasets/preference_pair" --output-dir .runtime/issue365/real-cpo-probe --timestamp 2026-05-06T155500Z --json`:
  selected real CPO case passed with `release_ready=true`; evidence bundle
  written to `.runtime/issue365/real-cpo-probe/bundle.json`.
- `MELIX_RUNTIME_DIR="$PWD/.runtime/sidecars/issue365-real-dpo" MELIX_WORKER_SOCKET_PATH="/tmp/mx365-real-dpo-python.sock" MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH="/tmp/mx365-real-dpo-swift.sock" bash scripts/dev_down.sh`:
  stopped the named real local preference runtime stack.

Results on 2026-05-06 after routing quantize runtime smoke through public CLI
and pipeline options:

- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="$PWD/.uv-cache" uv run --project services/mlx-worker-python pytest -q tests/integration/test_issue365_acceptance_bundle.py`:
  13 passed.
- `swift test --filter 'MelixCLIParserTests|MelixCLIRunnerTests'`:
  213 tests passed in 3 suites.
- `swift test --enable-code-coverage --filter 'MelixCLIRunnerTests|MelixCLIParserTests'`:
  213 tests passed in 3 suites and wrote Swift coverage data.
- `python3 scripts/swift_changed_line_coverage.py --binary .build/arm64-apple-macosx/debug/MelixPackageTests.xctest/Contents/MacOS/MelixPackageTests --profdata .build/arm64-apple-macosx/debug/codecov/default.profdata --diff-from origin/main Sources/MelixCLICore/MelixCLI.swift Sources/MelixCLICore/MelixCLICommandCodec.swift Sources/MelixCLICore/MelixPipelineRunner.swift tests/MelixCLITests/MelixCLIParserTests.swift tests/MelixCLITests/MelixCLIRunnerTests.swift docs/plans/2026-05-05-issue-365-cli-chain-routing.md`:
  99.48 percent total changed-line coverage, 962/967 executable lines.
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="$PWD/.uv-cache" uv run --project services/mlx-worker-python coverage run -m pytest -q tests/integration/test_issue365_acceptance_bundle.py services/mlx-worker-python/tests/test_maintenance_service.py services/mlx-worker-python/tests/test_mlx_backend.py services/mlx-worker-python/tests/test_lora_model_ops_unit.py`:
  273 passed with 2 warnings from MLX SWIG types.
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="$PWD/.uv-cache" uv run --project services/mlx-worker-python coverage json -o /tmp/issue365-cli-chain-routing-python-coverage.json`:
  wrote JSON coverage.
- `python3 scripts/python_changed_line_coverage.py --coverage-json /tmp/issue365-cli-chain-routing-python-coverage.json --diff-from origin/main scripts/issue365_acceptance_bundle.py services/mlx-worker-python/worker/model_ops/upload_receipt_pipeline.py services/mlx-worker-python/worker/runtime/mlx_text_runtime.py services/mlx-worker-python/worker/model_ops/preference_training.py services/mlx-worker-python/tests/test_maintenance_service.py services/mlx-worker-python/tests/test_mlx_backend.py services/mlx-worker-python/tests/test_lora_model_ops_unit.py tests/integration/test_issue365_acceptance_bundle.py docs/plans/2026-05-05-issue-365-cli-chain-routing.md`:
  97.80 percent total changed-line coverage, 621/635 executable lines.
- `python3 scripts/issue365_acceptance_bundle.py --execution-mode plan --output-dir .runtime/issue365/acceptance-plan-runtime-smoke --timestamp 2026-05-06T170000Z --json`:
  wrote a plan bundle with 10 planned cases and `release_ready=false`.
- `python3 scripts/issue365_acceptance_bundle.py --execution-mode dry-run --melix-cli .build/arm64-apple-macosx/debug/melix --output-dir .runtime/issue365/acceptance-dry-run-runtime-smoke --timestamp 2026-05-06T170500Z --json`:
  wrote a dry-run bundle with 10 succeeded cases, 0 failed cases, 0 blocked
  cases, and `release_ready=false`.
- `MELIX_SERVICE_INSTANCE_NAME=issue365-real-ptq-runtime-smoke MELIX_HTTP_PORT=12472 MELIX_RUNTIME_DIR="$PWD/.runtime/sidecars/issue365-real-ptq-runtime-smoke" MELIX_HOME="$PWD/.runtime/home-issue365-real-ptq-runtime-smoke" MELIX_WORKER_SOCKET_PATH="/tmp/mx365-real-ptq-runtime-smoke-python.sock" MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH="/tmp/mx365-real-ptq-runtime-smoke-swift.sock" bash scripts/dev_up.sh --prefer-built`:
  started a named real local runtime stack for the PTQ runtime smoke probe.
- `MELIX_HOME="$PWD/.runtime/home-issue365-real-ptq-runtime-smoke" MELIX_WORKER_SOCKET_PATH="/tmp/mx365-real-ptq-runtime-smoke-python.sock" MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH="/tmp/mx365-real-ptq-runtime-smoke-swift.sock" MELIX_HTTP_PORT=12472 python3 scripts/issue365_acceptance_bundle.py --execution-mode real --case-id lora_preference_ptq_quantized_inference --melix-cli "$PWD/.build/arm64-apple-macosx/debug/melix" --sft-dataset-uri "$PWD/services/mlx-worker-python/fixtures/training/melix-dev-dataset.v1" --preference-dataset-uri "$PWD/.runtime/issue365/input-datasets/preference_pair" --calibration-dataset-uri "$PWD/.runtime/issue365/input-datasets/calibration" --output-dir .runtime/issue365/real-ptq-runtime-smoke-probe --timestamp 2026-05-06T171500Z --json`:
  failed as expected because the quantize step's `runtime_generate` local
  inference smoke did not pass; the selected case has `status=failed` and
  `release_ready=false`.
- `.runtime/issue365/real-ptq-runtime-smoke-probe/artifacts/ptq/model-ops-0015/quantize.artifact/manifest.json`:
  recorded `local_inference_smoke.evidence_kind=local_runtime_generate`,
  `local_inference_smoke.smoke_mode=runtime_generate`,
  `local_inference_smoke.status=failed`,
  `release_gate.local_inference_smoke_result=failed`, and failure reason
  `No safetensors found in .../quantize.artifact`.
- `MELIX_RUNTIME_DIR="$PWD/.runtime/sidecars/issue365-real-ptq-runtime-smoke" MELIX_WORKER_SOCKET_PATH="/tmp/mx365-real-ptq-runtime-smoke-python.sock" MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH="/tmp/mx365-real-ptq-runtime-smoke-swift.sock" bash scripts/dev_down.sh`:
  stopped the named PTQ runtime smoke stack.
- `find .runtime -type f \( -iname '*.png' -o -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.webp' \) -print`:
  passed with no generated screenshot artifacts found.
- `git diff --check`:
  passed.

Results on 2026-05-06 after routing the PTQ acceptance case through the real
MLX-LM conversion backend:

- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="$PWD/.uv-cache" uv run --project services/mlx-worker-python pytest -q tests/integration/test_issue365_acceptance_bundle.py`:
  13 passed.
- `swift test --filter 'MelixCLIParserTests|MelixCLIRunnerTests'`:
  229 tests passed in 3 suites. Existing `try await store.save` warnings
  remain.
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="$PWD/.uv-cache" uv run --project services/mlx-worker-python coverage run -m pytest -q tests/integration/test_issue365_acceptance_bundle.py`:
  13 passed.
- `swift test --enable-code-coverage --filter 'MelixCLIParserTests|MelixCLIRunnerTests'`:
  229 tests passed in 3 suites and wrote Swift coverage data.
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="$PWD/.uv-cache" uv run --project services/mlx-worker-python coverage json -o /tmp/issue365-ptq-runtime-python-coverage-r2.json`:
  wrote JSON coverage.
- `python3 scripts/python_changed_line_coverage.py --coverage-json /tmp/issue365-ptq-runtime-python-coverage-r2.json --diff-from origin/main scripts/issue365_acceptance_bundle.py tests/integration/test_issue365_acceptance_bundle.py docs/plans/2026-05-05-issue-365-cli-chain-routing.md`:
  100.00 percent total changed-line coverage, 8/8 executable lines.
- `python3 scripts/swift_changed_line_coverage.py --binary .build/arm64-apple-macosx/debug/melixPackageTests.xctest/Contents/MacOS/melixPackageTests --profdata .build/arm64-apple-macosx/debug/codecov/default.profdata --diff-from origin/main Sources/MelixCLICore/MelixCLI.swift Sources/MelixCLICore/MelixCLICommandCodec.swift Sources/MelixCLICore/MelixPipelineRunner.swift tests/MelixCLITests/MelixCLIParserTests.swift tests/MelixCLITests/MelixCLIRunnerTests.swift docs/plans/2026-05-05-issue-365-cli-chain-routing.md`:
  100.00 percent total changed-line coverage, 156/156 executable lines.
- `python3 scripts/issue365_acceptance_bundle.py --execution-mode plan --output-dir .runtime/issue365/ptq-backend-plan-r2 --timestamp 2026-05-06T183500Z --json`:
  wrote a plan bundle with 10 planned cases and `release_ready=false`; the PTQ
  pipeline now contains `ptq_fuse_merged_model`,
  `merged_model_path=${steps.ptq_fuse_merged_model.result.derived_model_path}`,
  `source_artifact_kind=merged_adapter`,
  `quantization_backend=mlx_lm_convert`, and `mlx_lm_q_mode=affine`.
- `python3 scripts/issue365_acceptance_bundle.py --execution-mode dry-run --melix-cli .build/arm64-apple-macosx/debug/melix --output-dir .runtime/issue365/ptq-backend-dry-run-r2 --timestamp 2026-05-06T184000Z --json`:
  wrote a dry-run bundle with 10 succeeded cases, 0 failed cases, 0 blocked
  cases, and `release_ready=false`.
- `swift build --package-path services/mlx-text-worker-swift`:
  built the Swift text worker for `--prefer-built`; existing third-party MLX
  deprecation warnings and Swift concurrency warnings remain.
- `swift build --package-path services/control-plane-swift`:
  built the control plane for `--prefer-built`.
- `MELIX_SERVICE_INSTANCE_NAME=issue365-ptq-backend-real MELIX_HTTP_PORT=12473 MELIX_RUNTIME_DIR="$PWD/.runtime/sidecars/issue365-ptq-backend-real" MELIX_HOME="$PWD/.runtime/home-issue365-ptq-backend-real" MELIX_WORKER_SOCKET_PATH="/tmp/mx365-ptq-backend-real-python.sock" MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH="/tmp/mx365-ptq-backend-real-swift.sock" bash scripts/dev_up.sh --prefer-built`:
  started a named real local runtime stack for the PTQ backend probe.
- `MELIX_HOME="$PWD/.runtime/home-issue365-ptq-backend-real" MELIX_WORKER_SOCKET_PATH="/tmp/mx365-ptq-backend-real-python.sock" MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH="/tmp/mx365-ptq-backend-real-swift.sock" MELIX_HTTP_PORT=12473 python3 scripts/issue365_acceptance_bundle.py --execution-mode real --case-id lora_preference_ptq_quantized_inference --melix-cli "$PWD/.build/arm64-apple-macosx/debug/melix" --sft-dataset-uri "$PWD/services/mlx-worker-python/fixtures/training/melix-dev-dataset.v1" --preference-dataset-uri "$PWD/.runtime/issue365/input-datasets/preference_pair" --calibration-dataset-uri "$PWD/.runtime/issue365/input-datasets/calibration" --output-dir .runtime/issue365/ptq-backend-real-probe-r2 --timestamp 2026-05-06T182500Z --json`:
  selected real PTQ case passed with `release_ready=true`; evidence bundle
  written to `.runtime/issue365/ptq-backend-real-probe-r2/bundle.json`.
- `.runtime/issue365/ptq-backend-real-probe-r2/receipts/lora_preference_ptq_quantized_inference/steps/005-ptq_quantize.json`:
  recorded `execution_backend=mlx_lm_convert`, `real_weight_conversion=true`,
  `source_artifact_kind=merged_adapter`, `local_inference_smoke.status=passed`,
  `local_inference_smoke.evidence_kind=local_runtime_generate`,
  `release_gate.local_inference_smoke_result=passed`, and checked
  `config.json`, `tokenizer.json`, and `model.safetensors`.
- `find .runtime/issue365/ptq-backend-real-probe-r2/artifacts/ptq -maxdepth 4 -type f | sort`:
  confirmed the quantized artifact includes `model.safetensors`,
  `model.safetensors.index.json`, `config.json`, `tokenizer.json`,
  `tokenizer_config.json`, and `manifest.json`.
- `MELIX_RUNTIME_DIR="$PWD/.runtime/sidecars/issue365-ptq-backend-real" MELIX_WORKER_SOCKET_PATH="/tmp/mx365-ptq-backend-real-python.sock" MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH="/tmp/mx365-ptq-backend-real-swift.sock" bash scripts/dev_down.sh`:
  stopped the named PTQ backend runtime stack.

Results on 2026-05-05 after adding the acceptance bundle harness:

- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="$PWD/.uv-cache" uv run --project services/mlx-worker-python pytest -q tests/integration/test_issue365_acceptance_bundle.py`:
  9 passed.
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="$PWD/.uv-cache" uv run --project services/mlx-worker-python coverage run -m pytest -q tests/integration/test_issue365_acceptance_bundle.py`:
  9 passed.
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="$PWD/.uv-cache" uv run --project services/mlx-worker-python coverage json -o /tmp/issue365-cli-acceptance-bundle-coverage.json`:
  wrote JSON coverage.
- `python3 scripts/python_changed_line_coverage.py --coverage-json /tmp/issue365-cli-acceptance-bundle-coverage.json --diff-from origin/main scripts/issue365_acceptance_bundle.py tests/integration/test_issue365_acceptance_bundle.py docs/plans/2026-05-05-issue-365-cli-chain-routing.md`:
  99.37 percent total changed-line coverage, 316/318 executable lines.
- `python3 scripts/issue365_acceptance_bundle.py --execution-mode plan --output-dir .runtime/issue365/acceptance-smoke --timestamp 2026-05-05T000000Z --json`:
  wrote a plan bundle with 10 planned cases and `release_ready=false`.
- `python3 scripts/issue365_acceptance_bundle.py --execution-mode dry-run --melix-cli .build/arm64-apple-macosx/debug/melix --output-dir .runtime/issue365/acceptance-dry-run --timestamp 2026-05-05T000000Z --json`:
  passed with 10 succeeded dry-run cases, 0 failures, and
  `release_ready=false`.
- `swift test --filter 'MelixCLIRunnerTests|MelixCLIParserTests'`:
  212 tests passed in 3 suites. Existing `try await store.save` warnings
  remain.
- `git diff --check`: passed.

## Remaining Issue 365 Gaps

- Real GRPO policy-runtime candidate generation, scoring, and policy updates.
- RLHF reward-model inference and PPO/reward-guided update integration from
  issue 366.
- QAT training and QAT-aware quantized export.
- Full CLI chain tests backed by real local runtime evidence for every listed
  business line.
- Real local runtime evidence now exists for `lora_export_inference`,
  `qlora_export_inference`, `dora_export_inference`,
  `lora_dpo_export_inference`, `lora_orpo_export_inference`,
  `lora_cpo_export_inference`, and
  `lora_preference_ptq_quantized_inference`, but the remaining three CLI
  chains still require real local runtime evidence:
  `lora_grpo_export_inference`, `lora_rlhf_export_inference`, and
  `qat_quantized_inference`.
- Window UI runnable/inspectable acceptance for every listed business line.
- Final release evidence that separates deterministic/unit/scored-trace results
  from real local runtime results.
