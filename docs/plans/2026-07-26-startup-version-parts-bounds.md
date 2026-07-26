# Startup Signals Version Parts Bounds Scan

## Context

The registered PR-scoped probe `startup-signals-version-compare-single-pass`
includes a direct `normalized_version_parts()` hot path for whitespace-padded
version strings. The previous implementation materialized a stripped copy before
parsing numeric components, adding allocation work to each uncached direct call.

## Slice

Parse `normalized_version_parts()` with explicit leading/trailing whitespace
bounds instead of calling `str.strip()`. Keep the existing single-pass digit
parser and public return shape unchanged.

## Probe Coverage

The existing registered probe already covers this path with focused test,
coverage, and probe commands in `infra/perf/pr_scoped_probes.json`:

- `services/mlx-worker-python/worker/productization/startup_signals.py`
- `services/mlx-worker-python/tests/test_startup_signals.py`
- `scripts/startup_signals_version_probe.py`

## Verification Plan

1. Run the focused startup-signals tests from the registered probe.
2. Run changed-scope coverage for the registered probe scope.
3. Run `scripts/startup_signals_version_probe.py` locally on Linux and compare
   pre/post metrics, with emphasis on `normalized_parts_elapsed_ms_mean` and
   `normalized_parts_peak_bytes_mean`.
4. Use the PR-scoped performance CI report as the merge gate.
