# Video URI identity hash positional cache key

## Scope

This Python-only performance slice is limited to the URI branch of
`prepare_video_input(...)` in
`services/mlx-worker-python/worker/runtime/video_preprocessing.py`.
The hot path prepares repeated remote video references and derives a stable
identity hash from the URI, resolved format, filename, byte length, and temporal
bounds.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe
`video-preprocessing-uri-byte-length-reuse` in
`infra/perf/pr_scoped_probes.json`. The registry entry includes focused
`test_command`, `coverage_command`, and `probe_command` entries and watches the
video preprocessing source, focused tests, probe selection tests, and
`scripts/video_preprocessing_uri_probe.py`.

## Change

The slice keeps identity-hash behavior unchanged while calling the cached
`_uri_identity_hash(...)` helper with positional arguments instead of keyword
arguments. The helper signature now accepts the same fields positionally, which
avoids repeated keyword call/key construction overhead in the remote-video
preprocessing loop without changing the framed payload or SHA-256 digest.

## Verification plan

1. Run the registered focused test command for
   `video-preprocessing-uri-byte-length-reuse`.
2. Run the registered changed-scope coverage command and require at least 95%
   measured coverage for the touched scope.
3. Run the registered probe locally on Linux and compare against the baseline
   from `origin/main`; primary metric is `elapsed_ms_mean` (lower is better),
   while `byte_length_getattrs_per_call` and `parse_calls_per_call` must remain
   unchanged.

## Validation boundary

This is a Python-only slice and is locally verifiable on Linux. No Swift runtime
behavior changes are included.
