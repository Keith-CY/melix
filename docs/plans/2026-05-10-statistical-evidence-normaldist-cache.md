# Statistical Evidence NormalDist Cache

## Scope

This slice targets the paired statistical evidence interval helper in
`services/mlx-worker-python/worker/productization/statistical_evidence.py`.
It keeps behavior unchanged while avoiding repeated `NormalDist` construction for
the analytical confidence interval z-value lookup used by
`build_paired_statistical_evidence`.

## Registered Probe

Affected path coverage is already registered through
`statistical-evidence-bootstrap-single-sort` in
`infra/perf/pr_scoped_probes.json`. The registry entry includes focused tests,
changed-scope coverage, and `scripts/statistical_evidence_bootstrap_probe.py` as
the performance probe.

## Verification

Run the focused registered-probe flow locally on Linux:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/pr_scoped_performance_run.py --registry infra/perf/pr_scoped_probes.json --probe-id statistical-evidence-bootstrap-single-sort --base-repo <baseline-worktree> --head-repo "$PWD" --output /tmp/stat_normaldist_probe.json
```

Success criteria:

- focused statistical evidence tests pass;
- changed-scope coverage remains at least 95%;
- registered probe reports no regression and preferably lower `elapsed_ms_mean`.
