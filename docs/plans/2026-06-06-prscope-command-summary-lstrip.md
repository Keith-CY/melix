# PR-scoped performance command-summary lstrip fast path

## Scope

This Python-only performance slice is limited to `_summarize_command` in
`services/mlx-worker-python/worker/productization/pr_scoped_performance.py`.

The slice keeps command-summary semantics unchanged while replacing the manual
line-by-line scan with a direct `lstrip`/first-newline path. The hot path used by
PR-scoped probe command reporting normally has leading whitespace, a first command
line, and additional body lines; it only needs the first non-empty command line
plus an ellipsis marker.

## Registered probe

The affected path is already covered by the registered PR-scoped performance
probe `pr-scoped-performance-scope-matcher` in
`infra/perf/pr_scoped_probes.json`.

The registered entry includes focused:

- `test_command` for scope selection, glob matching, command-summary behavior, and probe dispatch.
- `coverage_command` for changed-scope coverage on `pr_scoped_performance.py` and its tests.
- `probe_command` that reports `build_scope_report_ms_*` and `command_summary_ms_mean`.

## Verification plan

Run on Linux before pushing:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_force_selects_all_on_infra_change services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_exact_force_all_skips_wildcard_scan services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_force_selects_all_on_pr_scope_script_change services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_changed_paths_force_all_wildcards_handles_empty_matchers services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_changed_paths_force_all_wildcards_short_circuits_on_match services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_matches_any_glob_uses_explicit_short_circuit services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_coverage_paths_for_probe_uses_explicit_glob_matcher services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_empty_direct_paths_skips_probe_matching services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_large_changed_set_preserves_exact_selection_semantics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_match_probe_indexes_deduplicates_repeated_watch_globs services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_match_probe_indexes_exact_only_intersects_changed_paths services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_match_probe_indexes_reuses_cached_frozenset_without_copying services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_compiled_glob_pattern_reuses_cached_regex services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_glob_matching_exact_path_skips_regex_compile services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_compiled_glob_matching_preserves_prefix_short_circuit services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dispatch_probe_impl_supports_pr_scoped_scope_matcher_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_smokes_return_metrics_against_current_repo services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_command_summary_keeps_ci_heartbeats_compact services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_command_json_probe_rejects_missing_command_and_non_numeric_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_force_selects_all_on_infra_change services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_exact_force_all_skips_wildcard_scan services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_force_selects_all_on_pr_scope_script_change services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_changed_paths_force_all_wildcards_handles_empty_matchers services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_changed_paths_force_all_wildcards_short_circuits_on_match services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_matches_any_glob_uses_explicit_short_circuit services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_coverage_paths_for_probe_uses_explicit_glob_matcher services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_empty_direct_paths_skips_probe_matching services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_large_changed_set_preserves_exact_selection_semantics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_match_probe_indexes_deduplicates_repeated_watch_globs services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_match_probe_indexes_exact_only_intersects_changed_paths services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_match_probe_indexes_reuses_cached_frozenset_without_copying services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_compiled_glob_pattern_reuses_cached_regex services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_glob_matching_exact_path_skips_regex_compile services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_compiled_glob_matching_preserves_prefix_short_circuit services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dispatch_probe_impl_supports_pr_scoped_scope_matcher_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_smokes_return_metrics_against_current_repo services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_command_summary_keeps_ci_heartbeats_compact services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_command_json_probe_rejects_missing_command_and_non_numeric_metrics && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/productization/pr_scoped_performance.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 -c "import json; from pathlib import Path; from worker.productization.pr_scoped_performance import _probe_pr_scoped_scope_matcher as probe; print(json.dumps(probe(Path.cwd()), sort_keys=True))"
```

GitHub Actions PR-scoped performance remains the final merge gate.

## Success criteria

- Focused tests pass.
- Changed-scope coverage is at or above the repository threshold for the touched scope.
- Local registered probe shows lower `command_summary_ms_mean` with unchanged scope-selection counts.
- PR-scoped performance CI completes successfully before merge.
