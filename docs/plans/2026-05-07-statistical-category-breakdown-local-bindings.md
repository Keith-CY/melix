# Statistical Evidence Category Breakdown Local Bindings

## Purpose

Keep the Phase 8 evaluation-compare category breakdown path behaviorally identical while reducing per-row aggregation overhead in `worker.productization.statistical_evidence.build_category_breakdown`.

## Scope

- Only touch the Python statistical-evidence category aggregation helper and its direct verification path.
- Preserve category label stripping, empty-label skipping, truthiness handling for correctness fields, sorted output keys, and rounded payload fields.
- Use the registered PR-scoped probe `statistical-evidence-category-breakdown-single-pass` as the performance gate.

## Verification Plan

- Focused tests for `services/mlx-worker-python/tests/test_statistical_evidence.py` and the registered PR-scoped performance selectors.
- Changed-scope coverage through the registered probe `coverage_command`.
- Registered local Linux probe command:
  `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/statistical_evidence_category_breakdown_probe.py`

## Acceptance Metric

Accept only if the registered category breakdown probe keeps the same checksum/sample counts and improves `elapsed_ms_mean` versus the origin/main baseline in repeated local samples.
