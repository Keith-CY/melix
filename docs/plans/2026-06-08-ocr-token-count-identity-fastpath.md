# Deterministic OCR token-count identity fast path

This Python-only performance slice is limited to the deterministic OCR runtime's repeated prompt-token accounting path in `services/mlx-worker-python/worker/runtime/deterministic_ocr_runtime.py`.

## Scope

Registered PR-scoped probe: `deterministic-ocr-token-count-scan` in `infra/perf/pr_scoped_probes.json`.

The affected registry entry already provides focused `test_command`, `coverage_command`, and `probe_command` entries covering the OCR runtime, shared whitespace token counter, probe selector tests, and `scripts/deterministic_ocr_token_count_probe.py`.

## Optimization

Repeated OCR accounting often asks for the token count of the same prepared single-image request that was just counted. The runtime already caches that identity, but the hot hit still read the request media lists and checked the single-image shape before returning the cached value.

This slice moves the same-request identity check to the beginning of `prompt_token_count()` so the repeated hot hit returns the cached count without re-reading the request media containers. Misses still follow the existing single-image and fallback semantics.

## Verification plan

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_vision_runtime.py::test_generate_streams_ocr_text_from_inline_image_bytes services/mlx-worker-python/tests/test_vision_runtime.py::test_ocr_token_count_scans_whitespace_without_split_list services/mlx-worker-python/tests/test_vision_runtime.py::test_ocr_single_image_token_count_reuses_precomputed_input_bytes services/mlx-worker-python/tests/test_vision_runtime.py::test_ocr_single_image_token_count_reuses_same_request_cache services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_deterministic_ocr_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_deterministic_ocr_token_count_probe_script_emits_metrics services/mlx-worker-python/tests/test_vision_runtime.py::test_prepare_vision_request_rejects_http_and_private_remote_image_inputs services/mlx-worker-python/tests/test_vision_runtime.py::test_bytes_from_local_image_uri_reuses_single_parsed_uri services/mlx-worker-python/tests/test_vision_runtime.py::test_prepare_vision_request_parses_each_image_uri_once
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_vision_runtime.py::test_generate_streams_ocr_text_from_inline_image_bytes services/mlx-worker-python/tests/test_vision_runtime.py::test_ocr_token_count_scans_whitespace_without_split_list services/mlx-worker-python/tests/test_vision_runtime.py::test_ocr_single_image_token_count_reuses_precomputed_input_bytes services/mlx-worker-python/tests/test_vision_runtime.py::test_ocr_single_image_token_count_reuses_same_request_cache services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_deterministic_ocr_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_deterministic_ocr_token_count_probe_script_emits_metrics services/mlx-worker-python/tests/test_vision_runtime.py::test_prepare_vision_request_rejects_http_and_private_remote_image_inputs services/mlx-worker-python/tests/test_vision_runtime.py::test_bytes_from_local_image_uri_reuses_single_parsed_uri services/mlx-worker-python/tests/test_vision_runtime.py::test_prepare_vision_request_parses_each_image_uri_once && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/runtime/deterministic_ocr_runtime.py services/mlx-worker-python/worker/runtime/token_counting.py services/mlx-worker-python/tests/test_vision_runtime.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/deterministic_ocr_token_count_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/deterministic_ocr_token_count_probe.py
```

## Success criteria

- Focused OCR tests pass locally on Linux.
- Changed-scope coverage remains at least 95% for the touched OCR/runtime scope.
- Registered probe reports a lower `elapsed_ms_mean` than the `origin/main` baseline on the same Linux worktree.
- CI PR-scoped performance report completes successfully before merge.
