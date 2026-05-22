# Startup Version ASCII Digit Fast Path

## Scope

This Python-only performance slice keeps startup version comparison behavior equivalent for Melix semantic-version inputs while avoiding repeated `str.isdigit()` dispatch in the tight normalized-version scanner.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe `startup-signals-version-compare-single-pass` in `infra/perf/pr_scoped_probes.json`.

The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/productization/startup_signals.py`
- `services/mlx-worker-python/tests/test_startup_signals.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/startup_signals_version_probe.py`

## Optimization

Use direct ASCII character-code checks inside the normalized version parser for separators (`+`, `-`, `.`) and digit bounds (`0` through `9`). Melix product versions and update-channel versions are ASCII semantic-version strings, and the parser treats non-prefix suffix text as build/prerelease metadata rather than ordering input.

This follow-up slice also makes the streaming comparator skip the remainder of a version after the first `+` or `-` suffix marker. That keeps the streaming comparator aligned with `normalized_version_parts()` for left-hand build metadata and avoids scanning suffix tails that cannot affect update ordering.

## Validation Plan

Run the registered focused tests, changed-scope coverage, and the registered probe locally on Linux before pushing. GitHub Actions PR-scoped performance remains the merge gate.

## Success Metric

Accept only if `startup-signals-version-compare-single-pass.elapsed_ms_mean` improves without changing `comparison_total` or increasing measured peak memory.
