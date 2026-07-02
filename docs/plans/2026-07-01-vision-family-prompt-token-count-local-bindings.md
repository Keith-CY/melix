# Vision Family Prompt Token Count Local Bindings

## Scope

This Python-only performance slice is limited to `ResolvedVisionFamilyConfig.prompt_token_count()` in `services/mlx-worker-python/worker/runtime/vision_family_adapters.py`.

The slice keeps behavior unchanged while reducing repeated hot-path attribute lookups by binding the prepared request media collections once before the image and video token scans.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe `vision-family-prompt-token-count-scan` in `infra/perf/pr_scoped_probes.json`.

The probe includes:

- `test_command` for focused vision-family token-count behavior and probe-registry tests.
- `coverage_command` for changed-scope coverage of the adapter, shared token counting helper, tests, and probe script.
- `probe_command` via `scripts/vision_family_prompt_token_count_probe.py`.

## Verification

Run before PR:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_vision_runtime.py::test_vision_family_prompt_token_count_matches_split_without_materializing_tokens services/mlx-worker-python/tests/test_vision_runtime.py::test_vision_family_prompt_token_count_reuses_cached_prompt_scan services/mlx-worker-python/tests/test_vision_runtime.py::test_vision_family_prompt_token_count_reuses_same_media_request_cache services/mlx-worker-python/tests/test_vision_runtime.py::test_vision_family_prompt_token_count_clamps_media_minimums services/mlx-worker-python/tests/test_vision_runtime.py::test_resolved_vision_family_config_uses_slots_for_hot_path_instances services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_vision_family_prompt_token_count_probe_script_emits_metrics services/mlx-worker-python/tests/test_vision_runtime.py::test_prepare_vision_request_rejects_http_and_private_remote_image_inputs services/mlx-worker-python/tests/test_vision_runtime.py::test_bytes_from_local_image_uri_reuses_single_parsed_uri services/mlx-worker-python/tests/test_vision_runtime.py::test_prepare_vision_request_parses_each_image_uri_once
```

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_vision_runtime.py::test_vision_family_prompt_token_count_matches_split_without_materializing_tokens services/mlx-worker-python/tests/test_vision_runtime.py::test_vision_family_prompt_token_count_reuses_cached_prompt_scan services/mlx-worker-python/tests/test_vision_runtime.py::test_vision_family_prompt_token_count_reuses_same_media_request_cache services/mlx-worker-python/tests/test_vision_runtime.py::test_vision_family_prompt_token_count_clamps_media_minimums services/mlx-worker-python/tests/test_vision_runtime.py::test_resolved_vision_family_config_uses_slots_for_hot_path_instances services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_vision_family_prompt_token_count_probe_script_emits_metrics services/mlx-worker-python/tests/test_vision_runtime.py::test_prepare_vision_request_rejects_http_and_private_remote_image_inputs services/mlx-worker-python/tests/test_vision_runtime.py::test_bytes_from_local_image_uri_reuses_single_parsed_uri services/mlx-worker-python/tests/test_vision_runtime.py::test_prepare_vision_request_parses_each_image_uri_once && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/runtime/vision_family_adapters.py services/mlx-worker-python/worker/runtime/token_counting.py services/mlx-worker-python/tests/test_vision_runtime.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/vision_family_prompt_token_count_probe.py
```

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/vision_family_prompt_token_count_probe.py
```

## Success criteria

- Focused tests pass.
- Changed-scope coverage is at least 95%.
- Registered probe remains neutral or improves for `elapsed_ms_mean` without increasing split calls.
