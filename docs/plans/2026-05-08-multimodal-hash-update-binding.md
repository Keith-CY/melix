# Multimodal Hash Update Binding

## Scope

This performance slice is limited to the Python multimodal preprocessing request
hash builder in `services/mlx-worker-python/worker/runtime/multimodal_preprocessing.py`.
The affected path is covered by the registered PR-scoped probe
`multimodal-preprocessing-image-uri-single-parse` in
`infra/perf/pr_scoped_probes.json`, which has focused `test_command`,
`coverage_command`, and `probe_command` entries.

## Change

`_vision_request_hash(...)` binds `hashlib.sha256().update` once for the prompt
and prepared image hash loop. This keeps the digest inputs and hash semantics
unchanged while avoiding repeated bound-method lookups in multi-image vision
requests. The video branch is intentionally left unchanged in this slice so the
Linux coverage gate remains focused on the exercised image path.

## Verification Plan

```text
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_vision_runtime.py::test_prepare_vision_request_hash_changes_when_prompt_or_image_changes services/mlx-worker-python/tests/test_vision_runtime.py::test_prepare_vision_request_preserves_multi_image_order_in_payload_and_hash services/mlx-worker-python/tests/test_vision_runtime.py::test_prepare_vision_request_parses_each_image_uri_once services/mlx-worker-python/tests/test_vision_runtime.py::test_prepare_vision_request_parses_remote_image_uri_once services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_multimodal_image_uri_parse_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_vision_runtime.py::test_prepare_vision_request_hash_changes_when_prompt_or_image_changes services/mlx-worker-python/tests/test_vision_runtime.py::test_prepare_vision_request_preserves_multi_image_order_in_payload_and_hash services/mlx-worker-python/tests/test_vision_runtime.py::test_prepare_vision_request_parses_each_image_uri_once services/mlx-worker-python/tests/test_vision_runtime.py::test_prepare_vision_request_parses_remote_image_uri_once services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_multimodal_image_uri_parse_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/runtime/multimodal_preprocessing.py services/mlx-worker-python/tests/test_vision_runtime.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/multimodal_image_uri_parse_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/multimodal_image_uri_parse_probe.py
```

## Probe and Metrics

The registered probe prepares 640 image references and reports
`elapsed_ms_mean`, `peak_bytes_mean`, `urlparse_calls_mean`,
`prepared_image_count`, and `sample_count`.

Initial Linux comparison on this worktree:

- Baseline probe runs: 116.527 ms, 72.596 ms, 70.187 ms (`old_mean=86.436 ms`,
  noisy first run included)
- Candidate probe runs: 62.457 ms, 75.519 ms, 63.889 ms (`new_mean=67.288 ms`)
- `urlparse_calls_mean` remained 320.0 and `peak_bytes_mean` remained 358250.0.

The PR-scoped performance CI report remains the merge gate for the registered
probe comparison.
