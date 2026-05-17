# Video URI Identity Hash Single Encode Slice

## Scope

This slice keeps video URI preprocessing behavior unchanged while narrowing the
hot path in `worker.runtime.video_preprocessing._uri_identity_hash`.

## Registered Probe

The affected Python path is covered by the registered PR-scoped performance
probe `video-preprocessing-uri-byte-length-reuse` in
`infra/perf/pr_scoped_probes.json`. The registry includes focused
`test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/runtime/video_preprocessing.py`
- `services/mlx-worker-python/tests/test_video_preprocessing.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/video_preprocessing_uri_probe.py`

This slice also updates the probe and coverage commands for this entry to use
`python3` explicitly.

## Optimization Hypothesis

URI video preprocessing builds a stable identity hash for every URI input. The
current single-encode implementation still allocates a tuple and dispatches
through `str.join(...)` for each call. Rendering the same NUL-framed payload with
adjacent f-strings preserves the exact digest bytes while avoiding the per-call
tuple/join overhead in the hot path.

## Behavior Guard

A focused regression test pins the expected NUL-framed digest for a representative
URI payload, ensuring the single-encode implementation remains byte-compatible
with the previous framed hash contract.

## Verification Plan

Run the registered focused tests, changed-scope coverage, and registered probe
locally on Linux before opening the PR. The PR-scoped performance workflow must
select and complete the registered probe in CI before merge.

## Success Criteria

- Focused video preprocessing tests pass.
- Changed-scope coverage remains at or above 95%.
- Registered probe shows a clear local improvement in `elapsed_ms_mean` without
  increasing `byte_length_getattrs_per_call`.
- GitHub Actions and the PR-scoped performance workflow are green.
