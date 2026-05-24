# Phase 6 Multimodal Operator Workflow

## Trigger

Use this runbook when you need to:

- boot the Phase 6 stack and exercise OCR, VLM, transcription, and speech end to end
- capture the reproducible Phase 6 latency and preprocessing report
- inspect the repository-owned machine-readable vision evidence report
- verify that multimodal work stays observable while text remains responsive
- confirm VLM fast-path admission, fallback, and image-feature cache evidence

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
curl -sS http://127.0.0.1:12436/v1/models
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

6. Run a VLM benchmark when you need batch-1 decode, repeated-image, scatter, and quantized-load fast-path metric evidence.

```bash
PYTHONPATH=.:services/mlx-worker-python \
uv run --project services/mlx-worker-python \
python -m pytest services/mlx-worker-python/tests/test_maintenance_service.py -k vlm_mode -q
```

For live throughput claims, run the same benchmark command against the selected
real VLM model before and after the change and archive both benchmark artifacts.
Deterministic runs prove evidence shape and fallback behavior only.

7. Inspect the runtime directory and logs if any multimodal path fails.

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
- VLM benchmark output includes image-feature cache hits/misses, decode-mode code, fallback-reason code, decode-sync-mode code, scatter-mode code, quantized-load-mode code, and quantized-load fallback-reason code

## Machine-Readable Evidence

The repository-owned report builder is `worker.productization.build_phase6_vision_metrics_report`.

The integration evidence path validates these `checks` keys:

- `vision.ingress.local_image_success`
- `vision.ingress.remote_image_refusal_success`
- `vision.ingress.multi_image_success`
- `vision.ocr.default_stop_success`
- `vision.vlm.tool_rejection_success`

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
- `vision.image_feature_cache_hits`
- `vision.image_feature_cache_misses`
- `vision.multimodal_decode_mode`
- `vision.multimodal_fallback_reason`
- `vision.multimodal_decode_sync_mode`
- `vision.multi_image_scatter_mode`
- `vision.quantized_load_mode`
- `vision.quantized_load_fallback_reason`

The fast-path categorical values are preserved as strings in the phase-6 evidence
JSON. VLM benchmark output uses numeric code metrics with the same metric names
because benchmark metric rows are numeric. The live control-plane metrics export
continues to use the existing numeric `RuntimeStats` bridge; adding string
runtime-stat fields would require a separate protobuf change and is intentionally
out of scope for the Issue 42 first stage.

An empty fallback-reason string means the fast path succeeded without fallback.
`not_reported` means no probe was available. Per-sample cache counters use `-1`
for missing probes, but aggregate benchmark hit/miss metrics exclude those
sentinel values so mixed probed/unprobed suites do not produce negative totals.

For VLM benchmark suites with heterogeneous samples, categorical fast-path
metrics report a distinct mixed code when more than one value is observed. For
`bench.<suite>.multimodal_decode_mode`, the mixed code is `5.0`; homogeneous
suites keep the baseline `0.0`, `single_stream` `1.0`, `image_cache_reuse`
`2.0`, `native_quantized` `3.0`, and `fallback` `4.0` codes.

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
