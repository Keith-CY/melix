# Dataset failed-segment partition append cache

## Scope

This Python performance slice is limited to `_partition_failed_segments(...)` in
`services/mlx-worker-python/worker/productization/dataset_preparation.py`.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe
`dataset-quality-lengths-chain` in `infra/perf/pr_scoped_probes.json`. The probe
includes focused `test_command`, `coverage_command`, and `probe_command` entries
for the dataset preparation path, dataset preparation versioning tests, the
PR-scoped performance tests, and `scripts/dataset_quality_lengths_probe.py`.

## Optimization

When failed segment ids are present, `_partition_failed_segments(...)` walks every
segment and appends each row to either the successful or failed list. The loop now
binds both list `append` methods once before the scan so the hot partition loop
avoids repeated method lookup while preserving the existing empty-failure fast
path and all ordering semantics.

## Verification

Run locally on Linux using the registered focused commands from
`dataset-quality-lengths-chain`:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q <registered focused test list>
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q <registered focused test list>
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/productization/dataset_preparation.py services/mlx-worker-python/tests/test_dataset_preparation_versioning.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/dataset_quality_lengths_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/dataset_quality_lengths_probe.py
python3 scripts/pr_scoped_performance_run.py --registry infra/perf/pr_scoped_probes.json --probe-id dataset-quality-lengths-chain --base-repo /root/.hermes/profiles/coder/workspace/melix --head-repo "$PWD" --output /tmp/dataset-failed-partition-append-cache.json
```

GitHub Actions PR-scoped performance remains the merge gate for the registered
probe report.

## Local evidence

Linux local verification for branch `perf/dataset-jsonl-read-bytes-20260627`:

- Focused tests: `8 passed in 1.00s`.
- Changed-scope coverage: `TOTAL 4 0 100%`.
- Direct post-change probe:
  - `elapsed_ms_mean=2.296288`
  - `failed_partition_elapsed_ms_mean=1.191316`
- Local PR-scoped runner (`python3 scripts/pr_scoped_performance_run.py --probe-id dataset-quality-lengths-chain`) completed successfully and wrote `/tmp/dataset-failed-partition-append-cache.json`:
  - base `elapsed_ms_mean=2.303499`, head `elapsed_ms_mean=2.123851`, delta `-0.179648 ms` (`-7.7989%`, speedup `1.0846x`)
  - base `failed_partition_elapsed_ms_mean=1.390565`, head `failed_partition_elapsed_ms_mean=1.151863`, delta `-0.238702 ms` (`-17.1658%`, speedup `1.2072x`)

CI still remains the merge gate for the registered probe report.

## Success criteria

- Focused tests pass.
- Changed-scope coverage for touched Python and probe files remains at or above
  95%.
- Local and CI registered probe metrics show non-regression on aggregate
  `elapsed_ms_mean`, with expected improvement or neutrality for
  `failed_partition_elapsed_ms_mean`.
