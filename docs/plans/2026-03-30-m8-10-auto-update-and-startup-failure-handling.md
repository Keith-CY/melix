# M8.10 Auto-Update And Startup Failure Handling

Status: completed. Repository-owned update-channel metadata, install-manifest startup diagnostics,
deterministic smoke coverage, and native operator-shell projection are implemented and verified.

## Goal

Add update checks, crash and hang awareness, and startup failure handling so packaged Melix installs can recover and explain failures clearly.

## Scope

- add update-check flow
- add crash and hang detection
- add startup failure reporting and host-port diagnostics

## Files

- update `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopFoundationState.swift`
- update `apps/macos-menubar/Sources/AppMain/MenuBar/StatusMenu.swift`
- update `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`
- add `apps/macos-menubar/Sources/AppMain/Persistence/ProductInstallState.swift`
- update `apps/macos-menubar/Tests/MenuBarTests/`
- update `services/mlx-worker-python/worker/productization/install_assets.py`
- add `services/mlx-worker-python/worker/productization/startup_signals.py`
- update `scripts/install_local_product.py`
- add `scripts/m8_startup_failure_smoke.py`
- add `infra/packaging/update-channels/stable.json`
- update `README.md`
- update `docs/runbooks/phase-8-local-install.md`
- update `infra/packaging/README.md`

## Implementation Notes

- failure reporting should point operators to actionable next steps and logs
- update logic should stay separate from runtime control logic
- startup failure handling should remain compatible with launch agents and packaged installs

## Verification

- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_install_assets.py services/mlx-worker-python/tests/test_install_local_product_script.py services/mlx-worker-python/tests/test_startup_signals.py services/mlx-worker-python/tests/test_m8_startup_failure_smoke.py -q`
- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python --extra mlx python scripts/m8_startup_failure_smoke.py --json`
- `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --filter ProductInstallStateTests`
- `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --enable-code-coverage --filter 'AppMainBootstrapTests|ProductInstallStateTests|RuntimeViewModelTests|StatusMenuTests|DesktopFoundationViewTests'`
- `make py-test`
- `make swift-test`

## Metrics

- Python changed-line coverage for the touched executable scope: `95.89%` (`280/292`)
- menu bar changed-line coverage for the touched executable scope: `99.65%` (`564/566`)
- aggregate changed-line coverage for the touched executable scope: `98.39%` (`844/858`)

## Completion Notes

- packaged install manifests now remain the authoritative source for product version,
  update-channel path, requested-versus-selected HTTP ports, ready probe URL, and log locations
- startup diagnostics now classify `host_port_conflict`, `control_plane_crash`, `worker_crash`,
  and `startup_hang` without introducing a second packaging-state store outside the manifest
- the native operator shell surfaces repository-owned update status and actionable packaged-startup
  guidance sourced from the same install-manifest contract used by the packaging layer

## Acceptance

- Melix can detect update availability and startup failures explicitly
- failure handling and operator messaging are test-covered
