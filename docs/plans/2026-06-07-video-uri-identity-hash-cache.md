# Video URI Identity Hash Cache Performance Slice

## Scope

This slice keeps video URI preprocessing behavior unchanged while reducing repeated
identity digest work for identical URI metadata frames. The affected path is
`services/mlx-worker-python/worker/runtime/video_preprocessing.py`.

## Registered Probe

The path is covered by the registered PR-scoped probe
`video-preprocessing-uri-byte-length-reuse` in `infra/perf/pr_scoped_probes.json`.
The probe includes focused `test_command`, `coverage_command`, and
`probe_command` entries and measures URI preprocessing elapsed time plus metadata
access counters.

## Change

Cache `_uri_identity_hash(...)` with the same bounded cache size used for parsed
video references. The hash input is fully represented by immutable string and
integer metadata arguments, so repeated calls for the same URI frame can reuse the
same digest without changing the NUL-framed digest contract.

## Verification

Run the registered focused tests, changed-scope coverage command, and registered
probe locally on Linux before PR creation. CI must run the same registered
PR-scoped performance probe before merge.
