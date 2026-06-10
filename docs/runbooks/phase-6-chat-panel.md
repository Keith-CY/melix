# Phase 6 Native Chat Panel

## Trigger

Use this runbook when you need to:

- boot the local Phase 6 stack and exercise the native Chat panel
- verify that desktop chat requests flow through the control plane instead of a worker-direct path
- confirm reasoning and tool-call deltas appear in the transcript
- inspect model capability readiness for text, OCR, VLM, transcription, and speech-capable models

## Preconditions

- macOS on Apple Silicon
- `make bootstrap` has completed successfully
- `make proto` has completed successfully
- `uv` and `swift` are available; `make proto` builds the pinned protobuf generators from the
  repository's locked dependencies
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

This default startup path uses the real backend configuration. Only opt into deterministic mode when you need a bounded transport/debug fixture.

3. Confirm the control plane can see the expected local models.

```bash
curl -sS http://127.0.0.1:12436/v1/models
```

4. Launch the native desktop shell.

```bash
swift run --package-path apps/macos-menubar melix-menubar
```

If you want the whole local app, including the backend stack and workspace window, without
recompiling on each restart, build once and use the built-artifact entrypoint instead:

```bash
make swift-test
MELIX_RUNTIME_DIR=.runtime/phase6 bash scripts/dev_app_up.sh
```

5. Open the `Chat` tab, choose the intended Provider from the chat header, and submit a prompt.
   - Confirm the transcript records the user prompt and assistant output.
   - Confirm reasoning and tool-call sections appear when the runtime emits those deltas.
   - Confirm user and assistant bubbles do not expose internal model IDs or request IDs.
   - Confirm the `Model Capabilities` section reflects current OCR, VLM, transcription, and speech readiness from the latest snapshot as compact icons.

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
- The Chat session has not been bound to a Provider yet; choose one from the chat header before submitting.
- The desktop app was started before the control plane or workers were ready.
- The local model snapshot does not expose multimodal capability classes, so the model capability section remains empty.

## Recovery

1. Stop the stack and clear stale Phase 6 runtime metadata.

```bash
MELIX_RUNTIME_DIR=.runtime/phase6 bash scripts/dev_down.sh
```

2. If live-model setup may be obscuring the failure, restart with an explicit deterministic fixture and confirm `/v1/models` is healthy.

```bash
MELIX_RUNTIME_DIR=.runtime/phase6 \
MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE=deterministic \
MELIX_BACKEND_MODE=deterministic \
bash scripts/dev_up.sh
```

3. Relaunch the desktop shell only after the control plane is healthy.

```bash
swift run --package-path apps/macos-menubar melix-menubar
```

For repeated full-app restarts without launch-time compile overhead:

```bash
make swift-test
MELIX_RUNTIME_DIR=.runtime/phase6 bash scripts/dev_app_up.sh
```

4. Return to the default real-model path only after the desktop chat plumbing is stable.

```bash
MELIX_RUNTIME_DIR=.runtime/phase6 \
MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE=swift \
MELIX_BACKEND_MODE=auto \
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
