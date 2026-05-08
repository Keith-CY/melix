# Statistical Evidence Constant Bootstrap Short-Circuit

## Goal

Avoid redundant paired-bootstrap sampling when every paired outcome has the same value. In that case every bootstrap replicate has the same mean, so the percentile interval can be returned exactly without allocating and sorting the replicate vector.

## Linux-only constraint

This is a Python worker/productization slice and is verifiable on Linux with focused pytest, changed-scope coverage, and a local synthetic performance probe.

## Touched files

- `services/mlx-worker-python/worker/productization/statistical_evidence.py`
- `services/mlx-worker-python/tests/test_statistical_evidence.py`
- `infra/perf/pr_scoped_probes.json`
- `docs/plans/statistical-evidence-constant-bootstrap-short-circuit.md`

## Performance probe definition

Run `/tmp/statistical_evidence_constant_probe.py <origin-main-worktree> <head-worktree>` against a synthetic homogeneous `paired_outcomes=(1.0,) * 10000` workload with `bootstrap_iterations=1000` and five samples. Compare mean elapsed time and traced peak allocation while asserting the returned bootstrap bounds stay exactly `1.0`.

The repository already has the `statistical-evidence-bootstrap-single-sort` PR-scoped performance probe watching this production file and test file. This slice relies on that registered probe to validate no regression in the mixed-outcome bootstrap path, and the local homogeneous probe validates the new short-circuit path.

## Success metrics

- Focused statistical evidence pytest passes.
- Changed-scope coverage for touched executable Python files is at least 95%.
- Local homogeneous bootstrap probe shows lower elapsed time and peak traced allocation on head than `origin/main`.
- `git diff --check` passes.
