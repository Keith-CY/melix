# PR scoped performance context-path disjoint fast path

This Python-only performance slice is limited to `worker.productization.pr_scoped_performance._scope_selection_uncached()`.

## Registered probe

The affected path is covered by the registered PR-scoped probe `pr-scoped-performance-scope-matcher` in `infra/perf/pr_scoped_probes.json`. The probe has focused `test_command`, `coverage_command`, and `probe_command` entries for `services/mlx-worker-python/worker/productization/pr_scoped_performance.py` and `services/mlx-worker-python/tests/test_pr_scoped_performance.py`.

## Optimization

Most PR scope calculations do not include context-only force-all paths such as the probe registry or scope matcher implementation files. In that common case, the existing normalized `changed_paths` tuple and `changed_path_set` are already the exact direct-path inputs needed by the matcher.

This slice adds an `isdisjoint` fast path so `_scope_selection_uncached()` reuses those normalized inputs directly when no context-only path is present. The fallback path still filters context-only paths before direct probe matching, preserving force-all/context semantics.

## Verification plan

1. Add a focused regression test proving the no-context path reuses the full normalized tuple/set inputs.
2. Run the registered probe's focused tests.
3. Run the registered changed-scope coverage command.
4. Run the registered scope matcher probe locally on Linux and compare against the pre-change baseline.
5. Use GitHub Actions PR-scoped performance as the merge gate.

## Evidence

Local Linux verification:

- Focused regression tests: `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_selection_reuses_sorted_direct_path_tuple_without_resorting services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_selection_reuses_full_path_set_when_no_context_only_paths services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_large_changed_set_preserves_exact_selection_semantics` → 3 passed.
- Registered focused tests: `pr-scoped-performance-scope-matcher` `test_command` → 25 passed.
- Registered changed-scope coverage: `pr-scoped-performance-scope-matcher` `coverage_command` → TOTAL 16/16 changed lines covered, 100.00%.
- Registered local probe: baseline `build_scope_report_ms_mean=2.257385`; head registered command `build_scope_report_ms_mean=2.173655`; delta `-0.083730 ms`, speedup `1.0385x` (3.71% lower). Selection count remained `7.0`; force-all remained `0.0`.

GitHub Actions PR-scoped performance remains the final registered probe validation and merge gate.
