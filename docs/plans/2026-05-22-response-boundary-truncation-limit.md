# Response-Only Boundary Truncation Limit Binding

## Scope

This slice covers `services/mlx-worker-python/worker/model_ops/response_only_boundary.py` and the registered PR-scoped probe `response-only-boundary-slotted-records`.

## Optimization

`aggregate_response_only_boundaries()` has a hot truncation path when `max_seq_length` is positive. The path already computes response-only boundary aggregates in one pass. This slice keeps the same algorithm and replaces the temporary `effective_total` assignment with an in-place capped `total_tokens` local before subtracting the assistant offset.

The behavior is unchanged:

- `response_tokens` is still computed from the original total token count before truncation.
- trainable response tokens still clamp to `max_seq_length` and floor at zero.
- truncated and fully truncated sample counters keep the same semantics.

## Validation

Use the existing registered probe entry in `infra/perf/pr_scoped_probes.json`:

- focused response-only boundary tests from `test_command`
- changed-scope coverage from `coverage_command`
- `scripts/response_only_boundary_slots_probe.py` from `probe_command`

The Linux local probe validates this Python-only slice before PR creation; CI must also run the registered PR-scoped probe before merge.
