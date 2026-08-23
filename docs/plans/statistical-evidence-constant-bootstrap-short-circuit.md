# Statistical Evidence Constant Bootstrap Short-Circuit

## Goal

Avoid redundant paired-bootstrap and analytical interval work when every paired outcome has the same value. In that case every bootstrap replicate and the analytical margin are exact, so the percentile interval can be returned without allocating and sorting the replicate vector, and the analytical interval can reuse the same constant-outcome scan instead of walking the sample again.

## Linux-only constraint

This is a Python worker/productization slice and is verifiable on Linux with focused pytest, changed-scope coverage, and a local synthetic performance probe.

## Touched files

- `services/mlx-worker-python/worker/productization/statistical_evidence.py`
- `services/mlx-worker-python/tests/test_statistical_evidence.py`
- `docs/plans/statistical-evidence-constant-bootstrap-short-circuit.md`

## Performance probe definition

Run `/tmp/statistical_evidence_constant_probe.py <origin-main-worktree> <head-worktree>` against a synthetic homogeneous `paired_outcomes=(1.0,) * 200000` workload with `bootstrap_iterations=1000` and five samples. Compare mean elapsed time and traced peak allocation while asserting the returned bootstrap bounds stay exactly `1.0`.

The repository already has the `statistical-evidence-bootstrap-single-sort` PR-scoped performance probe watching this production file and test file. This slice relies on that registered probe to validate no regression in the mixed-outcome bootstrap path, and the local homogeneous probe validates that the shared mean/constant scan improves the constant-outcome path.

## 2026-08-23 mixed-outcome summary comparison gate

This follow-up Python-only slice stays inside `services/mlx-worker-python/worker/productization/statistical_evidence.py` and the existing registered `statistical-evidence-bootstrap-single-sort` probe. The summary loop still computes the mean across every outcome, but after the first unequal value has proven the sample is non-constant it stops performing repeated equality comparisons for the remaining tail. Bootstrap and analytical interval behavior is unchanged; only the constant-detection guard work on mixed outcomes is reduced.

## Success metrics

- Focused statistical evidence pytest passes.
- Changed-scope coverage for touched executable Python files is at least 95%.
- Registered `statistical-evidence-bootstrap-single-sort` probe shows lower elapsed time on the mixed-outcome workload versus `origin/main`.
- `git diff --check` passes.
