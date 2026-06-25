# Issue 58 Packaged Python Import Isolation

## Status

Implemented as a focused issue #58 release-packaging slice on 2026-06-25.

## Goal

Make packaged app-bundle Python launches deterministic against ambient operator
Python state by declaring and applying a filesystem-first import isolation
contract before the packaged worker and readiness probes start.

## Scope

In scope:

- Declare the packaged Python import-isolation contract in the app-bundle target manifest.
- Apply the same environment flags in the generated `Melix.sh` launcher before any bundled
  Python worker or probe invocation.
- Extend deterministic packaging and release-gate smokes so release evidence records whether
  self-contained bundles satisfy the import-isolation gate.

Out of scope:

- Replacing packaged runtime verification with full sidecar import, Metal, or runtime hash probes.
- Changing development-mode or local-install runtime fallback behavior.
- Completing Homebrew or Nix distribution admin setup for issue #1620.

## Implementation Notes

The app-bundle launcher sets:

- `PYTHONSAFEPATH=1`
- `PYTHONNOUSERSITE=1`
- `PYTHONDONTWRITEBYTECODE=1`

It still sets `PYTHONPATH` explicitly to the bundled `python-site-packages`, bundled repo root, and
bundled worker source path. That preserves the existing self-contained bundle import graph while
removing the ambient current-directory and user-site paths that can shadow the bundled runtime.

The target manifest records `python_import_isolation` so release evidence can distinguish a bundle
that intentionally enforces import isolation from a checkout or launch-agent install where this
specific gate is not applicable.

## Performance Probes And Success Metrics

- `packaging_target_app_bundle_python_import_isolated` from `scripts/m8_packaging_target_smoke.py`
  must be `1`.
- `python_import_isolation.gate_satisfied` in packaged launch release-gate evidence must be `1`.
- The changed path is manifest rendering and launcher generation, so runtime latency is not measured
  in this slice. The deterministic smoke reports render-time packaging metrics and does not import
  the full ML runtime.

## Verification

Run focused packaging and release-gate tests:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest \
  services/mlx-worker-python/tests/test_macos_app_bundle.py \
  services/mlx-worker-python/tests/test_packaged_launch_release_gate.py \
  services/mlx-worker-python/tests/test_m8_packaging_target_smoke.py \
  services/mlx-worker-python/tests/test_m9_release_gate_smoke.py \
  services/mlx-worker-python/tests/test_release_gates.py::test_build_release_gate_report_records_packaged_launch_passed_state \
  -q
```

Run the deterministic smoke:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx python scripts/m8_packaging_target_smoke.py --json
```
