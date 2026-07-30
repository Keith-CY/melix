# Prefix cold index balanced orphan precheck

## Scope

This Python-only performance slice is limited to `ColdPrefixStore._ensure_loaded_locked()` cold-index reloads in `services/mlx-worker-python/worker/runtime/prefix_block_store.py`.

The existing cold-index reload already used a single `os.scandir()` pass and filename-derived snapshot names to prune orphaned metadata before JSON decode when snapshot sidecars were fewer than metadata sidecars. That count-only guard can miss balanced dirty directories: for example, one missing snapshot sidecar plus one unrelated stray snapshot keeps the counts equal, so the orphan metadata is decoded before being removed.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe `prefix-cold-index-scandir` in `infra/perf/pr_scoped_probes.json`. The entry has focused `test_command`, `coverage_command`, and `probe_command` entries and reports `elapsed_ms_mean`, `elapsed_ms_min`, `elapsed_ms_p95`, `json_load_calls_mean`, `path_glob_calls_mean`, and `scandir_calls_mean`.

This slice updates the probe fixture to include stray snapshot files alongside orphan metadata so the registered probe measures the balanced-dirty-directory case directly. The `json_load_calls_mean` metric now counts the hot-path `json.loads()` call used by the implementation.

## Optimization plan

1. Keep collecting metadata rows and snapshot names from one `os.scandir()` pass.
2. Always derive the expected snapshot name from each metadata filename and prune filename-orphaned metadata before JSON decode.
3. Preserve the post-decode session-id digest check for malformed or mismatched metadata whose filename-sidecar pair exists but whose payload points to a different session.
4. Run focused tests, changed-scope coverage, and the registered probe locally on Linux before opening the PR.
5. Use GitHub Actions PR-scoped performance as the registered probe merge gate.

## Verification

- Focused cold-prefix tests pass, including balanced orphan metadata with unrelated stray snapshots.
- Changed-scope coverage for touched Python/test/probe/registry files remains at or above 95%.
- Local registered probe should keep `path_glob_calls_mean=0`, `scandir_calls_mean=1`, and reduce `json_load_calls_mean` in the balanced orphan fixture from all metadata rows to valid metadata rows only; CI remains the merge-gate source of truth for the registered probe report.
