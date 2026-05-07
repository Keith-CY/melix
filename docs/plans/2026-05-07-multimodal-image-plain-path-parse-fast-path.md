# Multimodal Image Plain-Path Parse Fast Path

## Scope

This performance slice is limited to local plain-path image URI handling in
`services/mlx-worker-python/worker/runtime/multimodal_preprocessing.py`.
The path is covered by the registered PR-scoped probe
`multimodal-preprocessing-image-uri-single-parse` in
`infra/perf/pr_scoped_probes.json`.

## Change

Plain local image references that contain no URI scheme marker are treated as
filesystem paths without routing through `urllib.parse.urlparse`. URI forms that
need parsing, including `file://`, `http://`, `https://`, and unsupported
scheme-bearing values such as `ftp://`, still use the URI parser so existing
error semantics remain unchanged.

The affected probe command is also kept runnable with `python3` for this slice.

## Probe and Metrics

Use the registered probe:

```text
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/multimodal_image_uri_parse_probe.py
```

The probe builds a mixed set of 640 image references, alternating plain local
paths and `file://` URI references, and reports:

- `elapsed_ms_mean`
- `peak_bytes_mean`
- `urlparse_calls_mean`
- `prepared_image_count`
- `sample_count`

Expected effect: the plain-path half should skip `urlparse`, lowering
`urlparse_calls_mean` from 640 to 320 and reducing elapsed preprocessing time on
Linux.

## Verification Plan

```text
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_vision_runtime.py::test_prepare_vision_request_parses_each_image_uri_once services/mlx-worker-python/tests/test_vision_runtime.py::test_prepare_vision_request_parses_remote_image_uri_once services/mlx-worker-python/tests/test_vision_runtime.py::test_prepare_vision_request_rejects_missing_remote_and_unsupported_inputs services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_multimodal_image_uri_parse_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_vision_runtime.py::test_prepare_vision_request_parses_each_image_uri_once services/mlx-worker-python/tests/test_vision_runtime.py::test_prepare_vision_request_parses_remote_image_uri_once services/mlx-worker-python/tests/test_vision_runtime.py::test_prepare_vision_request_rejects_missing_remote_and_unsupported_inputs services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_multimodal_image_uri_parse_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/runtime/multimodal_preprocessing.py services/mlx-worker-python/tests/test_vision_runtime.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/multimodal_image_uri_parse_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/multimodal_image_uri_parse_probe.py
git diff --check
```
