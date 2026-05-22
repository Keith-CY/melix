# Statistical Evidence Bootstrap Single-Sort Optimization

## Goal

Reduce redundant work in the paired bootstrap confidence interval path by sorting the bootstrap replicate vector once and using the standard-library bulk equal-weight sampler for each bootstrap replicate, while preserving the paired bootstrap payload shape and deterministic seed behavior.

## Touched Files

- `services/mlx-worker-python/worker/productization/statistical_evidence.py`
- `services/mlx-worker-python/tests/test_statistical_evidence.py`
- `scripts/statistical_evidence_bootstrap_probe.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`

## Linux-Only Constraint

This is a pure Python worker/productization slice and can be verified locally on Linux with focused pytest, changed-scope coverage, and an explicit PR-scoped performance probe.

## Performance Probe

Register `statistical-evidence-bootstrap-single-sort` in the PR-scoped performance registry. The probe runs a deterministic synthetic paired-outcome workload through `build_paired_statistical_evidence(...)` and reports:

- `elapsed_ms_mean` (lower is better)
- `peak_bytes_mean` (lower is better)
- `sorted_calls_mean` (lower is better)
- `sample_size` and `bootstrap_iterations` guard metrics
- interval guard metrics including `lower_bound_mean` and `upper_bound_mean`

## Success Metrics

- Preserve bootstrap and analytical interval payload semantics.
- Sort bootstrap replicates once per interval instead of once per percentile bound.
- Preserve the existing per-bootstrap equal-weight-with-replacement sampling semantics while reducing duplicate percentile work and using `random.Random.choices(...)` for the inner draw loop.
- Reuse an already-normalized all-`float` paired-outcome tuple instead of allocating a duplicate normalization tuple on the registered bootstrap probe path; continue converting `int`, `bool`, and mixed numeric inputs through `float(...)`.
- Changed-scope automated coverage is at least 95%.
- Local base-vs-head probe shows lower elapsed time and/or peak traced bytes while preserving valid interval guard ordering.
- `git diff --check` passes.

## Verification Commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q \
  services/mlx-worker-python/tests/test_statistical_evidence.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_statistical_evidence_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_statistical_evidence_bootstrap_probe_script_emits_metrics

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q \
  services/mlx-worker-python/tests/test_statistical_evidence.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_statistical_evidence_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_statistical_evidence_bootstrap_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json \
  services/mlx-worker-python/worker/productization/statistical_evidence.py \
  services/mlx-worker-python/tests/test_statistical_evidence.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py \
  scripts/statistical_evidence_bootstrap_probe.py

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/statistical_evidence_bootstrap_probe.py
python3 scripts/pr_scoped_performance_run.py \
  --registry infra/perf/pr_scoped_probes.json \
  --probe-id statistical-evidence-bootstrap-single-sort \
  --base-repo /path/to/base-repo \
  --head-repo /path/to/head-repo \
  --output /tmp/statistical-evidence-probe.json

git diff --check
```
