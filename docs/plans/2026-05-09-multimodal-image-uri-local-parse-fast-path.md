# Multimodal Image URI Local Parse Fast Path

## Scope

This Python-only performance slice keeps behavior unchanged while reducing per-image overhead in `services/mlx-worker-python/worker/runtime/multimodal_preprocessing.py`.

## Registered Probe

The affected path is covered by the registered PR-scoped probe `multimodal-preprocessing-image-uri-single-parse` in `infra/perf/pr_scoped_probes.json`.

Focused commands:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_vision_runtime.py::test_prepare_vision_request_accepts_remote_http_inputs services/mlx-worker-python/tests/test_vision_runtime.py::test_prepare_vision_request_parses_each_image_uri_once services/mlx-worker-python/tests/test_vision_runtime.py::test_prepare_vision_request_parses_remote_image_uri_once services/mlx-worker-python/tests/test_vision_runtime.py::test_prepare_vision_request_rejects_missing_remote_and_unsupported_inputs services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_multimodal_preprocessing_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_multimodal_image_uri_parse_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_vision_runtime.py::test_prepare_vision_request_accepts_remote_http_inputs services/mlx-worker-python/tests/test_vision_runtime.py::test_prepare_vision_request_parses_each_image_uri_once services/mlx-worker-python/tests/test_vision_runtime.py::test_prepare_vision_request_parses_remote_image_uri_once services/mlx-worker-python/tests/test_vision_runtime.py::test_prepare_vision_request_rejects_missing_remote_and_unsupported_inputs services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_multimodal_preprocessing_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_multimodal_image_uri_parse_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/runtime/multimodal_preprocessing.py services/mlx-worker-python/tests/test_vision_runtime.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/multimodal_image_uri_parse_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/multimodal_image_uri_parse_probe.py
```

## Implementation Plan

- Avoid scanning for `/` when an image reference has no `:` and is therefore a plain local path.
- Reuse a module-level empty `ParseResult` for local image references rather than allocating an equivalent object for each local path.
- Store parsed image-reference records in a slotted dataclass to avoid per-reference instance dictionaries.
- Read local image references directly from the parsed `Path` in `_bytes_from_image_uri`, preserving the missing-file error while avoiding a separate `Path.exists()` stat on the valid hot path.
- Keep remote `http`/`https` parsing behavior unchanged, while allowing
  unescaped `file://` references to reuse the local-path fast path.

## Success Metrics

- Focused tests pass.
- Changed-scope coverage is at least 95%.
- Local registered probe reports lower `elapsed_ms_mean` with
  `urlparse_calls_mean == 0.0` for the synthetic mixed local-path/file-URI
  workload.
