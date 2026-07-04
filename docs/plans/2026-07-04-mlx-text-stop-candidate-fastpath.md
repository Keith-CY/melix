# MLX text stop filter no-pending candidate fast path

## Summary

Avoid rebuilding the stop-filter candidate string when no stop-sequence prefix is
pending. The common streaming path forwards token events that do not overlap a
configured stop sequence, so the filter can pass the event text object directly
into the stop-sequence scan and only concatenate when a previous chunk left a
pending viable stop prefix.

## Probe coverage

The affected path is covered by the registered PR-scoped probe
`mlx-text-stop-filter-prefix-cache` in `infra/perf/pr_scoped_probes.json`. The
entry has focused `test_command`, `coverage_command`, and `probe_command`
coverage for `services/mlx-worker-python/worker/runtime/mlx_text_runtime.py`,
`services/mlx-worker-python/tests/test_mlx_backend.py`, and
`scripts/mlx_text_stop_filter_probe.py`.

## Implementation plan

1. Add a focused regression assertion that the stop-filter scanner receives the
   existing token text object when no prefix is pending.
2. Change `_apply_stop_sequences(...)` to reuse `event.text` for the no-pending
   candidate path and keep the existing concatenation path when pending text is
   present.
3. Run the registered focused tests, changed-scope coverage command, and the
   registered base-vs-head PR-scoped probe locally on Linux.

## Validation boundary

This is a Python-only slice and is locally verifiable on Linux. No Swift runtime
effect is claimed.
