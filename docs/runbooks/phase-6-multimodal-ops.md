# Phase 6 Multimodal Operator Workflow

## Trigger

Use this runbook when you need to:

- boot the Phase 6 stack and exercise OCR, VLM, transcription, and speech end to end
- capture the reproducible Phase 6 latency and preprocessing report
- inspect the repository-owned machine-readable vision evidence report
- verify that multimodal work stays observable while text remains responsive

## Preconditions

- macOS on Apple Silicon
- `make bootstrap` has completed successfully
- `make proto` has completed successfully
- `make swift-test` and `make py-test` are green

## Diagnosis

1. Refresh the local build and generated protocol artifacts.

```bash
make bootstrap
make proto
make swift-test
make py-test
```

2. Start a fresh local stack under a dedicated Phase 6 runtime directory.

```bash
MELIX_RUNTIME_DIR=.runtime/phase6-ops bash scripts/dev_up.sh
```

This starts the default real backend path. Deterministic execution remains available only as an explicit fixture when you need repeatable isolation.

3. Confirm that the control plane exposes the expected local models.

```bash
curl -sS http://127.0.0.1:11434/v1/models
```

4. Run the reproducible Phase 6 metrics command.

```bash
make phase6-metrics
```

5. Run the repository-owned machine-readable vision evidence test when you need the stable `checks` and `metrics` payload.

```bash
PYTHONPATH=.:services/mlx-worker-python \
uv run --project services/mlx-worker-python \
pytest tests/integration/test_phase6_operator_workflows.py -k machine_readable -q
```

6. Inspect the runtime directory and logs if any multimodal path fails.

```bash
ls -la .runtime/phase6-ops
tail -n 50 .runtime/phase6-ops/control-plane.log
tail -n 50 .runtime/phase6-ops/python-worker.log
tail -n 50 .runtime/phase6-ops/swift-text-worker.log
```

## Expected Evidence

- `ocr` line reports request latency plus preprocessing latency and peak memory
- `vlm` line reports request latency, first-token latency, and preprocessing memory
- `transcription` line reports request latency, preprocessing memory, duration, and chunk count
- `speech` line reports request latency and output bytes
- `text_under_multimodal` line reports a non-`N/A` text TTFT measurement recorded while transcription load is active

## Machine-Readable Evidence

The repository-owned report builder is `worker.productization.build_phase6_vision_metrics_report`.

The integration evidence path validates these `checks` keys:

- `vision.ingress.local_image_success`
- `vision.ingress.remote_image_success`
- `vision.ingress.multi_image_success`
- `vision.ocr.default_stop_success`
- `vision.vlm.tool_call_success`

The matching `metrics` payload includes:

- `vision.integration_success_rate`
- `vision.ocr.request_latency_ms`
- `vision.vlm.request_latency_ms`
- `vision.ocr_latency_ms`
- `vision.vlm_first_token_ms`
- `vision.preprocess_latency_ms`
- `vision.preprocess_peak_memory_bytes`
- `vision.cache_memory_bytes`
- `vision.cache_hit_rate`

## Recovery

1. Stop the stack and clear stale runtime metadata.

```bash
MELIX_RUNTIME_DIR=.runtime/phase6-ops bash scripts/dev_down.sh
```

2. If live-model availability is the suspected blocker, reboot with explicit deterministic overrides and rerun the metrics command.

```bash
MELIX_RUNTIME_DIR=.runtime/phase6-ops \
MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE=deterministic \
MELIX_BACKEND_MODE=deterministic \
bash scripts/dev_up.sh
make phase6-metrics
```

3. Use the native Chat panel only after the control plane reports warm models.

```bash
swift run --package-path apps/macos-menubar melix-menubar
```

## Verification

```bash
make swift-test
make py-test
make integration-test
make coverage
make phase6-metrics
PYTHONPATH=.:services/mlx-worker-python uv run --project services/mlx-worker-python pytest tests/integration/test_phase6_operator_workflows.py -k machine_readable -q
MELIX_RUNTIME_DIR=.runtime/phase6-ops bash scripts/dev_down.sh
```
