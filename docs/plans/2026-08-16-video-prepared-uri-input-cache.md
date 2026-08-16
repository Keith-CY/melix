# Video prepared URI input cache

## Scope

This Python-only performance slice targets repeated URI-backed video preprocessing in `services/mlx-worker-python/worker/runtime/video_preprocessing.py`.

The hot path already reuses parsed URI references and URI identity hashes, but repeated calls with the same normalized URI metadata still rebuild the same immutable `PreparedVideoInput`. This slice adds a one-entry last prepared URI input cache keyed by the normalized URI, media metadata, byte length, and timing/frame bounds.

## Registered performance probe

The affected path is covered by the registered PR-scoped probe `video-preprocessing-uri-byte-length-reuse` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries and watches:

- `services/mlx-worker-python/worker/runtime/video_preprocessing.py`
- `services/mlx-worker-python/tests/test_video_preprocessing.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/video_preprocessing_uri_probe.py`

Primary metric: `elapsed_ms_mean` (lower is better). Guard metrics: `byte_length_getattrs_per_call` and `parse_calls_per_call` must not regress.

## Implementation plan

1. Preserve inline byte preprocessing behavior unchanged.
2. For URI inputs, normalize existing metadata fields and read `byte_length` once.
3. Return the cached `PreparedVideoInput` only when the full normalized URI cache key matches the last successful URI preparation.
4. Add a focused regression test proving repeated identical URI metadata reuses the prepared input and avoids another parser call.
5. Run the registered focused tests, changed-scope coverage command, and registered probe locally on Linux; use PR-scoped performance CI as the merge gate.

## Acceptance

- Focused video preprocessing tests pass.
- Changed-scope coverage for the touched Python/test/probe scope remains at or above 95%.
- Local and CI `video-preprocessing-uri-byte-length-reuse` probe reports lower `elapsed_ms_mean` without guard metric regressions.
