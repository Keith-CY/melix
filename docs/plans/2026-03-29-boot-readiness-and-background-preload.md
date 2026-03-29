# Boot Readiness and Background Preload Optimization

## Goal

Reduce Melix cold-boot and restart-recovery readiness time by making only the text-ready path blocking while moving non-text Python model preloads into a background bootstrap stage.

## Scope

- keep `melix-dev-text` preload as the blocking readiness gate
- move phase-five through phase-seven Python compatibility model preloads behind HTTP readiness
- add explicit bootstrap metrics for text-ready and background-preload completion
- update Phase 8 runtime probes so product metrics distinguish ready-state from background warmup

## Files

- modify `services/control-plane-swift/Sources/Bootstrap/main.swift`
- modify `services/control-plane-swift/Sources/WorkerClient/PythonBridgeWorkerClient.swift`
- modify `scripts/phase8_runtime_probes.py`
- modify `services/mlx-worker-python/worker/productization/acceptance_metrics.py`
- modify affected tests under `services/control-plane-swift/Tests`
- update relevant docs and runbooks if behavior changes

## Performance Probes

- `control_plane.text_ready_preload_ms`
- `control_plane.background_preload_ms`
- `desktop.cold_boot_to_ready_ms`
- `desktop.restart_recovery_ms`

## Verification

- `make swift-test`
- `make py-test`
- `make integration-test`
- `make phase8-metrics PHASE8_METRICS_ARGS="--json"`
- `git diff --check`

## Acceptance

- HTTP ready-state is reached after the text model is warm without waiting for non-text preload families
- background preload completion is still measurable
- Phase 8 metrics report clearly separates user-facing readiness from background warmup
