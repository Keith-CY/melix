# M4.9 Vision Integration Evidence

## Goal

Close the vision milestone with live integration evidence for multimodal ingress, OCR defaults, cache-aware vision execution, and tool-calling support.

## Scope

- productize repository-owned vision evidence into a machine-readable report builder
- add end-to-end coverage for local image, remote image, multi-image, OCR default stop, and VLM tool calls
- keep human-readable operator probes and machine-readable evidence discoverable from the runbook

## Files

- update `services/mlx-worker-python/worker/productization/acceptance_metrics.py`
- update `services/mlx-worker-python/worker/productization/__init__.py`
- update `services/mlx-worker-python/tests/test_acceptance_metrics.py`
- update `tests/integration/test_phase6_operator_workflows.py`
- update `docs/runbooks/phase-6-multimodal-ops.md`

## Implementation Notes

- reuse the existing Phase 6 stack and exported control-plane metrics instead of adding new runtime probes
- publish the vision evidence through `build_phase6_vision_metrics_report`, with stable `checks` and `metrics` sections
- keep the report keyed to repository-owned integration evidence rather than a one-off operator-only script
- preserve the existing `make phase6-metrics` text report for human inspection

## Verification

- `PYTHONPATH=.:services/mlx-worker-python uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_acceptance_metrics.py -q`
- `PYTHONPATH=.:services/mlx-worker-python uv run --project services/mlx-worker-python pytest tests/integration/test_phase6_operator_workflows.py -q`
- changed-line coverage for touched Python files
- `git diff --check`

## Acceptance

- the completed vision slice has repository-owned machine-readable evidence for ingress, OCR defaults, and VLM tool-calling
- operators can inspect Phase 6 latencies through `make phase6-metrics` and locate the matching machine-readable evidence path from the runbook

## Metrics Report

- Python verification: `services/mlx-worker-python/tests/test_acceptance_metrics.py` -> `10 passed`
- Python verification: `tests/integration/test_phase6_operator_workflows.py` -> `8 passed`
- Targeted machine-readable evidence path: `tests/integration/test_phase6_operator_workflows.py -k machine_readable` -> `1 passed`
- Python changed-line coverage: `98.53% (67/68)`
