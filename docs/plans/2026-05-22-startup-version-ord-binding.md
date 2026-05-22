# Startup version parser ord binding

## Scope

This Python-only performance slice is limited to the version comparison parser in
`services/mlx-worker-python/worker/productization/startup_signals.py`.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`startup-signals-version-compare-single-pass` in `infra/perf/pr_scoped_probes.json`.
The probe has focused `test_command`, `coverage_command`, and `probe_command`
entries and reports version comparison elapsed time, peak bytes, and update
result construction metrics.

## Hypothesis

`compare_versions` repeatedly calls `_next_normalized_version_part`, which scans
version strings character-by-character. Binding `ord` at module scope avoids a
builtin lookup inside both parser loops while keeping comparison semantics
unchanged.

## Verification plan

1. Run the registered focused startup signal tests.
2. Run the registered changed-scope coverage command.
3. Run the registered local Linux probe against `origin/main` and this branch.
4. Use PR-scoped performance CI as the final registered probe gate before merge.
