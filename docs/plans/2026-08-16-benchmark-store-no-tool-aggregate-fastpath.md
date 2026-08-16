# Benchmark store no-tool matrix aggregation fast path

## Scope

This Python-only performance slice is limited to matrix benchmark summary
hydration in `services/mlx-worker-python/worker/productization/benchmark_store.py`.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`benchmark-store-matrix-streaming` in `infra/perf/pr_scoped_probes.json`. That
probe watches `benchmark_store.py`, `test_benchmark_store.py`,
`test_pr_scoped_performance.py`, and `scripts/benchmark_store_probe.py`, and it
provides focused `test_command`, `coverage_command`, and `probe_command` entries.

## Optimization hypothesis

Most synthetic matrix benchmark request rows in the registered probe have no tool
turn metrics. The previous summary hydration path still built the per-cell tool
turn aggregate dictionary for every request row before discovering that all tool
turn fields were empty and returning the original summary rows. This slice adds a
cheap pre-scan that validates request row types and returns immediately when no
request row carries tool turn metrics, avoiding the discarded aggregate map.

When any request row has tool turn data, behavior is unchanged: the code performs
the existing aggregation and returns hydrated summary rows.

## Verification path

Run the registered benchmark-store focused tests, changed-scope coverage, and
`benchmark_store_probe.py` locally on Linux. The expected signal is lower
`elapsed_ms_mean` for the matrix streaming probe while preserving summary
hydration behavior for both no-tool and tool-turn cases.

## Success criteria

- Focused benchmark-store and PR-scoped probe tests pass.
- Changed-scope automated coverage for touched paths is at least 95%.
- The local registered probe shows improvement or a clear non-regression.
- GitHub Actions PR-scoped performance for `benchmark-store-matrix-streaming`
  completes successfully before merge.
