# Closure Audit Probe-Source Priority Optimization Plan

## Goal
Reduce redundant text-file scanning in `services/mlx-worker-python/worker/productization/closure_audit.py` by prioritizing a small curated set of high-signal evidence files before falling back to the full repository crawl.

## Linux-Only Constraint
This cron run executes on Linux, so the implementation must stay inside Python and repository CI surfaces that can be verified locally with focused pytest, changed-scope coverage, and a local performance probe.

## Touched Files
- `services/mlx-worker-python/worker/productization/closure_audit.py`
- `services/mlx-worker-python/tests/test_closure_audit.py`
- `services/mlx-worker-python/worker/productization/pr_scoped_performance.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`

## Optimization Hypothesis
The closure audit currently scans broad text roots in sorted order until every required metric probe has three retained sources. In the real repository, the required probe names already appear in a small set of canonical runbooks and progress evidence files. Prioritizing those curated files should reduce unnecessary reads and wall time while preserving fallback semantics.

## Performance Probe
Use the existing PR-scoped performance probe `closure-audit-probe-source-short-circuit`, updated to seed a repository shape closer to the real one and report the same concrete metrics:
- `elapsed_ms_mean`
- `probe_file_reads_mean`

Success means the head branch keeps behavior identical while reducing both metrics versus `origin/main`.

## Verification Commands
```text
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_closure_audit.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_closure_audit.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/productization/closure_audit.py services/mlx-worker-python/worker/productization/pr_scoped_performance.py services/mlx-worker-python/tests/test_closure_audit.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 -c "import json; from pathlib import Path; from worker.productization.pr_scoped_performance import _probe_closure_audit as probe; print(json.dumps(probe(Path.cwd()), sort_keys=True))"
git diff --check
```
