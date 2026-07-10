# Prefix cold index snapshot-name set performance slice

## Scope

This Python-only performance slice is limited to `worker.runtime.prefix_block_store.ColdPrefixStore._ensure_loaded_locked()`.
Cold-tier startup rebuilds the in-memory index from `.meta.json` sidecars and previously probed each expected `.kv.safetensors` snapshot path separately while replaying metadata. This slice keeps the reload semantics for regular cold-store files while reusing snapshot filenames discovered during the existing `os.scandir()` pass, avoiding per-metadata `Path.is_file()` snapshot probes.

## Registered performance probe

The affected path is covered by the registered PR-scoped performance probe `prefix-cold-index-scandir` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries and watches:

- `services/mlx-worker-python/worker/runtime/prefix_block_store.py`
- `services/mlx-worker-python/tests/test_prefix_cache_cold_tier.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/prefix_cold_index_scandir_probe.py`

The probe reports cold-index reload elapsed time plus `scandir_calls_mean` and `path_glob_calls_mean` for the synthetic cold tier.

## Implementation plan

1. Add regression coverage that cold-index reload reuses snapshot names from the directory scan instead of issuing per-meta `Path.is_file()` checks for `.kv.safetensors` snapshots.
2. During the existing `os.scandir()` pass, collect regular snapshot filenames alongside metadata paths.
3. Use the collected filename set to identify orphaned metadata during index replay.
4. Run the registered focused test command, changed-scope coverage command, and registered probe locally on Linux.
5. Use GitHub Actions PR-scoped performance as the merge gate after opening the PR.

## Validation notes

This slice is locally verifiable on Linux. No Swift runtime effect is claimed.
