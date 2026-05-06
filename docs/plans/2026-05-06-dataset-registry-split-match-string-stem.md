# Dataset registry split-match string-stem optimization

## Goal

Reduce redundant `Path(part).stem` construction in dataset snapshot split selection. The hot path `read_hf_dataset_snapshot_rows(..., split=...)` checks every relative path segment against the requested split; constructing a temporary `Path` for every segment is unnecessary because only the final suffix-free stem string is needed.

## Linux-only constraint

This is a Python-only slice under `services/mlx-worker-python` and can be verified on Linux with focused pytest, changed-scope coverage, and a local synthetic probe.

## Touched files

- `services/mlx-worker-python/worker/dataset_registry/catalog.py`
- `services/mlx-worker-python/tests/test_dataset_registry.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/dataset_registry_split_match_probe.py`
- `infra/perf/pr_scoped_probes.json`

## Implementation plan

1. Replace temporary `Path(part).stem.lower()` construction inside `_path_matches_split(...)` with a small string-only stem helper.
2. Add focused regression coverage for split matching semantics and for avoiding the temporary `Path` constructor in the hot helper.
3. Add a command-json PR-scoped performance probe that compares split selection over a synthetic snapshot with many files and records elapsed time plus a structural `path_constructor_calls_mean` metric.
4. Update the existing dataset registry scoped probe entry so catalog changes run the new focused tests, changed-scope coverage, and split-match probe.

## Performance probe

Probe ID: `dataset-registry-limited-read-streaming` (updated to measure split matching for this slice).

Success metrics:

- Preserve selected row counts for the `validation` split.
- Reduce `path_constructor_calls_mean` from one call per scanned path segment on `origin/main` to `0.0` on the branch.
- Improve or preserve elapsed split-selection time on the synthetic workload.

## Verification commands

- Focused pytest for new dataset registry tests and probe script smoke test.
- `coverage run` plus `scripts/changed_scope_coverage.py` for changed executable scope.
- Local `scripts/dataset_registry_split_match_probe.py` run.
- Base-vs-head `scripts/pr_scoped_performance_run.py --probe-id dataset-registry-limited-read-streaming` when practical.
- `git diff --check`.
