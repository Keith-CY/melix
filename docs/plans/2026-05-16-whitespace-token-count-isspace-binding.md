# Whitespace token count isspace binding slice

## Scope

This Python-only performance slice is limited to the shared whitespace token
counter used by vision-family prompt token accounting:

- `services/mlx-worker-python/worker/runtime/token_counting.py`
- existing focused regression coverage in `services/mlx-worker-python/tests/test_vision_runtime.py`

## Registered probe

The affected path is already covered by the PR-scoped probe
`vision-family-prompt-token-count-scan` in
`infra/perf/pr_scoped_probes.json`. The registry entry watches
`token_counting.py` and provides focused `test_command`, `coverage_command`, and
`probe_command` entries.

## Optimization

Bind `str.isspace` once before the scan loop so repeated prompt-token scans avoid
per-character bound-method lookup while preserving the current Unicode whitespace
semantics and the no-`split()` allocation contract.

## Verification plan

Run the registered focused commands locally on Linux:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_vision_runtime.py::test_vision_family_prompt_token_count_matches_split_without_materializing_tokens services/mlx-worker-python/tests/test_vision_runtime.py::test_vision_family_prompt_token_count_reuses_cached_prompt_scan services/mlx-worker-python/tests/test_vision_runtime.py::test_vision_family_prompt_token_count_clamps_media_minimums services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_vision_family_prompt_token_count_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_vision_runtime.py::test_vision_family_prompt_token_count_matches_split_without_materializing_tokens services/mlx-worker-python/tests/test_vision_runtime.py::test_vision_family_prompt_token_count_reuses_cached_prompt_scan services/mlx-worker-python/tests/test_vision_runtime.py::test_vision_family_prompt_token_count_clamps_media_minimums services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_vision_family_prompt_token_count_probe_script_emits_metrics && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/runtime/vision_family_adapters.py services/mlx-worker-python/worker/runtime/token_counting.py services/mlx-worker-python/tests/test_vision_runtime.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/vision_family_prompt_token_count_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/vision_family_prompt_token_count_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/pr_scoped_performance_run.py --registry infra/perf/pr_scoped_probes.json --probe-id vision-family-prompt-token-count-scan --base-repo <origin-main-worktree> --head-repo "$PWD" --output /tmp/vision-family-prompt-token-count-scan.json
```

## Acceptance criteria

- Focused behavior tests pass.
- Changed-scope coverage remains at least 95%.
- The registered probe reports no `split()` calls and lower `elapsed_ms_mean`
  versus `origin/main`.
