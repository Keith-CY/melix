# Prefix cold index meta-name cache

## Scope

This Python-only performance slice is limited to `ColdPrefixStore._ensure_loaded_locked()` cold-index reloads in `services/mlx-worker-python/worker/runtime/prefix_block_store.py`. The registered probe models a cold directory with valid snapshot sidecars plus orphaned metadata files. The previous scandir implementation saved only each metadata path string, then recreated a `Path` for every metadata row before using `.name` for the orphan filename precheck.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe `prefix-cold-index-scandir` in `infra/perf/pr_scoped_probes.json`. The entry has focused `test_command`, `coverage_command`, and `probe_command` entries and reports `elapsed_ms_mean`, `json_load_calls_mean`, `path_glob_calls_mean`, and `scandir_calls_mean`.

## Optimization plan

1. Keep collecting metadata rows from one `os.scandir()` pass.
2. Store `(entry.path, entry.name)` for metadata sidecars so the orphan precheck can reuse the scandir-provided filename without constructing a `Path` first.
3. Preserve orphan removal, valid metadata parsing, sorted reload order, and no-`Path.glob()` behavior.
4. Run focused tests, changed-scope coverage, and the registered probe locally on Linux before opening the PR.
5. Use GitHub Actions PR-scoped performance as the registered probe merge gate.

## Verification

- Focused cold-prefix tests pass.
- Changed-scope coverage for touched Python/test/probe/registry files remains at or above 95%.
- Local registered probe should keep `json_load_calls_mean=600`, `path_glob_calls_mean=0`, `scandir_calls_mean=1`, and improve or stay stable on `elapsed_ms_mean`; CI remains the merge-gate source of truth for the registered probe report.
