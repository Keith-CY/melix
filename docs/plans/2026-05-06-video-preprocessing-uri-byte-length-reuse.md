# Video Preprocessing URI Byte-Length Reuse

## Goal

Reduce redundant work in the Python video URI preprocessing hot path by reading `media.byte_length` once per URI input and reusing that value for both the prepared metadata payload and URI identity hash construction.

## Scope

Touched files:

- `services/mlx-worker-python/worker/runtime/video_preprocessing.py`
- `services/mlx-worker-python/tests/test_video_preprocessing.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/video_preprocessing_uri_probe.py`
- `infra/perf/pr_scoped_probes.json`

## Linux-only Verification Path

This is a Python-only optimization and can be verified on Linux with focused pytest, changed-scope coverage, and a local performance probe.

## Performance Probe

Register `video-preprocessing-uri-byte-length-reuse` in the PR-scoped performance registry. The probe repeatedly calls `prepare_video_input(...)` for URI-backed video input using a counting media stub.

Primary success metric:

- `byte_length_getattrs_per_call` drops from `2.0` on `origin/main` to `1.0` on the branch.

Secondary metric:

- `elapsed_ms_mean` should not regress beyond the probe warning threshold.

## Success Criteria

- Focused video preprocessing tests pass.
- PR-scoped performance registry tests for the new probe pass.
- Changed executable coverage for touched Python/test/probe files is at least 95%.
- Local probe emits concrete metrics showing one `byte_length` read per URI preprocessing call.
- `git diff --check` passes.
