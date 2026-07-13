# Model Load Executable File Scan Cache

## Scope

This Python-only performance slice is limited to `worker.model_load_trust._detect_executable_model_files()`.

The executable model-file fallback path currently scans the model directory on every policy resolution when `config.json` is present but does not declare an `auto_map` custom loader. Repeated policy resolution for the same unchanged model directory should reuse the executable-file scan result until the directory stat changes.

## Registered probe

The affected path is covered by the registered PR-scoped probe `model-load-config-json-bytes` in `infra/perf/pr_scoped_probes.json`.

The probe already has focused `test_command`, `coverage_command`, and `probe_command` entries for `services/mlx-worker-python/worker/model_load_trust.py`, `services/mlx-worker-python/tests/test_model_load_trust.py`, `services/mlx-worker-python/tests/test_pr_scoped_performance.py`, and `scripts/model_load_config_json_bytes_probe.py`. This slice adds the executable-file directory-stat cache regression test to the registered focused command set.

## Implementation plan

1. Add a stat-keyed LRU helper for executable model-file detection.
2. Keep missing paths and non-directories equivalent to the existing empty detection result.
3. Add a regression test proving repeated detection of an unchanged directory calls `os.scandir` once.
4. Run the registered focused tests, changed-scope coverage, and local registered probe on Linux.
5. Use GitHub Actions PR-scoped performance as the merge gate.

## Expected metrics

The primary expected improvement is lower `executable_elapsed_ms_mean` in `scripts/model_load_config_json_bytes_probe.py`. The config-json `auto_map` path should remain neutral because it already returns before executable-file scanning.
