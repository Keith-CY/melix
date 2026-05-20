# Response-only boundary slotted records

## Scope

This Python-only performance slice targets the response-only boundary records used
by LoRA dataset preparation and trainer manifest aggregation:

- `services/mlx-worker-python/worker/model_ops/response_only_boundary.py`
- `services/mlx-worker-python/tests/test_response_only_boundary.py`
- `scripts/response_only_boundary_slots_probe.py`
- `infra/perf/pr_scoped_probes.json`

The original slice kept response-only masking semantics unchanged while removing
per-instance `__dict__` allocation from the immutable boundary and aggregate
records by using slotted dataclasses. The 2026-05-20 follow-up keeps the same
registered probe and inlines response-token and truncation arithmetic inside the
single-pass aggregate loop to avoid repeated property/method dispatch per
boundary record.

## Registered probe

Registered probe: `response-only-boundary-slotted-records`.

The probe constructs a synthetic 50k-boundary workload and aggregates it with the
same public helper used by LoRA manifest metric collection. It reports:

- `construction_elapsed_ms_mean`
- `aggregation_elapsed_ms_mean`
- `peak_bytes_mean`
- `instance_dict_count_mean`

The focused test and coverage commands in `infra/perf/pr_scoped_probes.json`
exercise the non-tokenizer aggregate path, the slotted-record regression test,
probe selection, probe JSON execution, and registry validation.

## Verification plan

1. Run the focused registered pytest command locally on Linux.
2. Run the registered changed-scope coverage command locally on Linux.
3. Run the registered probe locally on `origin/main` and the head branch to
   compare construction, aggregation, peak memory, and instance dict metrics.
4. Use GitHub Actions PR-scoped performance as the merge gate.

## Acceptance criteria

- `ResponseOnlyBoundary` and `ResponseOnlyBoundaryAggregate` do not expose an
  instance `__dict__`.
- Existing response-only aggregate behavior remains unchanged.
- Local probe shows lower or equal object-allocation structural cost
  (`instance_dict_count_mean == 0.0` on head) and no functional checksum drift.
- PR-scoped performance CI completes the registered probe successfully.
