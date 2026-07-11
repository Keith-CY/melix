# Video Preprocessing URI Constant Membership Fast Path

## Scope

This Python-only performance slice keeps video URI preprocessing behavior equivalent while hoisting repeated membership literals from the URI parsing and validation hot path into module-level constants.

## Registered Probe

The affected path is covered by the registered PR-scoped probe `video-preprocessing-uri-byte-length-reuse` in `infra/perf/pr_scoped_probes.json`.

The existing probe already provides focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/runtime/video_preprocessing.py`
- `services/mlx-worker-python/tests/test_video_preprocessing.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/video_preprocessing_uri_probe.py`

## Expected Behavior

- Remote HTTPS video URI validation remains unchanged.
- Local/file URI validation remains unchanged.
- Parsed video reference handling still preserves decoded path name and suffix behavior.
- Byte-length and parse-call counts stay at the registered probe baseline of one call per preprocessing request.

## Verification Plan

Run the registered focused video preprocessing tests, changed-scope coverage, and the registered probe locally on Linux before pushing. GitHub Actions PR-scoped performance remains the merge gate after PR creation.
