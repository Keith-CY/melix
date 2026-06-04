# Startup Version Raw Prefix Guard Elision

## Scope

This slice is limited to the Python startup version comparison hot path in `services/mlx-worker-python/worker/productization/startup_signals.py`. The raw `v`-prefix equivalence fast path already proves the longer string is non-empty through the length check, so this slice removes redundant truthiness checks before inspecting the first character.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe `startup-signals-version-compare-single-pass` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` values. This is a Python-only slice and is locally verifiable on Linux.

## Verification Plan

1. Run the focused registered test command for `startup-signals-version-compare-single-pass`.
2. Run the registered changed-scope coverage command.
3. Run the registered local probe on Linux and compare baseline vs optimized `elapsed_ms_mean` for version comparison.
4. Use GitHub Actions and the registered PR-scoped performance report as the final merge gate.

## Acceptance

- Focused tests pass.
- Changed-scope coverage is at least 95% for the changed scope.
- The registered probe shows a non-regressing version comparison path.
- The change remains limited to raw `v`-prefix guard elision.
