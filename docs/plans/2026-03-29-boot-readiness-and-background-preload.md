# Boot Readiness, Lazy Text Load, and Background Preload Optimization

## Goal

Reduce Melix cold-boot and restart-recovery readiness time by making HTTP readiness independent from text-model warmup, moving non-text Python model preloads into a background bootstrap stage, and measuring the first text-model load separately.

## Scope

- remove blocking `melix-dev-text` preload from startup
- support on-demand text-model load on the first text request
- move phase-five through phase-seven Python compatibility model preloads behind HTTP readiness
- add explicit startup metrics for HTTP readiness, first text warmup, and preload memory impact
- add segmented startup metrics for the Swift text worker, Python worker, and control-plane HTTP readiness path
- add internal worker bootstrap metrics so phase-eight reports separate process launch delay from in-process bootstrap work
- add an opt-in `scripts/dev_up.sh --prefer-built` path so local operator loops can skip `swift run` startup overhead when the Swift executables are already built
- migrate `scripts/dev_up.sh` launch planning and startup orchestration into a Python entrypoint so command construction is structured and testable across macOS Bash versions
- make Python worker bootstrap metrics exports atomic so runtime probes no longer depend on transient half-written JSON files
- update Phase 8 runtime probes so product metrics distinguish ready-state, first text warmup, and background warmup

## Files

- modify `services/control-plane-swift/Sources/Bootstrap/main.swift`
- modify `services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIHandler.swift`
- modify `services/control-plane-swift/Sources/WorkerClient/PythonBridgeWorkerClient.swift`
- modify `tests/integration/helpers.py`
- modify `scripts/phase8_runtime_probes.py`
- modify `services/mlx-worker-python/worker/productization/acceptance_metrics.py`
- modify `services/mlx-worker-python/worker/grpc_server.py`
- modify `services/mlx-text-worker-swift/Sources/Core/WorkerBootstrap.swift`
- modify `scripts/dev_up.sh`
- create `scripts/dev_up.py`
- modify affected tests under `services/control-plane-swift/Tests`
- modify affected worker and productization tests under `services/mlx-worker-python/tests`
- update relevant docs and runbooks if behavior changes

## Performance Probes

- `control_plane.http_ready_ms`
- `control_plane.text_first_load_ms`
- `control_plane.text_first_load_estimated_resident_bytes`
- `control_plane.text_first_load_resident_bytes`
- `control_plane.background_preload_ms`
- `desktop.swift_text_worker_ready_ms`
- `desktop.swift_text_worker_spawn_to_bootstrap_ms`
- `desktop.swift_text_worker_registry_init_ms`
- `desktop.swift_text_worker_services_init_ms`
- `desktop.swift_text_worker_server_construct_ms`
- `desktop.swift_text_worker_bootstrap_ms`
- `desktop.python_worker_ready_ms`
- `desktop.python_worker_spawn_to_bootstrap_ms`
- `desktop.python_worker_arg_parse_ms`
- `desktop.python_worker_registry_init_ms`
- `desktop.python_worker_server_build_ms`
- `desktop.python_worker_server_start_ms`
- `desktop.python_worker_bootstrap_ms`
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
- worker bootstrap evidence distinguishes process-spawn delay from in-process bootstrap phases for both worker families
- the first text request lazily warms the text model and records its latency and resident bytes
- background preload completion is still measurable
- local operators can opt into prebuilt Swift executables without changing the default source-based startup path, and `dev_up` behavior is no longer coupled to Bash 4-only builtins
- metrics exports are written atomically for all worker families, and phase-8 probes can tolerate deadline boundaries without racing transient partial writes
- Phase 8 metrics report clearly separates user-facing readiness, first text warmup, and background warmup
