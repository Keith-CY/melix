# Vision Family Prompt Token Count Branch Elision

## Scope

This performance slice is limited to `ResolvedVisionFamilyConfig.prompt_token_count`
in `services/mlx-worker-python/worker/runtime/vision_family_adapters.py`.

The optimization preserves token accounting semantics while replacing per-item
conditional-expression accumulation and final `max()` clamping with explicit
branch normalization. This keeps the divisor/cost safety clamps and per-image or
per-video minimum token behavior unchanged, but avoids a small amount of repeated
helper and expression overhead in the registered prompt-token hot path.

## Registered Probe

The affected Python path is covered by the registered PR-scoped performance
probe `vision-family-prompt-token-count-scan` in
`infra/perf/pr_scoped_probes.json`.

The probe includes focused `test_command`, `coverage_command`, and
`probe_command` entries for `vision_family_adapters.py`, `test_vision_runtime.py`,
`test_pr_scoped_performance.py`, and
`scripts/vision_family_prompt_token_count_probe.py`.

## Plan

1. Preserve the existing prompt, image, video, and bias token accounting behavior.
2. Normalize image divisor and video frame cost once with explicit branches.
3. Accumulate per-media token counts after explicit minimum-token clamping.
4. Return the final minimum of one token with an explicit branch instead of
   `max()`.
5. Run the registered focused tests, changed-scope coverage, and registered
   probe locally on Linux before opening the PR.

## Verification

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_vision_runtime.py::test_vision_family_prompt_token_count_matches_split_without_materializing_tokens services/mlx-worker-python/tests/test_vision_runtime.py::test_vision_family_prompt_token_count_reuses_cached_prompt_scan services/mlx-worker-python/tests/test_vision_runtime.py::test_vision_family_prompt_token_count_clamps_media_minimums services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_vision_family_prompt_token_count_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_vision_runtime.py::test_vision_family_prompt_token_count_matches_split_without_materializing_tokens services/mlx-worker-python/tests/test_vision_runtime.py::test_vision_family_prompt_token_count_reuses_cached_prompt_scan services/mlx-worker-python/tests/test_vision_runtime.py::test_vision_family_prompt_token_count_clamps_media_minimums services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_vision_family_prompt_token_count_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/runtime/vision_family_adapters.py services/mlx-worker-python/tests/test_vision_runtime.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/vision_family_prompt_token_count_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/vision_family_prompt_token_count_probe.py
```
