# Statistical Evidence Bootstrap In-Place Sort

## Goal

Reduce temporary allocation in the paired bootstrap confidence interval path by sorting the already-owned replicate vector in place instead of allocating a second sorted list.

## Scope

- `services/mlx-worker-python/worker/productization/statistical_evidence.py`
- `services/mlx-worker-python/tests/test_statistical_evidence.py`

## Linux-only verification path

This is a Python-only optimization and can be verified on Linux with focused pytest, changed-scope coverage, and the existing registered PR-scoped performance probe.

## Performance probe

Registered probe: `statistical-evidence-bootstrap-single-sort`

The probe runs `scripts/statistical_evidence_bootstrap_probe.py` and reports:

- `elapsed_ms_mean`
- `peak_bytes_mean`
- `sorted_calls_mean`
- interval bound sanity metrics

## Success metrics

- Bootstrap interval payloads remain identical for the deterministic focused fixture.
- Focused tests pass.
- Changed executable line coverage is at least 95%.
- Local registered probe reduces `sorted_calls_mean` from `1.0` to `0.0` while preserving lower/upper bound ordering.
