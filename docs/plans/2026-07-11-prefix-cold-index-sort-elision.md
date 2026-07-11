# Prefix cold index scan-order sort elision

## Scope

This Python-only performance slice is limited to `ColdPrefixStore._ensure_loaded_locked()` cold-index reloads in `services/mlx-worker-python/worker/runtime/prefix_block_store.py`. The registered probe models a cold directory with valid snapshot sidecars plus orphaned metadata files.

The current reload path already uses a single `os.scandir()` pass and stores `(entry.path, entry.name)` for each metadata sidecar. This follow-up removes the additional full metadata-list sort before parsing. Cold-index semantics are keyed by `session_id`, eviction ordering uses each record's persisted `stored_at`, and orphan cleanup is name-based, so reload correctness does not depend on lexicographic filesystem order.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe `prefix-cold-index-scandir` in `infra/perf/pr_scoped_probes.json`. The entry has focused `test_command`, `coverage_command`, and `probe_command` entries and reports `elapsed_ms_mean`, `json_load_calls_mean`, `path_glob_calls_mean`, and `scandir_calls_mean`.

## Optimization plan

1. Keep collecting metadata rows and snapshot names from one `os.scandir()` pass.
2. Iterate metadata sidecars in scan order instead of sorting all rows first.
3. Preserve orphan removal, valid metadata parsing, no-`Path.glob()` behavior, and `stored_at`-based budget eviction semantics.
4. Run focused tests, changed-scope coverage, and the registered probe locally on Linux before opening the PR.
5. Use GitHub Actions PR-scoped performance as the registered probe merge gate.

## Verification

- Focused cold-prefix tests pass.
- Changed-scope coverage for touched Python/test/probe/registry files remains at or above 95%.
- Local registered probe should keep `json_load_calls_mean=600`, `path_glob_calls_mean=0`, `scandir_calls_mean=1`, and reduce `elapsed_ms_mean` by skipping the metadata-list sort; CI remains the merge-gate source of truth for the registered probe report.
