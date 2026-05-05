# Statistical Evidence Bootstrap Single-Sort Optimization

## Goal
Reduce redundant work in the paired bootstrap confidence interval path by sorting the bootstrap replicate vector once and reusing it for the lower and upper percentile bounds.

## Touched Files
- `services/mlx-worker-python/worker/productization/statistical_evidence.py`
- `services/mlx-worker-python/tests/test_statistical_evidence.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`

## Linux-Only Constraint
This is a pure Python worker/productization slice and can be verified locally on Linux with focused pytest, changed-scope coverage, and an explicit PR-scoped performance probe.

## Performance Probe
Register `statistical-evidence-bootstrap-single-sort` in the PR-scoped performance registry. The probe runs a deterministic synthetic paired-outcome workload through `build_paired_statistical_evidence(...)` and reports:
- `elapsed_ms_mean` (lower is better)
- `peak_bytes_mean` (lower is better)
- `sample_size`
- `bootstrap_iterations`
- `delta_accuracy`

## Success Metrics
- Focused statistical evidence tests pass.
- Changed executable line coverage is at least 95% for the touched scope.
- Local base-vs-head scoped probe shows lower elapsed time and lower or acceptable peak traced memory while preserving deterministic output fields.
- `git diff --check` passes.

## Verification Commands
```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_statistical_evidence.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_statistical_evidence_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_statistical_evidence.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_statistical_evidence_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/productization/statistical_evidence.py services/mlx-worker-python/tests/test_statistical_evidence.py services/mlx-worker-python/tests/test_pr_scoped_performance.py

python scripts/pr_scoped_performance_scope.py --base origin/main --head HEAD --registry infra/perf/pr_scoped_probes.json --output /tmp/statistical-scope.json
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python scripts/pr_scoped_performance_run.py --scope /tmp/statistical-scope.json --probe-id statistical-evidence-bootstrap-single-sort --base-ref origin/main --head-ref HEAD --output /tmp/statistical-probe.json

git diff --check
```
