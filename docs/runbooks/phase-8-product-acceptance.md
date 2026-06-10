# Phase 8 Product Acceptance

## Purpose

Run the end-of-phase product acceptance flow for Melix and capture the final metrics report.

## Repository Verification

Before claiming productization completion, run the repository-owned verification commands:

```bash
make proto
make py-test
make swift-test
make integration-test
make coverage
```

Use these as the final repository verification gate for LoRA, benchmark, and CLI productization
in addition to the release-gate and metrics commands below.

Run the repository-owned deterministic acceptance smokes as part of the same gate:

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" \
uv run --project services/mlx-worker-python --extra mlx python scripts/phase8_lora_cli_smoke.py --json
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" \
uv run --project services/mlx-worker-python --extra mlx python scripts/phase8_lora_window_smoke.py --json
```

## Install Or Upgrade

Generate or refresh the local product assets:

```bash
python3 scripts/install_local_product.py --json
```

Bootstrap the generated launch agents:

```bash
launchctl bootstrap gui/$(id -u) "$HOME/Library/LaunchAgents/io.melix.swift-text-worker.plist"
launchctl bootstrap gui/$(id -u) "$HOME/Library/LaunchAgents/io.melix.python-worker.plist"
launchctl bootstrap gui/$(id -u) "$HOME/Library/LaunchAgents/io.melix.control-plane.plist"
```

## Roll Back

To roll back to a previous repository revision:

1. `python3 scripts/uninstall_local_product.py`
2. check out the target revision
3. rerun `python3 scripts/install_local_product.py --json`
4. bootstrap the generated launch agents again

## Diagnostics And Training

Run the deterministic release gate:

```bash
make phase8-release-gate PHASE8_RELEASE_GATE_ARGS="--json"
```

This verifies:

- install evidence
- benchmark thresholds
- restart recovery
- runtime-core multi-model evidence
- runtime-core memory-guard evidence
- training sanity
- M9 ecosystem and security evidence, including closure-audit blockers and release-gate probe coverage

For the manual LoRA operator workflow, use `docs/runbooks/phase-8-lora-adapter-workflow.md`.

## CLI Pipeline v1

The preferred machine-oriented acceptance entry point is now the typed CLI pipeline runner:

```bash
melix pipeline run \
  --file docs/examples/pipelines/phase8-acceptance.pipeline.json \
  --inputs /path/to/phase8-inputs.json \
  --trace-id phase8-$(date -u +%Y%m%dT%H%M%SZ) \
  --format json-v1
```

Use `--dry-run --format json-v1` first to validate command planning and receipt paths without
executing model operations. Dry-run resolves input references and any step references backed by
already loaded receipts; references to future steps remain literal `${steps...}` strings in planned
arguments. Use `--receipt-dir PATH` when CI needs receipts in a workspace-owned artifact directory.
Use `--resume` only when the prior summary manifest has matching pipeline and input hashes and the
step receipts still match the current step metadata. Use `--from-step STEP_ID` to reload earlier
step receipts and rerun a downstream section after fixing local state.

Each pipeline run writes:

- one `melix.cli.output.v1` or `melix.cli.error.v1` receipt per step
- a `melix.pipeline.run.v1` summary manifest with pipeline hash, input hash, step status, receipt
  paths, step-level `artifact_paths`, and pipeline metrics

Successful step receipts include `pipeline_step` metadata with the step ID, index, command ID,
pipeline hash, input hash, and resolved-argument hash. Resume and from-step recovery validate this
metadata before reusing a receipt; stale, swapped, or schema-incompatible receipts fail fast and
write a failed summary manifest.

Keep `scripts/phase8_acceptance_bundle.py` working during v1. The pipeline runner becomes the
default Phase 8 acceptance path only after deterministic integration coverage proves parity with
the scripted bundle flow.

Keep pipeline verification deterministic by default. CI should use the pipeline tests and dry-run
sample to validate typed command planning, reference resolution, receipts, resume behavior, and
summary artifacts without requiring a live model. Preserve live model and live runtime coverage as
explicit acceptance gates: use `MELIX_PHASE8_REAL_SMALL_MODEL_E2E=1` for the real Phase 8
small-model path, and use `MELIX_RUN_LIVE_RUNTIME_TESTS=1` when running CLI smoke tests that
depend on local worker sockets.

## Latest Deterministic Acceptance Evidence

Recorded on 2026-04-09. This evidence closes the repository-owned deterministic acceptance gate.
Bucket 2 below still tracks the remaining live-runtime revalidation work.

- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python --extra mlx coverage run --data-file /tmp/phase4-python.coverage --source=scripts,tests/integration,services/mlx-worker-python/tests -m pytest services/mlx-worker-python/tests/test_phase8_lora_smoke_scripts.py services/mlx-worker-python/tests/test_m15_desktop_polish_smoke_script.py services/mlx-worker-python/tests/test_m9_agent_export_smoke.py tests/integration/test_phase8_lora_cli_smoke.py tests/integration/test_phase8_lora_window_smoke.py tests/integration/test_desktop_polish_smoke.py tests/integration/test_disk_streaming_smoke.py tests/integration/test_queue_pressure.py tests/integration/test_session_lifecycle_integration.py -q`
  -> `18 passed in 207.07s`
