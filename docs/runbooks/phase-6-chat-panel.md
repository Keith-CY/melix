# Phase 6 Native Chat Panel

## Trigger

Use this runbook when you need to:

- boot the local Phase 6 stack and exercise the native Chat panel
- verify that desktop chat requests flow through the control plane instead of a worker-direct path
- confirm reasoning and tool-call deltas appear in the transcript
- inspect route readiness for text, OCR, VLM, transcription, and speech-capable models

## Preconditions

- macOS on Apple Silicon
- `make bootstrap` has completed successfully
- `make proto` has completed successfully
- `uv`, `swift`, `protoc`, and `protoc-gen-swift` are available
- the Phase 6 stack can already serve `/v1/models`

## Diagnosis

1. Confirm the repository bootstrap is current.

```bash
make bootstrap
make proto
```

2. Start a fresh local stack under a Phase 6 runtime directory.

```bash
MELIX_RUNTIME_DIR=.runtime/phase6 bash scripts/dev_up.sh
```

3. Confirm the control plane can see the expected local models.

```bash
curl -sS http://127.0.0.1:11434/v1/models
```

4. Launch the native desktop shell.

```bash
swift run --package-path apps/macos-menubar melix-menubar
```

5. Open the `Chat` tab and submit a prompt against the default text model.
   - Confirm the transcript records the user prompt and assistant output.
   - Confirm reasoning and tool-call sections appear when the runtime emits those deltas.
   - Confirm the `Analysis Routes` section reflects current OCR, VLM, transcription, and speech readiness from the latest snapshot.

6. Inspect the Phase 6 runtime directory when the panel does not update.

```bash
ls -la .runtime/phase6
tail -n 50 .runtime/phase6/control-plane.log
tail -n 50 .runtime/phase6/python-worker.log
tail -n 50 .runtime/phase6/swift-text-worker.log
```

## Common Causes

- The local stack was started without the `MELIX_RUNTIME_DIR=.runtime/phase6` override, so the operator is reading the wrong logs.
- The text model is not warm, so the control plane cannot route the desktop chat request.
- The desktop app was started before the control plane or workers were ready.
- The local model snapshot does not expose multimodal capability classes, so the route-readiness section remains empty.

## Recovery

1. Stop the stack and clear stale Phase 6 runtime metadata.

```bash
MELIX_RUNTIME_DIR=.runtime/phase6 bash scripts/dev_down.sh
```

2. Restart the deterministic path first and confirm `/v1/models` is healthy.

```bash
MELIX_RUNTIME_DIR=.runtime/phase6 \
MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE=deterministic \
bash scripts/dev_up.sh
```

3. Relaunch the desktop shell only after the control plane is healthy.

```bash
swift run --package-path apps/macos-menubar melix-menubar
```

4. Retry the real Swift MLX path only after the deterministic desktop chat flow is stable.

```bash
MELIX_RUNTIME_DIR=.runtime/phase6 \
MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE=swift \
MELIX_DEV_TEXT_MODEL_PATH="<model path or repo>" \
bash scripts/dev_up.sh
```

## Verification

```bash
make swift-test
make py-test
make integration-test
make coverage
MELIX_RUNTIME_DIR=.runtime/phase6 bash scripts/dev_down.sh
```

## Escalation

- Stop and inspect the XPC path if the Chat panel can refresh snapshots but cannot start a chat execution.
- Stop and inspect the worker route if the transcript never receives a first delta after the control plane accepts the request.
- Do not continue to the next Phase 6 milestone until the native Chat panel can drive a real request through the control plane and the transcript reflects streamed deltas.
