# M8.11 Platform Packaging And Target Differentiation

## Status

Completed on 2026-04-04 with a repository-owned packaging target matrix, shared packaging target
metadata for `launch_agents`, `homebrew`, and `.app bundle` outputs, a deterministic smoke command,
and updated packaging or runbook documentation.

## Goal

Define platform packaging and Apple Silicon target differentiation so Melix can package optimized product variants without fragmenting the runtime model.

## Scope

- define target differentiation strategy
- preserve one logical product identity across packaging variants
- keep packaging outputs compatible with install and update flows
- emit stable packaging target metadata across all supported Apple Silicon delivery targets

## Files

- update `infra/`
- update `docs/runbooks/`
- update `README.md`
- update `docs/README.md`
- update `services/mlx-worker-python/worker/productization/`
- update `scripts/`

## Implementation Notes

- target differentiation should remain explicit in packaging metadata and documentation
- packaging variants should not create diverging protocol or operator semantics
- keep the path open for future hardware-specific optimizations without product confusion

## Verification

- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_packaging_targets.py services/mlx-worker-python/tests/test_install_assets.py services/mlx-worker-python/tests/test_install_local_product_script.py services/mlx-worker-python/tests/test_homebrew_distribution.py services/mlx-worker-python/tests/test_homebrew_service_script.py services/mlx-worker-python/tests/test_macos_app_bundle.py services/mlx-worker-python/tests/test_package_macos_menubar_app_script.py services/mlx-worker-python/tests/test_m8_packaging_target_smoke.py -q`
- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python --extra mlx python scripts/m8_packaging_target_smoke.py --json`
- `make py-test`
- `git diff --check`

## Acceptance

- Melix has a repository-owned packaging target matrix across the supported Apple Silicon delivery
  targets
- packaging behavior is documented and compatible with install and update flows
- launch-agent install manifests, Homebrew service manifests, and preview app-bundle metadata all
  preserve the shared Melix logical identity while making target differentiation explicit
