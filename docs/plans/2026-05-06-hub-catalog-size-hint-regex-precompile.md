# Hub Catalog Size Hint Regex Precompile

## Goal

Reduce repeated regex compilation overhead in the Hub catalog size-hint parser while preserving accepted size-hint formats.

## Touched Files

- `services/mlx-worker-python/worker/model_ops/hub_catalog.py`
- `services/mlx-worker-python/tests/test_hub_catalog.py`
- `scripts/hub_catalog_size_hint_probe.py`
- `infra/perf/pr_scoped_probes.json`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`

## Linux Constraint

This is a Python-only worker optimization and can be verified on Linux with focused pytest, changed-scope coverage, and a local PR-scoped performance probe.

## Performance Probe

Registered probe: `hub-catalog-size-hint-regex-precompile`

The probe repeatedly calls `_size_hint_from_text(...)` across direct card-data hints, explicit README/model-card hints, and non-matching fallback text. It records:

- `elapsed_ms_mean` — lower is better.
- `peak_bytes_mean` — informational.
- `size_hint_calls_mean` — structural workload size.
- `matched_hint_count` and `checksum` — behavior guard rails.

## Success Metrics

- Focused pytest passes.
- Changed executable line coverage is at least 95% for the touched Python scope.
- Local base-vs-head probe shows lower `elapsed_ms_mean` with identical structural guard rails.
- `git diff --check` passes.
