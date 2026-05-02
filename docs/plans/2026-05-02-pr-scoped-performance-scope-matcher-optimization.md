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
1. Introduce a small internal literal-prefix fast path for glob matching so paths that cannot match a probe glob avoid regex lookup/matching entirely.
2. Preserve existing scope-selection semantics exactly, including:
   - force-all behavior
   - watch glob matching behavior
   - selected probe IDs and ordering
3. Add focused regression tests for the optimized matcher path and the dedicated probe selection.
4. Use the registered `pr-scoped-performance-scope-matcher` probe so CI measures the optimized scope-selection path directly.

## Slice update: literal-prefix miss short-circuit
This slice keeps the existing registry and probe shape intact. The affected path already has the registered `pr-scoped-performance-scope-matcher` probe with focused `test_command`, `coverage_command`, and `probe_command` entries. The code change derives and caches the literal prefix before the first glob metacharacter (`*`, `?`, or `[`) and uses that prefix to skip impossible path/glob pairs before regex matching. `_match_probe_indexes(...)` also builds the `(prefix, compiled regex, probe indexes)` matcher table once per scope report so the hot path avoids repeated cache lookups while preserving exact-match semantics through the existing regex matcher.

## Implemented slice
- Split force-all and watch-glob matching into exact-path and wildcard paths so exact changed files avoid regex glob checks.
- Cache the derived watch-glob index and the scope-report registry load by path, mtime, and size for repeated scope computations in the same process.
- Keep the public `load_probe_registry(...)` parser uncached so direct validation callers still observe file contents immediately.

## Slice update: force-all wildcard matcher reuse
- Cache the compiled force-all wildcard matcher table once per process instead of re-deriving the literal prefix and regex lookup on every changed path.
- Keep exact-path force-all matching first so common exact infra/script paths still return without invoking wildcard matching.
- Keep selection semantics unchanged; this only changes matcher setup reuse in the scope-report hot path.

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
