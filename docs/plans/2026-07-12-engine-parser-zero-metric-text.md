# Engine Parser Zero Metric Text Fast Path

## Scope

This Python-only performance slice is limited to the plain-text `EngineCore.generate(...)`
completion metadata path in `services/mlx-worker-python/worker/engine/engine_core.py`.
The behavior stays unchanged: completed events still expose the same parser metric keys
and string values.

## Registered Probe

The affected path is covered by the registered PR-scoped probe
`engine-generate-usage-token-elision` in `infra/perf/pr_scoped_probes.json`. The entry
already has focused `test_command`, `coverage_command`, and `probe_command` values for
`engine_core.py`, `test_generate_stream.py`, `test_pr_scoped_performance.py`, and
`scripts/engine_generate_usage_token_probe.py`.

## Optimization Slice

The common plain-text completion path emits several parser metrics whose values are
usually zero. This slice reuses the existing `_METRIC_ZERO_TEXT` singleton through
`_parser_metric_text(...)` instead of allocating fresh `str(0)` results for those
counters. Non-zero counters keep the same string conversion behavior.

## Verification Plan

1. Run the registered focused test command for `engine-generate-usage-token-elision`.
2. Run the registered changed-scope coverage command for the same probe.
3. Run the registered local probe on Linux and compare against the `origin/main`
   baseline.
4. Use PR-scoped performance CI as the merge gate for registered probe validation.

## Linux Boundary

This is a Python worker slice and is fully locally verifiable on Linux. No Swift runtime
effect is claimed.
