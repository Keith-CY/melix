# Response-only Boundary Record Init Slice

## Scope

This Python-only performance slice is limited to `ResponseOnlyBoundary` construction in `services/mlx-worker-python/worker/model_ops/response_only_boundary.py`.

The record is created once per response-only dataset sample before aggregate manifest statistics are computed. The previous implementation used a frozen slotted dataclass with a custom `object.__setattr__` initializer. This slice keeps the record slotted and dictionary-free while using direct slot assignment to reduce per-record construction overhead.

## Registered probe

The affected path is covered by the registered PR-scoped probe `response-only-boundary-slotted-records` in `infra/perf/pr_scoped_probes.json`.

The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` values for:

- `services/mlx-worker-python/tests/test_response_only_boundary.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/response_only_boundary_slots_probe.py`

## Implementation plan

1. Preserve the public fields and slotted/no-`__dict__` memory shape of `ResponseOnlyBoundary`.
2. Replace frozen-slot initialization with direct slot assignment for faster sample-record construction.
3. Verify focused response-only tests, changed-scope coverage, and the registered probe locally on Linux.
4. Use PR-scoped performance CI as the merge gate.

## Metrics

Success is measured by lower `construction_elapsed_ms_mean` from `scripts/response_only_boundary_slots_probe.py`; `aggregation_elapsed_ms_mean`, `peak_bytes_mean`, and `instance_dict_count_mean` remain guardrails. This is Python-only and locally verifiable on Linux. No Swift runtime effect is claimed.
