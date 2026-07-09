# Prefix Cold Index Suffix Filter Performance Slice

## Scope

This Python-only performance slice is limited to cold prefix-cache index reloads in
`worker.runtime.prefix_block_store.ColdPrefixStore._ensure_loaded_locked`.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe
`prefix-cold-index-scandir` in `infra/perf/pr_scoped_probes.json`. The probe has
focused `test_command`, `coverage_command`, and `probe_command` entries, watches
the production file, focused tests, probe script, and registry entry, and reports
cold-index reload timing plus `scandir`/legacy `Path.glob` counters.

## Plan

1. Preserve the existing single-`os.scandir()` reload path and deterministic
   sidecar sorting.
2. Filter `DirEntry.name` by the `.meta.json` suffix before calling
   `DirEntry.is_file(follow_symlinks=False)` so non-metadata snapshot files avoid
   an unnecessary file-stat check during cold-index reload.
3. Add a regression test that proves non-metadata entries do not call
   `is_file()` during index loading.
4. Update the registered probe commands to include the new focused regression
   test.
5. Run the focused tests, changed-scope coverage, and registered probe locally on
   Linux before opening the PR. GitHub Actions PR-scoped performance remains the
   merge gate for the registered probe report.

## Validation boundary

This slice changes Python filesystem scanning behavior and is locally verifiable
on Linux. No Swift runtime behavior is changed.
