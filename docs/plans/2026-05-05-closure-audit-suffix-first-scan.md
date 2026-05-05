# Closure audit suffix-first text scan

## Scope

This performance slice is limited to the Python closure-audit probe source discovery path in `services/mlx-worker-python/worker/productization/closure_audit.py`.

## Registered probe

The affected path is covered by the registered PR-scoped probe `closure-audit-probe-source-short-circuit` in `infra/perf/pr_scoped_probes.json`. The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries and measures closure-audit elapsed time plus probe-source completeness.

## Optimization

`_iter_text_files_sorted()` already avoids following directory symlinks and yields repository text files in deterministic order. This slice keeps that behavior but checks `entry.name.endswith(_TEXT_FILE_SUFFIXES)` before calling `entry.is_file(follow_symlinks=False)` for non-directory entries. Non-text files therefore avoid an unnecessary file-status call and `Path` allocation during fallback repository scans.

## Verification plan

Run the registered probe's local Linux commands:

1. Focused closure-audit pytest coverage from `closure-audit-probe-source-short-circuit`.
2. Changed-scope coverage from `closure-audit-probe-source-short-circuit`.
3. Registered probe comparison with `scripts/pr_scoped_performance_run.py` against an `origin/main` baseline worktree.

## Success criteria

- Focused tests pass.
- Changed-scope coverage remains at or above 95% for touched files.
- The registered probe shows non-regressing or improved `elapsed_ms_mean`; `probe_sources_complete` remains true.
- PR-scoped performance CI selects and completes the registered probe before merge.
