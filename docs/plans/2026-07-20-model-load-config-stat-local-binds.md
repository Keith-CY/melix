# Model Load Config Stat Local Bind Slice

## Scope

This Python-only performance slice is limited to
`worker.model_load_trust._detect_custom_loader_requirement()` on the model-load
trust policy path.

Repeated trust-policy resolutions already cache parsed `config.json` payloads and
executable file scans by file or directory stat. The remaining per-resolution
work still performs global lookups for the bound `os.stat` helper and regular-file
predicate before it can reach those caches. This slice binds those helpers to
locals inside the config-stat branch so repeated policy checks keep the same
semantics while reducing hot-loop lookup overhead.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`model-load-config-json-bytes` in `infra/perf/pr_scoped_probes.json`.

The probe already includes focused `test_command`, `coverage_command`, and
`probe_command` entries for `services/mlx-worker-python/worker/model_load_trust.py`,
`services/mlx-worker-python/tests/test_model_load_trust.py`,
`services/mlx-worker-python/tests/test_pr_scoped_performance.py`, and
`scripts/model_load_config_json_bytes_probe.py`.

## Implementation plan

1. Keep the existing config-path and stat-based cache behavior unchanged.
2. Bind `_OS_STAT` and `_STAT_ISREG` to local variables in the config-stat branch
   before the repeated stat and regular-file checks.
3. Run the registered focused tests, changed-scope coverage, and local registered
   probe on Linux.
4. Use GitHub Actions PR-scoped performance as the merge gate.

## Expected metrics

The expected improvement is modest but measurable in
`scripts/model_load_config_json_bytes_probe.py` because both the `auto_map`
config path and executable fallback path pass through the config-stat branch on
every policy resolution. The primary metrics are `elapsed_ms_mean` and
`executable_elapsed_ms_mean`; memory metrics should remain neutral.
