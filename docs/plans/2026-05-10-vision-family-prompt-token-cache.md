# Vision family prompt token cache

## Scope

This Python-only performance slice targets repeated prompt token accounting in
`services/mlx-worker-python/worker/runtime/vision_family_adapters.py`.

The current prompt token counter intentionally avoids `prompt_text.split()` list
materialization. This slice keeps that behavior and adds a bounded cache for the
pure whitespace token-count helper so repeated VLM prompt accounting for the same
prompt text can avoid rescanning the prompt string.

## Registered probe

Use the existing PR-scoped registered probe
`vision-family-prompt-token-count-scan` in `infra/perf/pr_scoped_probes.json`.
It covers the runtime path, focused behavior tests, changed-scope coverage, and
`scripts/vision_family_prompt_token_count_probe.py`.

## Success metrics

- Behavior parity: prompt token counts continue to match `split()` semantics
  without calling the prompt object's `split()` method.
- Cache behavior: repeated calls for the same prompt produce one cache miss and
  at least one cache hit.
- Probe direction: `elapsed_ms_mean` and/or `peak_bytes_mean` should improve or
  remain within the registered threshold while `split_calls_mean` remains `0.0`.

## Local verification

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_vision_runtime.py::test_vision_family_prompt_token_count_matches_split_without_materializing_tokens services/mlx-worker-python/tests/test_vision_runtime.py::test_vision_family_prompt_token_count_reuses_cached_prompt_scan services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_vision_family_prompt_token_count_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_vision_runtime.py::test_vision_family_prompt_token_count_matches_split_without_materializing_tokens services/mlx-worker-python/tests/test_vision_runtime.py::test_vision_family_prompt_token_count_reuses_cached_prompt_scan services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_vision_family_prompt_token_count_probe_script_emits_metrics && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/runtime/vision_family_adapters.py services/mlx-worker-python/tests/test_vision_runtime.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/vision_family_prompt_token_count_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/vision_family_prompt_token_count_probe.py
```
