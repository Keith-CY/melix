# MLX-VLM family-config cache optimization

## Goal

Reduce repeated `resolve_vision_family_config(...)` work in the MLX-VLM runtime hot path by caching the resolved family config on the loaded-model payload, while preserving request shaping, prompt token counting, and capability metadata semantics.

## Scope

This slice is limited to:

- `services/mlx-worker-python/worker/runtime/mlx_vlm_runtime.py`
- `services/mlx-worker-python/tests/test_mlx_vlm_runtime.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/mlx_vlm_family_config_probe.py`
- `infra/perf/pr_scoped_probes.json`

## Linux constraint

This is a Python-only optimization slice. Verification must stay Linux-local via focused pytest, changed-scope coverage, and a PR-scoped performance probe that compares `origin/main` to the branch implementation.

## Performance probe

Register a dedicated PR-scoped performance probe for the MLX-VLM family-config path that:

- exercises repeated `render_prompt(...)` plus `prompt_token_count(...)` calls on one loaded-model payload
- measures `elapsed_ms_mean`
- measures `resolve_calls_mean`
- preserves explicit correctness signals such as `prompt_token_count`, `iteration_count`, and `sample_count`

## Implementation plan

1. Cache the resolved family config on the loaded-model payload during `load_model(...)`.
2. Make `MLXVLMRuntime._family_config(...)` reuse that cached object and lazily populate it for compatibility when older/manual loaded-model payloads do not already contain the cache entry.
3. Add focused regression tests that prove repeated prompt rendering and prompt token counting reuse the cached config instead of re-resolving it.
4. Register the dedicated `command_json` PR-scoped probe and add focused probe-registry tests.
5. Validate with focused pytest, changed-scope coverage >=95%, `git diff --check`, and a local `origin/main` vs head probe run.

## Success criteria

- `load_model(...)`, `render_prompt(...)`, and `prompt_token_count(...)` preserve existing shaping and token-count semantics.
- Loaded-model payloads reuse one cached family config across repeated calls.
- Compatibility behavior still works when `_family_config(...)` receives an older/manual payload without the cache entry.
- Changed-scope coverage for the touched executable Python files remains at least 95%.
- The dedicated probe shows lower `elapsed_ms_mean` and lower `resolve_calls_mean` than `origin/main` for the same synthetic workload.
