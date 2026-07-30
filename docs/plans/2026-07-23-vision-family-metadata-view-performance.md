# Vision family metadata view performance slice

## Scope

Optimize one Python hot path in `worker/runtime/vision_family_adapters.py`: resolving
vision-family and processor metadata should read caller-provided metadata as a mapping
view instead of materializing a defensive `dict` copy for every call.

## Registered probe

The affected path is covered by the existing PR-scoped registered probe
`vision-family-prompt-token-count-scan` in `infra/perf/pr_scoped_probes.json`.
That registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` commands and watches:

- `services/mlx-worker-python/worker/runtime/vision_family_adapters.py`
- `services/mlx-worker-python/worker/runtime/token_counting.py`
- `services/mlx-worker-python/tests/test_vision_runtime.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/vision_family_prompt_token_count_probe.py`

## Plan

1. Add regression coverage that metadata resolution and processor capability
   helpers can read a mapping without iterating over it for a copy.
2. Replace per-call `dict(metadata or {})` materialization with direct mapping
   reads in the vision-family adapter helpers.
3. Run the focused registered test command, changed-scope coverage command, and
   registered probe locally on Linux.
4. Create a PR and rely on GitHub Actions PR-scoped performance for CI validation.

## Linux verification boundary

This is a Python-only slice and is locally verifiable on Linux. No Swift runtime
effect is claimed.
