# PR-scoped compiled glob startswith binding

## Scope

This Python-only performance slice is limited to the compiled-glob matcher helper
in `services/mlx-worker-python/worker/productization/pr_scoped_performance.py`.
The helper is used while selecting PR-scoped performance probes for changed paths.

The behavior remains unchanged: exact compiled matcher order is preserved, literal
prefix filters still skip regex matching when the changed path cannot match, and
paths without matching prefixes still fall through to the compiled regex check.

## Registered Probe

The affected path is already covered by the registered PR-scoped performance
probe `pr-scoped-performance-scope-matcher` in
`infra/perf/pr_scoped_probes.json`. The entry has focused `test_command`,
`coverage_command`, and `probe_command` values for the scope-selection code,
registry entry, and PR-scoped performance tests.

## Implementation Plan

1. Keep `_matches_any_compiled_glob()` semantics unchanged.
2. Bind `path.startswith` once before the matcher loop so each literal-prefix
   check avoids repeated method lookup on the hot path.
3. Run the registered focused tests, changed-scope coverage command,
   `git diff --check`, and the registered probe locally on Linux.
4. Use GitHub Actions PR-scoped performance as the final registered probe gate
   before merge.

## Expected Signal

The registered probe should report neutral-to-lower `build_scope_report_ms_mean`
for scope selection while preserving `selected_probe_count_mean` and
`force_all_selected_mean`.
