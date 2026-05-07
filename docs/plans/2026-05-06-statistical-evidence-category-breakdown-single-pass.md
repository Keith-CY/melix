# Statistical Evidence Category Breakdown Single-Pass Plan

## Goal

Reduce redundant work and memory pressure in `build_category_breakdown(...)` by replacing per-category retained row lists and follow-up scans with a compact single-pass aggregate.

## Linux-only constraint

This is a Python worker/productization slice under `services/mlx-worker-python`, so it can be verified on Linux with focused pytest, changed-scope coverage, and a local PR-scoped performance probe.

## Touched files

- `services/mlx-worker-python/worker/productization/statistical_evidence.py`
- `services/mlx-worker-python/tests/test_statistical_evidence.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`
- `scripts/statistical_evidence_category_breakdown_probe.py`

## Performance probe

Register `statistical-evidence-category-breakdown-single-pass` in the PR-scoped performance registry. The probe builds a synthetic many-row category payload, calls `build_category_breakdown(...)`, and reports:

- `elapsed_ms_mean` — lower is better
- `peak_bytes_mean` — lower is better
- structural row/category/checksum metrics to catch semantic drift

## Success metrics

- Preserve category labels, sorted output ordering, sample sizes, rounded base/target accuracy, and delta accuracy.
- Focused tests pass.
- Changed-scope coverage for touched executable Python files is at least 95%.
- Local base-vs-head probe shows lower peak memory and/or elapsed time for the synthetic workload.

## Verification commands

- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q ...`
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q ... && coverage json ... && python3 scripts/changed_scope_coverage.py ...`
- `python3 scripts/pr_scoped_performance_run.py --probe-id statistical-evidence-category-breakdown-single-pass ...`
- `git diff --check`
