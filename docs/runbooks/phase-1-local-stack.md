# Phase 1 Local Stack

## Trigger

Use this runbook when you need to:

- boot the full phase-1 local stack
- debug the default Swift text route
- reproduce the deterministic integration path
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

Use the opt-in fast path only when the Swift binaries are already built and you want to avoid `swift run` launcher overhead during repeated local restarts.

```bash
bash scripts/dev_up.sh --prefer-built
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

5. Run the reproducible metrics report for the deterministic stack.

```bash
make phase1-metrics
```

## Common Causes

- The runtime directory already contains stale pid files from a previous run.
- The Swift text worker socket path already exists because shutdown did not complete.
- `MELIX_DEV_TEXT_MODEL_PATH` is missing while `MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE=swift`.
- Swift package caches or module caches were not initialized before startup.
- `--prefer-built` was used before the Swift executables were built under `.build/.../debug`.

## Recovery

1. Stop the phase-1 stack and clear stale runtime metadata.

```bash
bash scripts/dev_down.sh
```

2. Restart in deterministic mode to confirm the shared RPC and HTTP path are healthy.

```bash
bash scripts/dev_up.sh
make phase1-metrics
```

3. Retry the real Swift MLX path only after the deterministic path is stable.

```bash
MELIX_DEV_TEXT_MODEL_PATH="<model path or repo>" \
MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE=swift \
bash scripts/dev_up.sh
```

4. When the MLX path is required, capture a machine-readable report.

```bash
MELIX_DEV_TEXT_MODEL_PATH="<model path or repo>" \
make phase1-metrics PHASE1_METRICS_ARGS="--swift-backend-mode swift --json"
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

- Stop and inspect the logs if the deterministic stack cannot warm `melix-dev-text`.
- Stop and inspect the environment if the Swift MLX path fails without `MELIX_DEV_TEXT_MODEL_PATH`.
- Do not continue to later milestones until the deterministic metrics report and integration suite both pass.
