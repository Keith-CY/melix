# Startup product version absolute-path fast path

## Scope

This Python-only performance slice is limited to `read_product_version()` in
`services/mlx-worker-python/worker/productization/startup_signals.py`.

The function is called repeatedly by the registered startup-signals probe with an
already absolute `Path` object. The previous implementation still rebuilt and
resolved that absolute path on every call before opening `pyproject.toml`. This
slice preserves the existing relative-path and string-input normalization path,
but reuses absolute `Path` inputs directly before appending `pyproject.toml`.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe
`startup-signals-version-compare-single-pass` in
`infra/perf/pr_scoped_probes.json`.

The probe has focused `test_command`, `coverage_command`, and `probe_command`
entries covering:

- `services/mlx-worker-python/worker/productization/startup_signals.py`
- `services/mlx-worker-python/tests/test_startup_signals.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/startup_signals_version_probe.py`

## Plan

1. Add regression coverage proving absolute `Path` inputs do not call
   `Path.resolve()` while still reading the project version.
2. Keep relative/string inputs on the existing `expanduser().resolve()` path.
3. Run the registered focused tests, changed-scope coverage, and registered probe
   locally on Linux.
4. Use GitHub Actions PR-scoped performance as the registered probe merge gate.

## Validation

Local Linux validation and probe deltas are recorded in the PR body for the
accepted slice.