- `python3 scripts/python_changed_line_coverage.py --coverage-json /tmp/phase4-python-coverage.json scripts/m15_desktop_polish_smoke.py scripts/m9_agent_export_smoke.py scripts/phase8_lora_cli_smoke.py scripts/phase8_lora_window_smoke.py services/mlx-worker-python/tests/test_m15_desktop_polish_smoke_script.py services/mlx-worker-python/tests/test_m9_agent_export_smoke.py services/mlx-worker-python/tests/test_phase8_lora_smoke_scripts.py tests/integration/helpers.py tests/integration/test_disk_streaming_smoke.py tests/integration/test_phase8_lora_cli_smoke.py tests/integration/test_phase8_lora_window_smoke.py tests/integration/test_queue_pressure.py tests/integration/test_session_lifecycle_integration.py`
  -> `97.13% (305/314)` changed-line coverage across the touched Python scope
- `python3 scripts/swift_changed_line_coverage.py ...`
  -> changed-line Swift coverage across the touched executable scope:
  root CLI `98.12% (835/851)`,
  Window UI `98.22% (883/899)`,
  control plane `96.25% (231/240)`,
  aggregate `97.94% (1949/1990)`
- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python --extra mlx python scripts/phase8_lora_cli_smoke.py --json`
  -> passed with fixed `model_id == mlx-community/Qwen3.5-0.8B-OptiQ-4bit` and positive
  `train`, `activate`, `compare`, `export`, and `remove_derived` acceptance coverage plus
  negative missing-argument checks
- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python --extra mlx python scripts/phase8_lora_window_smoke.py --json`
  -> passed with the same fixed model ID, positive and negative Window acceptance coverage, and
  rendered controls `QLoRA`, `Adapter-backed Runtime`, `Run Comparison`, and
  `Remove Derived Model`
- `make phase8-metrics PHASE8_METRICS_ARGS="--json"`
  -> completed with `release_gate.passed == true`,
  `release_gate.m9_missing_probe_count == 0`,
  `release_gate.m9_failed_threshold_count == 0`, and
  `runtime.multi_model_ready_count == 3`

## Model Management Status Buckets

As of 2026-04-09, track model-management acceptance in three buckets so release decisions
do not blur code-complete surfaces, pending live validation, and open product gaps.

### Bucket 1: Implemented And Test-Covered

Treat regressions in these flows as bugs, not as future roadmap work:

- [x] Hugging Face search, model-card inspection, MLX-only filtering, and managed-import download.
- [x] First-class local model import into managed storage with a shared machine-readable managed-model receipt shape.
- [x] Ordered registry-root management, including `list`, `add`, `remove`, `move`, `rescan`, and managed-root precedence.
- [x] Registry-driven model library flows for `list`, `inspect`, `load`, and `unload`.
- [x] Download-queue hydration, status rendering, and resumable download recovery.
- [x] Serveable-model filtering for `Provider` binding and start-time validation.
- [x] `Provider` create, update, remove, select, start, pause, resume, wake, stop, and unavailable-binding preservation.
- [x] CLI-first provider rebinding and `chat run` execution against managed base or derived models without `MELIX_DEV_TEXT_MODEL_PATH`.
- [x] Shared CLI-core execution for LoRA train, activate, remove-derived, benchmark, matrix benchmark, evaluation, evaluation compare, and export actions.
- [x] Shared CLI-core execution for LoRA train, activate, remove-derived, benchmark, matrix benchmark, evaluation, evaluation compare, export, and acceptance-bundle orchestration.
- [x] Window UI subprocess-backed CLI shell coverage for managed Hub download, local import, provider mutation and start, LoRA train, activate, remove-derived, benchmark, matrix benchmark, evaluation, evaluation compare, and export.
- [x] Production Window UI uses the public `melix` subprocess path while test-only Window acceptance uses the shared CLI runner seam directly.
- [x] Repository-owned deterministic LoRA CLI acceptance smoke exists at `scripts/phase8_lora_cli_smoke.py`.
- [x] Repository-owned deterministic LoRA Window acceptance smoke exists at `scripts/phase8_lora_window_smoke.py`.

### Bucket 2: Implemented But Pending Live Acceptance Revalidation

