# Dataset Registry File Slots

## Scope

This Python-only performance slice is limited to the dataset snapshot file record
path in `services/mlx-worker-python/worker/dataset_registry/catalog.py`.

## Registered PR-scoped probe

The affected path is already covered by the registered PR-scoped performance
probe `dataset-registry-snapshot-inference-single-pass` in
`infra/perf/pr_scoped_probes.json`. The entry declares focused `test_command`,
`coverage_command`, and `probe_command` values for:

- `services/mlx-worker-python/worker/dataset_registry/catalog.py`
- `services/mlx-worker-python/tests/test_dataset_registry.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/dataset_registry_snapshot_probe.py`

No probe registry change is required for this slice.

## Optimization hypothesis

Dataset snapshot construction creates one `DatasetFile` record per supported
file before serializing the registry payload. `DatasetFile` instances are frozen
value records and do not need per-instance `__dict__` storage. Enabling dataclass
slots for this hot record should reduce peak allocation pressure during large
snapshot scans while preserving field access, equality, and `to_dict()` behavior.

## Verification plan

1. Add a focused regression test that proves `DatasetFile` remains a frozen value
   record, serializes through `to_dict()`, and no longer exposes a mutable
   instance `__dict__`.
2. Implement only `DatasetFile` slots.
3. Run the registered focused pytest command locally on Linux.
4. Run the registered changed-scope coverage command locally on Linux and require
   at least 95 percent changed-scope coverage.
5. Run `scripts/dataset_registry_snapshot_probe.py` before and after the change
   and compare `peak_bytes_mean` and `elapsed_ms_mean`.
6. Use GitHub Actions PR-scoped performance as the final registered probe gate
   before merge.

## Linux validation boundary

This slice is Python-only and locally verifiable on Linux. No Swift runtime
performance claims are made.
