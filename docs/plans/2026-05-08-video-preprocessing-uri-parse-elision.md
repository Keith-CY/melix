# Video preprocessing URI parse elision

## Goal

Reduce redundant parsing and decoding work in `prepare_video_input(...)` for URI-backed video inputs when the media metadata does not provide an explicit filename and the URI path contains no percent-encoded bytes.

## Scope

- `services/mlx-worker-python/worker/runtime/video_preprocessing.py`
- `services/mlx-worker-python/tests/test_video_preprocessing.py`
- `scripts/video_preprocessing_uri_probe.py`
- `infra/perf/pr_scoped_probes.json`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`

## Linux-only constraint

This is a Python worker slice and can be verified on Linux with focused pytest, changed-scope coverage, and the registered PR-scoped performance probe.

## Performance probe

Use the existing registered probe `video-preprocessing-uri-byte-length-reuse` and extend its script metrics with `parse_calls_per_call`.

Success metrics:

- Preserve existing `byte_length_getattrs_per_call == 1.0`.
- Keep URI parse calls at one per call for a remote URI without explicit filename.
- Avoid calling `unquote(...)` for URI paths that do not contain percent-encoded bytes.
- Keep behavior identical for inferred format, filename, byte length, and identity hash.

## Verification commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_video_preprocessing.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_video_preprocessing_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_video_preprocessing_uri_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_video_preprocessing.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_video_preprocessing_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_video_preprocessing_uri_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/runtime/video_preprocessing.py services/mlx-worker-python/tests/test_video_preprocessing.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/video_preprocessing_uri_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/video_preprocessing_uri_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/pr_scoped_performance_run.py --registry infra/perf/pr_scoped_probes.json --probe-id video-preprocessing-uri-byte-length-reuse --base-repo <baseline-worktree> --head-repo "$PWD" --output /tmp/video-preprocessing-uri-probe.json
```