These flows exist in code, but still need fresh real-runtime acceptance evidence before
release sign-off:

- [x] Run one real desktop flow for `download -> registry refresh -> Provider select -> server start` through the native Window UI CLI subprocess bridge using a downloaded Hugging Face text model without fallback environment model-path injection.

### Live CLI Evidence Captured

- [x] The repository-owned CLI acceptance bundle was re-run live on `2026-04-09T162920Z`.
- [x] The live CLI bundle records one base-model chat run and one derived-model chat run against `mlx-community/Qwen3.5-0.8B-OptiQ-4bit`.
- [x] The live CLI bundle records the exact model ID, dataset ID, benchmark suites, evaluation suite, LoRA job ID, matrix benchmark job ID, evaluation job ID, and exported artifact paths for the real acceptance run.
- [x] Live LoRA training, benchmark, matrix benchmark, evaluation, and export flows completed through the public `melix` CLI contract; see `progress.md` for the exact evidence path and measured timings.

### Live Window UI Evidence Captured

- [x] The repository-owned native Window UI acceptance bundle and screenshot were captured live on `2026-04-09T192003Z`.
- [x] The live Window UI bundle records one base-model chat run and one derived-model chat run against the approved model `mlx-community/Qwen3.5-0.8B-OptiQ-4bit`.
- [x] The live Window UI evidence bundle is preserved at `/Users/ChenYu/Library/Application Support/Melix/acceptance/phase8/window-ui/2026-04-09T192003Z/bundle.json`.
- [x] The live Window UI screenshot is preserved at `/Users/ChenYu/Library/Application Support/Melix/acceptance/phase8/window-ui/2026-04-09T192003Z/window-ui.png`.
- [x] The live Window UI bundle chains back to the live CLI evidence bundle at `/Users/ChenYu/Library/Application Support/Melix/acceptance/phase8/cli/2026-04-09T162920Z/bundle.json`.
- [x] The live Window UI bundle records `selected_surface=Server`, `selected_provider_id=provider-1`, `lora_train_job_id=model-ops-0137`, `lora_activate_job_id=model-ops-0141`, `bench_job_id=model-ops-0149`, `bench_matrix_job_id=model-ops-0154`, and `evaluation_job_id=eval-0004`; see `progress.md` for the exact measured timings.

### Bucket 3: Open Product Gaps

These remain roadmap items rather than closed product behavior:

- [x] Preserve a repository-owned Window UI acceptance evidence bundle and screenshot chain from the native CLI-backed surface.

## Final Metrics Report

Generate the final product metrics report:

```bash
make phase8-metrics PHASE8_METRICS_ARGS="--json"
```

The report includes:

- cold boot to ready
- Swift text worker spawn-to-ready latency
- Swift text worker spawn-to-bootstrap latency
- Swift text worker registry initialization latency
- Swift text worker service wiring latency
- Swift text worker server construction latency
- Swift text worker bootstrap latency
- Python worker spawn-to-ready latency
- Python worker spawn-to-bootstrap latency
- Python worker argument parsing latency
- Python worker registry initialization latency
- Python worker server construction latency
- Python worker server start latency
- Python worker bootstrap latency
- control-plane spawn-to-ready latency
- HTTP ready latency
- background preload latency
- first text-model warm latency
- first text-model estimated resident bytes
- first text-model resident bytes
- runtime-core multi-model ready count
- runtime-core multi-model request success rate
- runtime-core prefill memory-guard rejection count
- runtime-core prefill memory-guard success rate
- operator action latency
- install success rate
- benchmark regression percentage
- smoke pass rate
- M9 required probe count
- M9 missing probe count
- M9 failed threshold count
- closure-audit blocker count
- closure-audit accepted-risk count
- closure-audit evidence-gap count
- closure-audit deferred-work count
- training duration
- adapter publish latency
- restart-to-ready latency
- restart Swift text worker spawn-to-ready latency
- restart Python worker spawn-to-ready latency
- restart control-plane spawn-to-ready latency
- snapshot restore latency
- restart recovery latency and success

## Recovery

If the local stack needs to be reinstalled or reset:

```bash
python3 scripts/uninstall_local_product.py --prune
python3 scripts/install_local_product.py --json
```

Then rerun:

```bash
make phase8-release-gate PHASE8_RELEASE_GATE_ARGS="--json"
make phase8-metrics PHASE8_METRICS_ARGS="--json"
```

When debugging the release decision, also run the deterministic M9-only smoke fixtures:

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" \
uv run --project services/mlx-worker-python python scripts/m9_release_gate_smoke.py --repo-root "$(pwd)" --json
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" \
uv run --project services/mlx-worker-python python scripts/m9_release_gate_smoke.py --repo-root "$(pwd)" --fixture-mode failing --json
```
