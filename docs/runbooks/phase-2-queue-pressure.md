# Phase 2 Queue Pressure and Metrics

## Trigger

Use this runbook when you need to:

- boot the live Phase 2 local stack
- confirm that follower requests queue behind an active text request
- capture the reproducible Phase 2 metrics report
- debug missing scheduler or acceleration evidence

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

2. Start a fresh local stack under a Phase 2 runtime directory.

```bash
MELIX_RUNTIME_DIR=.runtime/phase2 bash scripts/dev_up.sh
```

This boots the default real backend path. Use a deterministic override only when you need an explicit fixture to isolate queueing behavior from model-availability issues.

3. Confirm the control plane is serving the warm dev model.

```bash
curl -sS http://127.0.0.1:11434/v1/models
```

4. Capture the Phase 2 metrics report for the running stack.

```bash
MELIX_RUNTIME_DIR=.runtime/phase2 make phase2-metrics
```

5. Inspect the exported metrics and logs if queue evidence is missing.

```bash
cat .runtime/phase2/control-plane-metrics.json
cat .runtime/phase2/swift-text-worker-metrics.json
tail -n 50 .runtime/phase2/control-plane.log
tail -n 50 .runtime/phase2/swift-text-worker.log
```

## Common Causes

- The runtime directory contains stale pid files or sockets from a previous run.
- The stack was started without the Phase 2 runtime directory override, so the metrics export paths are not where the operator expects them.
- The required real MLX text model source is unavailable for the default live path.
- The queue-pressure run is too short or does not generate enough decode work to create measurable follower delay.

## Recovery

1. Stop the stack and clear the runtime directory metadata.

```bash
MELIX_RUNTIME_DIR=.runtime/phase2 bash scripts/dev_down.sh
```

2. If the live path is blocked by model setup, restart with an explicit deterministic fixture and rerun the report.

```bash
MELIX_RUNTIME_DIR=.runtime/phase2 \
MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE=deterministic \
MELIX_BACKEND_MODE=deterministic \
bash scripts/dev_up.sh

MELIX_RUNTIME_DIR=.runtime/phase2 make phase2-metrics
```

3. Return to the default real backend path when live MLX evidence is required.

```bash
MELIX_RUNTIME_DIR=.runtime/phase2 \
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
MELIX_RUNTIME_DIR=.runtime/phase2 make phase2-metrics
MELIX_RUNTIME_DIR=.runtime/phase2 bash scripts/dev_down.sh
```

## Escalation

- Stop and inspect the exported metrics if `scheduler.queue_delay_ms` remains zero under a deliberate two-request queue-pressure run.
- Stop and inspect the worker runtime if speculative or accelerated-prefill metrics remain zero on the selected runtime path.
- Do not continue to Phase 3 until the Phase 2 report is stable and repeatable on the intended signoff path, which should be the default real backend unless you are explicitly isolating with a deterministic fixture.
