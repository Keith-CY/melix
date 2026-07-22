# Dataset Source Read Local Bindings

## Scope

This Python-only performance slice is limited to dataset ingest source text reads
in `services/mlx-worker-python/worker/productization/dataset_preparation.py`.

The unbounded source reader keeps the existing single binary read behavior and
UTF-8 decoding semantics, while binding the hot globals used by each source-file
read (`os.fspath`, module-level `open`, and `bytes.decode`) into local variables.
The goal is to reduce repeated global/method lookup overhead in large source
record scans without changing cap enforcement, failure behavior, or monkeypatch
seams used by tests.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe
`dataset-source-records-scandir` in `infra/perf/pr_scoped_probes.json`. The
registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries for:

- `services/mlx-worker-python/worker/productization/dataset_preparation.py`
- `services/mlx-worker-python/tests/test_dataset_preparation_ingest.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/dataset_source_records_probe.py`

The probe reports source-tree traversal timing plus source kind, read, and record
construction metrics. This slice uses `read_elapsed_ms_*` as the primary local
Linux signal.

## Verification Plan

Run the registered focused tests, changed-scope coverage command, `git diff --check`,
and the registered `dataset-source-records-scandir` probe locally on Linux before
opening the PR. GitHub Actions PR-scoped performance remains the merge gate for
the registered probe report.
