# Prefix cold index orphan precheck performance slice

## Scope

This Python-only performance slice is limited to `worker.runtime.prefix_block_store.ColdPrefixStore._ensure_loaded_locked()`.
Cold-tier startup rebuilds the in-memory index from `.meta.json` sidecars. When snapshot files are missing, the prior reload path opened and decoded each orphaned sidecar before discovering that the expected `.kv.safetensors` file was absent. This slice reuses the snapshot filename set collected by the existing `os.scandir()` pass to prune filename-orphaned sidecars before JSON decode.

## Registered performance probe

The affected path is covered by the registered PR-scoped performance probe `prefix-cold-index-scandir` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries and watches:

- `services/mlx-worker-python/worker/runtime/prefix_block_store.py`
- `services/mlx-worker-python/tests/test_prefix_cache_cold_tier.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/prefix_cold_index_scandir_probe.py`
- `infra/perf/pr_scoped_probes.json`

The probe now includes an orphan-sidecar scenario and reports `json_load_calls_mean` in addition to cold-index reload elapsed time, `scandir_calls_mean`, and `path_glob_calls_mean`.

## Implementation plan

1. Add regression coverage proving filename-orphaned sidecars are pruned before `json.load(...)` is invoked.
2. During reload, derive the expected snapshot filename from each metadata sidecar filename and skip JSON decode when that filename was not observed in the `os.scandir()` snapshot set.
3. Preserve the existing post-decode session digest check so malformed sidecars with mismatched `session_id` values are still removed.
4. Extend the registered probe to recreate orphan sidecars for every sample and count JSON decode calls.
5. Run the registered focused test command, changed-scope coverage command, and registered probe locally on Linux; rely on PR-scoped CI to replay the registered probe before merge.

## Validation notes

This slice is locally verifiable on Linux. No Swift runtime effect is claimed.
