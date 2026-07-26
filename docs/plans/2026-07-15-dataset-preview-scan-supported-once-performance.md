# Dataset Preview Scan Supported-Name Predicate Performance Slice

## Scope

This Python-only performance slice is limited to
`worker.dataset_registry.catalog._supported_scan_entry_records()`, the scan
record helper used by limited dataset preview discovery.

## Registered Probe

The affected path is covered by the registered PR-scoped probe
`dataset-registry-preview-limit-short-circuit` in
`infra/perf/pr_scoped_probes.json`. The entry includes focused
`test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/dataset_registry/catalog.py`
- `services/mlx-worker-python/tests/test_dataset_registry.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/dataset_registry_limit_probe.py`
- `scripts/dataset_registry_preview_limit_probe.py`

## Slice

Cache each directory entry's README classification and supported dataset suffix
predicate result inside `_supported_scan_entry_records()`. The scan helper still
avoids file stat calls for unsupported names, still yields directories for
recursive preview traversal, and still filters README metadata files, but it no
longer recomputes `_is_supported_dataset_file_name()` for unsupported files,
broken supported files, or supported non-regular entries after the directory
probe.

## Success Metrics

Use the registered probe metrics:

- `elapsed_ms_mean` lower is better for limit-one preview scans,
- `multi_limit_elapsed_ms_mean` lower is better for multi-file limited previews,
- `peak_bytes_mean` and `multi_limit_peak_bytes_mean` lower is better or neutral,
- returned row/file counts must remain unchanged.

The change is accepted only if focused tests pass, changed-scope coverage is at
least 95%, and the registered probe improves or remains non-regressive locally
on Linux and in PR-scoped CI.

## 2026-07 heap key helper slice

A follow-up Python-only slice keeps the same registered probe and narrows the
`heapq.nsmallest()` callback overhead in `_first_supported_scan_entries()` by
replacing the per-call `lambda item: item[0]` key with the C-level
`operator.itemgetter(0)` helper. Traversal order, filtering semantics, and the
limited preview result shape remain unchanged.
