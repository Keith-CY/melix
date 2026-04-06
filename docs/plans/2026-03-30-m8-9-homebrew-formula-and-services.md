# M8.9 Homebrew Formula And Services

Status: completed in commit `feat: close M8.9 homebrew formula and services`

## Goal

Add Homebrew-based distribution and service management so Melix can be installed and managed through standard local packaging flows.

## Scope

- define a Homebrew formula
- support service management through Homebrew
- document the install, upgrade, and service lifecycle

## Files

- create `infra/homebrew/`
- create `scripts/melix_homebrew_service.py`
- create `scripts/m8_homebrew_formula_smoke.py`
- create `scripts/m8_homebrew_service_smoke.py`
- create `services/mlx-worker-python/worker/productization/homebrew_formula.py`
- create `services/mlx-worker-python/worker/productization/homebrew_service.py`
- update `docs/runbooks/`
- update `README.md`
- update `docs/README.md`

## Implementation Notes

- package metadata should remain aligned with Melix release artifacts and startup behavior
- service management should reuse product-owned launch semantics
- documentation should distinguish development startup from packaged service operation

## Verification

- package validation command for the touched scope
- service lifecycle smoke command for the touched scope
- `make py-test`
- `ruby -c infra/homebrew/Formula/melix.rb`
- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_homebrew_distribution.py services/mlx-worker-python/tests/test_homebrew_service_script.py -q`
- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python --extra mlx python scripts/m8_homebrew_formula_smoke.py --json`
- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python --extra mlx python scripts/m8_homebrew_service_smoke.py --json`
- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python --extra mlx python scripts/melix_homebrew_service.py manifest --json`
- `python3 scripts/python_changed_line_coverage.py --coverage-json /tmp/m8_9_python_coverage.json services/mlx-worker-python/worker/productization/homebrew_formula.py services/mlx-worker-python/worker/productization/homebrew_service.py services/mlx-worker-python/tests/test_homebrew_distribution.py services/mlx-worker-python/tests/test_homebrew_service_script.py scripts/m8_homebrew_formula_smoke.py scripts/m8_homebrew_service_smoke.py scripts/melix_homebrew_service.py`

## Acceptance

- Melix has a repository-owned Homebrew distribution plan with service support
- install and service behavior are documented and reproducible

## Completion Notes

- added a checked-in Homebrew formula under `infra/homebrew/Formula/melix.rb` that installs Melix directly from the checked-out repository root, builds the CLI plus the control-plane and Swift text-worker binaries, and exposes a `melix-homebrew-service` wrapper for `brew services`
- added repository-owned Homebrew service supervision helpers that reuse the Melix local-product layout and environment contract while replacing launch-agent plists with a directly supervised three-process service bundle
- added deterministic formula and service smoke commands so the Homebrew distribution path is verifiable without depending on a live published tap or long-running service startup during repository CI
- documented the Homebrew install, upgrade, stop, and prune lifecycle in a dedicated runbook and surfaced the new path in the top-level README and documentation map
- changed-line coverage for the touched executable scope:
  - Python executable scope: `100.00%` (`453/453`) across `services/mlx-worker-python/worker/productization/homebrew_formula.py`, `services/mlx-worker-python/worker/productization/homebrew_service.py`, `services/mlx-worker-python/tests/test_homebrew_distribution.py`, `services/mlx-worker-python/tests/test_homebrew_service_script.py`, `scripts/m8_homebrew_formula_smoke.py`, `scripts/m8_homebrew_service_smoke.py`, and `scripts/melix_homebrew_service.py`
  - Ruby Homebrew formula scope: `N/A` because the repository does not yet have a changed-line coverage tool for Ruby formula files
