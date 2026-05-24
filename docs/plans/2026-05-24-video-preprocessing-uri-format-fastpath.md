# Video preprocessing URI format fast path

## Scope

This Python-only performance slice is limited to URI-backed video preprocessing in `services/mlx-worker-python/worker/runtime/video_preprocessing.py`.

## Registered probe

The affected path is already covered by the registered PR-scoped performance probe `video-preprocessing-uri-byte-length-reuse` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` fields and watches:

- `services/mlx-worker-python/worker/runtime/video_preprocessing.py`
- `services/mlx-worker-python/tests/test_video_preprocessing.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/video_preprocessing_uri_probe.py`

## Optimization plan

For URI video inputs with no explicit `format`, `mime_type`, or `filename`, reuse the already parsed URI suffix directly when it is one of the supported video formats. This keeps validation and output behavior unchanged while avoiding an extra `_resolve_video_format` call and varargs tuple construction in the hot path exercised by the registered probe.

## Verification

Run the registered focused test command, changed-scope coverage command, and local registered probe on Linux. GitHub Actions PR-scoped performance remains the merge gate for base-vs-head validation.
