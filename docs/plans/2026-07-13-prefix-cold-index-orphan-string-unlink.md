# Prefix cold index orphan string unlink

## Scope

This Python-only performance slice is limited to `ColdPrefixStore._ensure_loaded_locked()` cold-index reloads in `services/mlx-worker-python/worker/runtime/prefix_block_store.py`. The registered probe models a cold directory with valid snapshot sidecars plus orphaned metadata files.

The current reload path already uses one `os.scandir()` pass and reuses `entry.name` for the filename-based orphan precheck. This follow-up keeps the orphan precheck in that fast path by unlinking prechecked orphan metadata sidecars directly from the `entry.path` string instead of first constructing a `Path` object only to call `unlink()`.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe `prefix-cold-index-scandir` in `infra/perf/pr_scoped_probes.json`. The entry has focused `test_command`, `coverage_command`, and `probe_command` entries and reports `elapsed_ms_mean`, `elapsed_ms_min`, `elapsed_ms_p95`, `json_load_calls_mean`, `path_glob_calls_mean`, and `scandir_calls_mean`.

## Optimization plan

1. Keep collecting metadata rows and snapshot names from one `os.scandir()` pass.
2. For filename-prechecked orphan metadata sidecars, call an `os.unlink()` string-path helper rather than materializing `Path(meta_path_string)`.
3. Preserve valid metadata parsing, malformed metadata cleanup, no-`Path.glob()` behavior, and scandir-only cold index reload behavior.
4. Run focused tests, changed-scope coverage, and the registered probe locally on Linux before opening the PR.
5. Use GitHub Actions PR-scoped performance as the registered probe merge gate.

## Verification

- Focused cold-prefix tests pass.
- Changed-scope coverage for touched Python/test/plan files remains at or above 95%.
- Local registered probe should keep `json_load_calls_mean=600`, `path_glob_calls_mean=0`, `scandir_calls_mean=1`, and improve or stay stable on elapsed metrics; CI remains the merge-gate source of truth for the registered probe report.
