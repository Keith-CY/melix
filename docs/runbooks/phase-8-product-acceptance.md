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
```

Use these as the final repository verification gate for LoRA, benchmark, and CLI productization
in addition to the release-gate and metrics commands below.

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
- [x] Serveable-model filtering for `Server Session` binding and start-time validation.
- [x] `Server Session` create, update, remove, select, start, pause, resume, wake, stop, and unavailable-binding preservation.
- [x] CLI-first server-session rebinding and `chat run` execution against managed base or derived models without `MELIX_DEV_TEXT_MODEL_PATH`.
- [x] Shared CLI-core execution for LoRA train and activate, benchmark, matrix benchmark, evaluation, export, and acceptance-bundle orchestration.
- [x] Window UI subprocess-backed CLI shell coverage for managed Hub download, local import, server-session mutation and start, LoRA train and activate, benchmark, matrix benchmark, evaluation, and export.

### Bucket 2: Implemented But Pending Live Acceptance Revalidation

These flows exist in code, but still need fresh real-runtime acceptance evidence before
release sign-off:

- [x] Run one real desktop flow for `download -> registry refresh -> Server Session select -> server start` through the native Window UI CLI subprocess bridge using a downloaded Hugging Face text model without fallback environment model-path injection.

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
- [x] The live Window UI bundle records `selected_surface=Server`, `selected_server_session_id=server-session-1`, `lora_train_job_id=model-ops-0137`, `lora_activate_job_id=model-ops-0141`, `bench_job_id=model-ops-0149`, `bench_matrix_job_id=model-ops-0154`, and `evaluation_job_id=eval-0004`; see `progress.md` for the exact measured timings.

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
