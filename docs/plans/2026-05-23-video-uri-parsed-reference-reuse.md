# Video URI Parsed Reference Reuse Slice

## Scope

This slice keeps Python video URI preprocessing behavior unchanged while trimming
per-call overhead in `worker.runtime.video_preprocessing.prepare_video_input` for
URI-backed video inputs.

## Registered Probe

The affected Python path is covered by the registered PR-scoped performance probe
`video-preprocessing-uri-byte-length-reuse` in
`infra/perf/pr_scoped_probes.json`. The registry includes focused
`test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/runtime/video_preprocessing.py`
- `services/mlx-worker-python/tests/test_video_preprocessing.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/video_preprocessing_uri_probe.py`

## Optimization Hypothesis

`prepare_video_input(...)` already parses each URI once into
`ParsedVideoReference`. The hot path still allocates a temporary candidate tuple
for format inference and then calls `_filename_from_reference(...)`, which must
perform a type dispatch even when the parsed reference already carries the path
name. Branching on whether an explicit filename exists lets the URI path pass the
parsed reference directly to format resolution and reuse `parsed_reference.path_name`
for the fallback filename.

## Behavior Guard

The existing parsed-URI reuse test now also monkeypatches
`_filename_from_reference(...)` to fail, proving the URI path consumes the parsed
reference metadata directly while preserving format and filename behavior.

## Verification Plan

Run the registered focused tests, changed-scope coverage, and registered probe
locally on Linux before opening the PR. The PR-scoped performance workflow must
select and complete the registered probe in CI before merge.

## Success Criteria

- Focused video preprocessing tests pass.
- Changed-scope coverage remains at or above 95%.
- Registered probe shows a clear local improvement in `elapsed_ms_mean` without
  increasing `byte_length_getattrs_per_call` or `parse_calls_per_call`.
- GitHub Actions and the PR-scoped performance workflow are green.
