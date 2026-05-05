# PR-scoped Performance Force-All Exact Intersection Slice

## Scope

This Python-only performance slice narrows the PR-scoped performance scope matcher hot path in `services/mlx-worker-python/worker/productization/pr_scoped_performance.py`.

`build_scope_report(...)` currently calls `_path_matches_force_all(...)` for every changed path. That helper checks exact force-all path membership and then runs wildcard-prefix matching for each path. The registered scope-matcher probe uses thousands of changed paths and only a small fixed force-all set, so the exact force-all check can be moved to one set intersection before the wildcard loop.

## Registered probe

The affected path is covered by the registered PR-scoped probe `pr-scoped-performance-scope-matcher` in `infra/perf/pr_scoped_probes.json`. The probe declares focused `test_command`, `coverage_command`, and `probe_command` entries and measures `build_scope_report_ms_mean`, `selected_probe_count_mean`, and `force_all_selected_mean`.

## Implementation plan

1. Preserve current changed-file normalization and selected-probe semantics.
2. Compute `force_all` with a direct exact-path set intersection first.
3. Only scan changed paths through compiled wildcard matchers when no exact force-all file changed.
4. Add/adjust focused tests proving exact force-all detection still selects all probes and wildcard detection still works.
5. Compare `pr-scoped-performance-scope-matcher` against `origin/main` with the registered local probe before pushing.

## Verification

This slice is Python-only and locally verifiable on Linux with:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_force_selects_all_on_infra_change services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_force_selects_all_on_pr_scope_script_change services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_large_changed_set_preserves_exact_selection_semantics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_match_probe_indexes_deduplicates_repeated_watch_globs services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_match_probe_indexes_exact_only_intersects_changed_paths services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_compiled_glob_pattern_reuses_cached_regex services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_compiled_glob_matching_preserves_prefix_short_circuit services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dispatch_probe_impl_supports_pr_scoped_scope_matcher_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_smokes_return_metrics_against_current_repo
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_force_selects_all_on_infra_change services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_force_selects_all_on_pr_scope_script_change services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_large_changed_set_preserves_exact_selection_semantics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_match_probe_indexes_deduplicates_repeated_watch_globs services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_match_probe_indexes_exact_only_intersects_changed_paths services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_compiled_glob_pattern_reuses_cached_regex services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_compiled_glob_matching_preserves_prefix_short_circuit services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dispatch_probe_impl_supports_pr_scoped_scope_matcher_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_smokes_return_metrics_against_current_repo
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/productization/pr_scoped_performance.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/pr_scoped_performance_run.py --registry infra/perf/pr_scoped_probes.json --probe-id pr-scoped-performance-scope-matcher --base-repo <origin-main-worktree> --head-repo "$PWD" --output-json .runtime/pr-scope-matcher-result.json
```

CI remains the merge gate for the registered PR-scoped performance report.
