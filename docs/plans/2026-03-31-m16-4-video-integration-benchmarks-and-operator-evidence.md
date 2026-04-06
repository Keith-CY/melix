# M16.4 Video Integration Benchmarks And Operator Evidence

## Status

Completed on 2026-04-06. The repository now owns a live-path video smoke workflow that exercises
local-path, remote-URL, bounded multi-frame, and routing-under-load scenarios, emits one
machine-readable video operator-evidence report, and documents reproduction plus diagnosis in a
dedicated runbook.

## Goal

Leave video understanding with reproducible integration evidence, operator runbooks, and measurable benchmark data rather than only contract-level support.

## Scope

- add live integration coverage for representative video requests
- record preprocessing, routing, and latency metrics
- document operator workflows and recovery paths

## Files

- update `tests/integration/`
- update `docs/runbooks/`
- update `docs/README.md`

## Implementation Notes

- Benchmarks should cover at least one short local video, one remote video path, and one bounded multi-frame workload.
- Operator evidence should include cleanup inspection and background-lane diagnosis.

## Verification

- `make swift-test`
- `make py-test`
- `make integration-test`
- `PYTHONPATH='.:services/mlx-worker-python' uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_acceptance_metrics.py tests/integration/test_video_runtime_smoke.py -q`
- `PYTHONPATH='.:services/mlx-worker-python' uv run --project services/mlx-worker-python coverage run --data-file=/tmp/m16_4_python.coverage -m pytest services/mlx-worker-python/tests/test_acceptance_metrics.py tests/integration/test_video_runtime_smoke.py -q`
- `python3 scripts/python_changed_line_coverage.py --coverage-json /tmp/m16_4_python_coverage.json services/mlx-worker-python/worker/productization/acceptance_metrics.py services/mlx-worker-python/worker/productization/__init__.py scripts/m16_video_runtime_smoke.py services/mlx-worker-python/tests/test_acceptance_metrics.py tests/integration/test_video_runtime_smoke.py`

## Acceptance

- Video integration coverage is live-path and reproducible.
- Runbooks and metrics reports capture real operator-relevant evidence for video workloads.
