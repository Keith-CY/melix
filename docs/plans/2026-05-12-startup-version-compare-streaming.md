# Startup Version Compare Streaming

## Scope

This slice keeps the existing startup-signal version comparison behavior while reducing per-comparison work in `compare_versions()`.

Affected files:

- `services/mlx-worker-python/worker/productization/startup_signals.py`
- `services/mlx-worker-python/tests/test_startup_signals.py`

## Probe Coverage

The path is already covered by the registered PR-scoped probe `startup-signals-version-compare-single-pass` in `infra/perf/pr_scoped_probes.json`. The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries and runs on `ubuntu-latest`.

## Implementation Plan

1. Preserve `normalized_version_parts()` as the public materialized helper.
2. Add a shared streaming parser for version parts.
3. Make `compare_versions()` consume the streaming parser directly so ordinary comparisons avoid allocating normalized part lists.
4. Add a focused regression test proving `compare_versions()` no longer depends on the materialized helper.
5. Verify with focused pytest, changed-scope coverage, and the registered probe locally on Linux before PR.

## Success Metrics

Registered probe: `startup-signals-version-compare-single-pass`.

Baseline from `origin/main` in this worktree before the change:

```text
{"comparison_total": -48.0, "elapsed_ms_mean": 153.81884485084032, "pair_count": 12000.0, "peak_bytes_mean": 356.0, "sample_count": 7.0}
```

The accepted slice should reduce `elapsed_ms_mean` without changing `comparison_total`. `peak_bytes_mean` is informational in the registry and may vary with generator-frame accounting.

Post-change local Linux probe runs:

```text
{"comparison_total": -48.0, "elapsed_ms_mean": 50.83740156676088, "pair_count": 12000.0, "peak_bytes_mean": 828.0, "sample_count": 7.0}
{"comparison_total": -48.0, "elapsed_ms_mean": 49.80765115137079, "pair_count": 12000.0, "peak_bytes_mean": 828.0, "sample_count": 7.0}
{"comparison_total": -48.0, "elapsed_ms_mean": 54.59928269764142, "pair_count": 12000.0, "peak_bytes_mean": 828.0, "sample_count": 7.0}
```

Observed best local delta: `153.81884485084032 ms -> 49.80765115137079 ms` (`-104.01119369946953 ms`, about `3.09x` faster) with unchanged `comparison_total=-48.0`.
