# Dataset Registry Supported Suffix Binding Performance Slice

## Scope

This Python-only performance slice is limited to
`worker.dataset_registry.catalog._is_supported_dataset_file_name()`, the suffix
predicate used by dataset registry discovery and limited preview scans.

## Registered Probe

The affected path is covered by the registered PR-scoped probe
`dataset-registry-preview-limit-short-circuit` in
`infra/perf/pr_scoped_probes.json`. The entry includes focused `test_command`,
`coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/dataset_registry/catalog.py`
- `services/mlx-worker-python/tests/test_dataset_registry.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/dataset_registry_preview_limit_probe.py`

## Slice

Bind the supported suffix mapping as a default argument for the hot suffix
predicate. This preserves suffix handling, lowercase fast paths, and mixed-case
fallback behavior while avoiding repeated global mapping lookups in scan-heavy
preview paths.

## Success Metrics

Use the registered probe metrics:

- `elapsed_ms_mean` lower is better for limit-one preview scans,
- `multi_limit_elapsed_ms_mean` lower is better for multi-file limited previews,
- `peak_bytes_mean` and `multi_limit_peak_bytes_mean` lower is better or neutral,
- returned row/file counts must remain unchanged.

The change is accepted only if focused tests pass, changed-scope coverage is at
least 95%, and the registered probe improves or remains non-regressive locally
on Linux and in PR-scoped CI.
