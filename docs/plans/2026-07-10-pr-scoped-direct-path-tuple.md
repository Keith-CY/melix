# PR-scoped direct path tuple scope matcher slice

## Scope

This Python-only performance slice targets the PR-scoped performance scope matcher in `services/mlx-worker-python/worker/productization/pr_scoped_performance.py`.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe `pr-scoped-performance-scope-matcher` in `infra/perf/pr_scoped_probes.json`. The registry entry already includes focused `test_command`, `coverage_command`, and `probe_command` entries for local Linux and CI validation.

## Change

Keep matching semantics unchanged while reducing per-scope matcher overhead by reusing the already sorted direct changed-path tuple from `_scope_selection_uncached()` when context-only paths are filtered. This avoids converting the direct path subset back into an unordered set and sorting it again before matching probe watch paths.

## Verification plan

Run the registered focused tests, changed-scope coverage command, and registered probe locally on Linux before opening the PR. GitHub Actions PR-scoped performance remains the merge gate for the registered probe report.

## Success criteria

- Focused behavior tests pass.
- Changed-scope coverage for `pr_scoped_performance.py` and its focused tests is at least 95 percent.
- Local registered probe shows lower or non-regressing `build_scope_report_ms_mean` while preserving `selected_probe_count_mean` and `force_all_selected_mean`.
- PR-scoped performance CI selects and completes `pr-scoped-performance-scope-matcher` successfully before merge.
