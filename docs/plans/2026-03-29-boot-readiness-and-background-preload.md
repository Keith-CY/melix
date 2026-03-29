# Boot Readiness, Lazy Text Load, and Background Preload Optimization

## Goal

Reduce Melix cold-boot and restart-recovery readiness time by making HTTP readiness independent from text-model warmup, moving non-text Python model preloads into a background bootstrap stage, and measuring the first text-model load separately.

## Scope

- remove blocking `melix-dev-text` preload from startup
- support on-demand text-model load on the first text request
- move phase-five through phase-seven Python compatibility model preloads behind HTTP readiness
- add explicit startup metrics for HTTP readiness, first text warmup, and preload memory impact
- add segmented startup metrics for the Swift text worker, Python worker, and control-plane HTTP readiness path
- update Phase 8 runtime probes so product metrics distinguish ready-state, first text warmup, and background warmup

## Files

- modify `services/control-plane-swift/Sources/Bootstrap/main.swift`
- modify `services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIHandler.swift`
- modify `services/control-plane-swift/Sources/WorkerClient/PythonBridgeWorkerClient.swift`
- modify `tests/integration/helpers.py`
- modify `scripts/phase8_runtime_probes.py`
- modify `services/mlx-worker-python/worker/productization/acceptance_metrics.py`
- modify affected tests under `services/control-plane-swift/Tests`
- update relevant docs and runbooks if behavior changes

## Performance Probes

- `control_plane.http_ready_ms`
- `control_plane.text_first_load_ms`
- `control_plane.text_first_load_estimated_resident_bytes`
- `control_plane.text_first_load_resident_bytes`
- `control_plane.background_preload_ms`
- `desktop.swift_text_worker_ready_ms`
- `desktop.python_worker_ready_ms`
- `desktop.control_plane_spawn_to_ready_ms`
- `desktop.cold_boot_to_ready_ms`
- `desktop.first_text_model_warm_ms`
- `desktop.text_model_load_estimated_resident_bytes`
- `desktop.text_model_load_resident_bytes`
- `desktop.restart_swift_text_worker_ready_ms`
- `desktop.restart_python_worker_ready_ms`
- `desktop.restart_control_plane_spawn_to_ready_ms`
- `desktop.restart_recovery_ms`

## Verification

- `make swift-test`
- `make py-test`
- `make integration-test`
- `make phase8-metrics PHASE8_METRICS_ARGS="--json"`
- `make coverage`
- `git diff --check`

## Acceptance

- HTTP ready-state is reached without warming the text model first
- segmented startup evidence shows how much time is spent in the Swift text worker, Python worker, and control-plane bootstrap stages
- the first text request lazily warms the text model and records its latency and resident bytes
- background preload completion is still measurable
- Phase 8 metrics report clearly separates user-facing readiness, first text warmup, and background warmup
