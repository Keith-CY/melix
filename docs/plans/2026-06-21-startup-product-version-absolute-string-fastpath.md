# Startup product version absolute string fast path

## Scope

Optimize the Python startup product-version reader for callers that pass an
already absolute repository root as a string.

## Registered probe

The slice is covered by the existing PR-scoped performance probe
`startup-signals-version-compare-single-pass`, which watches:

- `services/mlx-worker-python/worker/productization/startup_signals.py`
- `services/mlx-worker-python/tests/test_startup_signals.py`
- `scripts/startup_signals_version_probe.py`

The probe includes focused `test_command`, `coverage_command`, and
`probe_command` entries in `infra/perf/pr_scoped_probes.json`. This slice keeps
the existing probe registration and updates the probe's product-version path to
exercise absolute string roots.

## Implementation plan

1. Preserve the current absolute `Path` fast path.
2. Convert string inputs with `Path(...).expanduser()` first and only call
   `resolve()` when the expanded path is relative.
3. Add a regression test that monkeypatches `Path.resolve` and verifies absolute
   string inputs do not resolve.
4. Run the registered focused tests, coverage command, and probe locally on
   Linux before opening the PR.

## Validation boundary

This is a Python-only slice and is locally verifiable on Linux. No Swift runtime
effect is claimed.
