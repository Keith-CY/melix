# Video preprocessing URI parse cache slice

This Python-only performance slice targets repeated URI video preprocessing in `services/mlx-worker-python/worker/runtime/video_preprocessing.py`.

## Scope

Cache `_parse_video_reference()` results for repeated URI/path strings with a bounded `lru_cache`. The `ParsedVideoReference` result is immutable (`slots=True`, `frozen=True`), so repeated preprocessing of the same URI can reuse decoded path/name/suffix metadata without changing validation, format inference, filename fallback, byte-length accounting, or identity-hash payloads.

## Registered probe coverage

The affected path is covered by the existing PR-scoped registered probe `video-preprocessing-uri-byte-length-reuse` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/runtime/video_preprocessing.py`
- `services/mlx-worker-python/tests/test_video_preprocessing.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/video_preprocessing_uri_probe.py`

## Verification plan

1. Run the focused registered test command for `video-preprocessing-uri-byte-length-reuse`.
2. Run the registered changed-scope coverage command and require at least 95% measured scope coverage.
3. Run the registered local Linux probe before and after the implementation.
4. Push the branch only if the probe direction is favorable or the delta is clearly neutral with explainable measurement noise.
5. Treat hosted PR-scoped performance CI as the merge gate.

## Metrics

Primary metric: `elapsed_ms_mean` from `video-preprocessing-uri-byte-length-reuse` (lower is better). Secondary guard metrics: `byte_length_getattrs_per_call` and `parse_calls_per_call` must not regress; parse-call instrumentation wraps the parser function and may remain at one wrapper call per preprocessing call even when the internal parser result is served from the cache.
