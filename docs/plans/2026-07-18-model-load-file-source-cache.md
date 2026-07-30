# Model Load File Detection Source Cache

## Scope

This Python-only performance slice is limited to
`worker.model_load_trust._model_files_detection_source()` on the executable
model-file fallback path.

The fallback path already caches directory scans by directory stat. Repeated
policy resolutions for the same unchanged executable model directory still build
the same `model_files:` detection-source string from the cached file-name tuple
on every rejection. This slice reuses that string for stable executable-file
name tuples while preserving the sorted tuple produced by the scanner.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`model-load-config-json-bytes` in `infra/perf/pr_scoped_probes.json`.

The probe includes focused `test_command`, `coverage_command`, and
`probe_command` entries for `services/mlx-worker-python/worker/model_load_trust.py`,
`services/mlx-worker-python/tests/test_model_load_trust.py`,
`services/mlx-worker-python/tests/test_pr_scoped_performance.py`, and
`scripts/model_load_config_json_bytes_probe.py`.

## Implementation plan

1. Add a small LRU cache around executable model-file detection-source string
   construction.
2. Add a focused regression test proving repeated single-file detection-source
   construction hits the cache and keeps the exact source text.
3. Run the registered focused tests, changed-scope coverage, and local registered
   probe on Linux.
4. Use GitHub Actions PR-scoped performance as the merge gate.

## Expected metrics

The primary expected improvement is lower `executable_elapsed_ms_mean` in
`scripts/model_load_config_json_bytes_probe.py`. The config-json `auto_map` path
should remain neutral because it returns before executable-file source string
construction.
