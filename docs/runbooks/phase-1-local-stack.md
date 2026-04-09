# Phase 1 Local Stack

## Trigger

Use this runbook when you need to:

- boot the full phase-1 local stack
- debug the default Swift text route
- reproduce the explicit deterministic fixture path when you need to isolate live-model availability
- capture the phase-1 metrics report

## Preconditions

- macOS on Apple Silicon
- `make bootstrap` has completed successfully
- `make proto` has completed successfully
- `uv`, `swift`, `protoc`, and `protoc-gen-swift` are available

## Diagnosis

1. Confirm the repository bootstrap is current.

```bash
make bootstrap
make proto
```

2. Start the local phase-1 stack.

```bash
bash scripts/dev_up.sh
```

This default startup path uses the real backend configuration (`MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE=swift` and `MELIX_BACKEND_MODE=auto`). Use deterministic execution only when you explicitly need a fixture run.

Use the opt-in fast path only when the Swift binaries are already built and you want to avoid `swift run` launcher overhead during repeated local restarts.

```bash
bash scripts/dev_up.sh --prefer-built
```

When you want the backend stack plus the native workspace window without recompiling at launch
time, build once and then use the full-app entrypoint:

```bash
make swift-test
bash scripts/dev_app_up.sh
```

3. Check model visibility through the control plane.

```bash
curl -sS http://127.0.0.1:11434/v1/models
```

4. Inspect the runtime directory and logs when startup fails.

```bash
ls -la .runtime/phase1
tail -n 50 .runtime/phase1/swift-text-worker.log
tail -n 50 .runtime/phase1/python-worker.log
tail -n 50 .runtime/phase1/control-plane.log
```

5. Run the metrics report for the current stack.

```bash
make phase1-metrics
```

## Common Causes

- The runtime directory already contains stale pid files from a previous run.
- The Swift text worker socket path already exists because shutdown did not complete.
- No serveable text model is available in the managed or scanned model roots while the default real backend path is active.
- Swift package caches or module caches were not initialized before startup.
- `--prefer-built` or `scripts/dev_app_up.sh` was used before the Swift executables were built under `.build/.../debug`.

## Recovery

1. Stop the phase-1 stack and clear stale runtime metadata.

```bash
bash scripts/dev_down.sh
```

2. If live-model setup may be hiding the failure, restart with an explicit deterministic fixture to confirm the shared RPC and HTTP path are healthy.

```bash
MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE=deterministic \
MELIX_BACKEND_MODE=deterministic \
bash scripts/dev_up.sh
make phase1-metrics
```

3. Return to the default real backend path only after the transport layer is stable and a serveable text model source is available.

```bash
MELIX_DEV_TEXT_MODEL_PATH="<model path or repo>" \
MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE=swift \
MELIX_BACKEND_MODE=auto \
bash scripts/dev_up.sh
```

4. When the MLX path is required, capture a machine-readable report.

```bash
MELIX_DEV_TEXT_MODEL_PATH="<model path or repo>" \
make phase1-metrics PHASE1_METRICS_ARGS="--swift-backend-mode swift --json"
```

5. When you want the full app after the backend path is stable, relaunch from built artifacts.

```bash
make swift-test
bash scripts/dev_app_up.sh
```

## Verification

```bash
make swift-test
make py-test
make integration-test
make coverage
bash scripts/dev_down.sh
```

## Escalation

- Stop and inspect the logs if the default real backend path cannot warm or load `melix-dev-text`.
- Stop and inspect the environment if no serveable text model is visible to the default real backend path.
- Use the deterministic fixture only as a bounded debugging aid, not as the product-default signoff path for later milestones.
