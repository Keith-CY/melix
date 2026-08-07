# Statistical Evidence Bootstrap Replicate Comprehension

## Goal

Reduce Python loop overhead in the paired bootstrap confidence interval path by building the replicate vector with a list comprehension before the existing in-place sort.

## Scope

- `services/mlx-worker-python/worker/productization/statistical_evidence.py`
- `docs/plans/2026-07-13-statistical-evidence-bootstrap-comprehension.md`

No protocol, dependency, or generated artifact changes are included.

## Linux verification boundary

This is a Python-only worker/productization slice and is fully locally verifiable on Linux with focused pytest, changed-scope coverage, and the registered PR-scoped performance probe.

## Registered probe

Affected path: `services/mlx-worker-python/worker/productization/statistical_evidence.py`

Registered PR-scoped probe: `statistical-evidence-bootstrap-single-sort` in `infra/perf/pr_scoped_probes.json`. The registry entry already includes focused `test_command`, `coverage_command`, and `probe_command` entries and watches this source file, the statistical evidence tests, the PR-scoped performance tests, the registry, and `scripts/statistical_evidence_bootstrap_probe.py`.

The probe reports:

- `elapsed_ms_mean` (lower is better)
- `peak_bytes_mean` (lower is better)
- `sorted_calls_mean` (lower is better)
- deterministic interval guard metrics

## Expected behavior

The slice preserves deterministic bootstrap semantics for a fixed `bootstrap_seed`, keeps one in-place replicate sort, and leaves short-circuit handling for empty, zero-iteration, singleton, and constant samples unchanged.

## Success metrics

- Focused statistical evidence tests pass.
- Changed-scope coverage remains at least 95%.
- The registered local probe preserves interval bounds and `sorted_calls_mean == 0.0`.
- Local repeated probe samples show lower `elapsed_ms_mean` and/or lower `peak_bytes_mean` versus the synced `origin/main` baseline.
- GitHub PR-scoped performance CI completes successfully before merge.
