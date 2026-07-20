# Dataset Source Read Local Open Binding Performance Slice

## Scope

This Python-only performance slice is limited to the dataset ingest source read path in `services/mlx-worker-python/worker/productization/dataset_preparation.py`.

## Registered Probe

The affected path is covered by the registered PR-scoped probe `dataset-source-records-scandir` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for the dataset preparation implementation, focused ingest tests, PR-scoped performance dispatch tests, and `scripts/dataset_source_records_probe.py`.

## Optimization

Bind the binary file opener used by `_read_source_text(...)` inside the helper before branching and use that function-local binding for both the unbounded single-read path and the capped chunked-read path. This keeps normal `builtins.open` patching semantics intact because the lookup still occurs when `_read_source_text(...)` is called, not at module import time.

Behavior remains unchanged: source paths are still converted with `os.fspath(...)`, files are still read in binary mode, unbounded reads still perform a single `read()`, capped reads still enforce the configured byte limit while streaming 64 KiB chunks, and UTF-8 decoding remains unchanged.

## Verification Plan

Run locally on Linux before PR:

1. The focused registered `dataset-source-records-scandir` test command.
2. Changed-scope coverage using the registered coverage command.
3. The registered `dataset-source-records-scandir` probe locally with repeated samples.
4. `git diff --check`.

GitHub Actions PR-scoped performance remains the merge gate for the registered probe report.
