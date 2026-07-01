# Model load trust non-empty leading-character fast path

## Scope

This Python-only performance slice is limited to the model-load trust policy
source fallback helper in `services/mlx-worker-python/worker/model_load_trust.py`.
It preserves existing behavior for empty, whitespace-only, leading-whitespace,
and common non-empty policy source values.

The affected path is covered by the registered PR-scoped probe
`model-load-config-json-bytes` in `infra/perf/pr_scoped_probes.json`. The entry
already provides focused `test_command`, `coverage_command`, and `probe_command`
values and selects this probe when `worker/model_load_trust.py` or its tests
change.

## Plan

1. Add a focused regression guard for a leading-whitespace but non-empty policy
   source so the helper's fallback behavior remains unchanged.
2. Avoid whole-string whitespace scanning for the common non-empty policy source
   path by checking the leading character first, falling back to `isspace()` only
   when the source begins with whitespace.
3. Run the registered focused test command, changed-scope coverage command, and
   registered probe locally on Linux before opening the PR.

## Metrics

- Baseline registered probe before change on Linux:
  `elapsed_ms_mean=6.020329135935754`, `elapsed_ms_min=5.959293979685754`,
  `peak_bytes_mean=3251.5714285714284`, `rejections_mean=300.0`.
- Candidate registered probe after change on Linux (3 runs):
  `elapsed_ms_mean` values `6.383530138659158`, `5.759119446988085`,
  `5.7851652964018285`; mean `5.975938294016356` ms. Delta vs baseline:
  `-0.04439084191939724` ms (`~0.7373%` lower). `rejections_mean` remained
  `300.0` for all runs and `peak_bytes_mean` remained `3251.5714285714284`.
- Acceptance target: lower or neutral `elapsed_ms_mean` with unchanged rejection
  count under the registered probe.
