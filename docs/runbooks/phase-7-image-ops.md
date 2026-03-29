# Phase 7 Image Operator Workflow

## Trigger

Use this runbook when you need to:

- boot the Phase 7 stack and exercise image generation plus image editing end to end
- reproduce queueing, cancellation, and text-under-image-load evidence
- capture the reproducible Phase 7 latency, artifact-publish, and peak-memory report

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

2. Start a fresh local stack under a dedicated Phase 7 runtime directory.

```bash
MELIX_RUNTIME_DIR=.runtime/phase7-ops bash scripts/dev_up.sh
```

3. Confirm that the control plane exposes the expected local image model.

```bash
curl -sS http://127.0.0.1:11434/v1/models
```

4. Run the reproducible Phase 7 metrics command.

```bash
make phase7-metrics
```

5. Inspect the runtime directory and logs if any image path fails.

```bash
ls -la .runtime/phase7-ops
tail -n 50 .runtime/phase7-ops/control-plane.log
tail -n 50 .runtime/phase7-ops/python-worker.log
tail -n 50 .runtime/phase7-ops/swift-text-worker.log
```

## Expected Evidence

- `image_generate` reports request latency, job latency, artifact publish latency, peak memory, and output bytes
- `image_edit` reports request latency, job latency, artifact publish latency, and peak memory
- `image_queue` reports a non-zero queue wait after a follower request waits behind a slower image job
- `text_under_image` reports a non-`N/A` TTFT measurement while image work is active
- `image_cancel` reports a successful cancel attempt and a `409` cancelled terminal response

## Recovery

1. Stop the stack and clear stale runtime metadata.

```bash
MELIX_RUNTIME_DIR=.runtime/phase7-ops bash scripts/dev_down.sh
```

2. Reboot the deterministic path and rerun the metrics command.

```bash
MELIX_RUNTIME_DIR=.runtime/phase7-ops \
MELIX_DETERMINISTIC_IMAGE_DELAY_MS=120 \
bash scripts/dev_up.sh
make phase7-metrics
```

3. Use the native Image panel only after the control plane reports warm models.

```bash
swift run --package-path apps/macos-menubar melix-menubar
```

## Verification

```bash
make swift-test
make py-test
make integration-test
make coverage
make phase7-metrics
MELIX_RUNTIME_DIR=.runtime/phase7-ops bash scripts/dev_down.sh
```
