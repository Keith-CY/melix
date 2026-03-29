# Phase 6 Multimodal Operator Workflow

## Trigger

Use this runbook when you need to:

- boot the Phase 6 stack and exercise OCR, VLM, transcription, and speech end to end
- capture the reproducible Phase 6 latency and preprocessing report
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

3. Confirm that the control plane exposes the expected local models.

```bash
curl -sS http://127.0.0.1:11434/v1/models
```

4. Run the reproducible Phase 6 metrics command.

```bash
make phase6-metrics
```

5. Inspect the runtime directory and logs if any multimodal path fails.

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

## Recovery

1. Stop the stack and clear stale runtime metadata.

```bash
MELIX_RUNTIME_DIR=.runtime/phase6-ops bash scripts/dev_down.sh
```

2. Reboot the deterministic path and rerun the metrics command.

```bash
MELIX_RUNTIME_DIR=.runtime/phase6-ops \
MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE=deterministic \
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
MELIX_RUNTIME_DIR=.runtime/phase6-ops bash scripts/dev_down.sh
```
