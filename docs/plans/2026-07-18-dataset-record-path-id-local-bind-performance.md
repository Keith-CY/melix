# Dataset Record Path ID Local Bind Performance Slice

## Scope

This slice keeps dataset ingest record behavior unchanged and narrows the hot
path inside `services/mlx-worker-python/worker/productization/dataset_preparation.py`.
The target is `_record()` source-id generation while the registered dataset
source records probe builds thousands of source record payloads.

## Registered Probe

The affected path is covered by the registered PR-scoped probe
`dataset-source-records-scandir` in `infra/perf/pr_scoped_probes.json`. The
registry entry already includes focused `test_command`, `coverage_command`, and
`probe_command` entries for:

- `services/mlx-worker-python/worker/productization/dataset_preparation.py`
- `services/mlx-worker-python/tests/test_dataset_preparation_ingest.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/dataset_source_records_probe.py`

## Implementation Plan

1. Preserve record source-id and source-uri semantics with focused regression
   assertions in `test_dataset_preparation_ingest.py`.
2. Bind `os.fspath` at module scope and use it directly in `_record()` to avoid
   repeated global `str` conversion lookup on the per-record source-id hot path.
3. Run the registered focused tests, changed-scope coverage, and local Linux
   `dataset-source-records-scandir` probe before pushing.
4. Let the PR-scoped performance workflow validate the registered probe in CI
   before merge.

## Linux Probe Notes

Pre-change local probe from synced `origin/main` worktree:

```text
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" \
MELIX_DATASET_SOURCE_RECORDS_PROBE_SAMPLES=7 \
uv run --project services/mlx-worker-python python3 scripts/dataset_source_records_probe.py

record_elapsed_ms_mean=19.496, elapsed_ms_mean=13.119, source_kind_elapsed_ms_mean=20.048
```

Initial post-change local probe:

```text
record_elapsed_ms_mean=19.006, elapsed_ms_mean=11.954, source_kind_elapsed_ms_mean=19.305
```

The authoritative merge gate remains the registered PR-scoped performance CI
report.
