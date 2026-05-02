# PR-Scoped Performance Scope Matcher Optimization Plan

## Goal
Reduce redundant glob-matching work in Melix's PR-scoped performance harness when `build_scope_report(...)` selects probes for a changed file set.

## Why this slice
The current implementation repeatedly runs glob matching for every changed path against every probe watch glob and the force-all globs. On large diffs this repeats equivalent matcher setup work and is a safe Linux-verifiable Python-only optimization target.

## Linux-only constraint
This cron run executes on Linux and cannot validate the macOS/Swift app directly. The optimization must therefore stay inside the Python PR-scoped performance harness and use local focused pytest, changed-scope coverage, and an explicit local base-vs-head probe.

## Planned touched files
- `services/mlx-worker-python/worker/productization/pr_scoped_performance.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`

## Proposed implementation
1. Introduce a small internal fast path for scope selection that avoids repeating equivalent glob translation/matching work across every path × glob comparison.
2. Preserve existing scope-selection semantics exactly, including:
   - force-all behavior
   - watch glob matching behavior
   - selected probe IDs and ordering
3. Add focused regression tests for the optimized matcher path and the dedicated probe selection.
4. Register/update a dedicated PR-scoped performance probe for the harness so CI measures the optimized scope-selection path directly.

## Performance probe
- Probe target: `build_scope_report(...)` on a synthetic large changed-file set and current probe registry.
- Primary metrics:
  - `build_scope_report_ms_mean` lower is better
  - `selected_probe_count_mean` unchanged from baseline
  - `force_all_selected_mean` unchanged from baseline
- Probe strategy:
  - load the current registry from `infra/perf/pr_scoped_probes.json`
  - synthesize a representative large changed-file list with both matching and non-matching paths
  - compare `origin/main` vs head through the PR-scoped performance harness

## Success metrics
- Focused tests pass.
- Changed-scope automated coverage is at least 95% for touched executable scope.
- Local explicit probe shows lower `build_scope_report_ms_mean` with unchanged selection semantics.
- `git diff --check` passes.

## Verification commands
```text
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_pr_scoped_performance.py::<focused nodes>
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_pr_scoped_performance.py::<focused nodes>
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/productization/pr_scoped_performance.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 -c "... dedicated scope probe ..."
git diff --check
```
