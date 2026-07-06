# Engine Usage Integer Fast Path

This Python-only performance slice is limited to the generate usage accounting helper `worker.engine.engine_core._non_negative_int()`.

## Scope

The generate usage path normalizes prompt, completion, cached-prompt, and media usage counters through `_non_negative_int()`. Those values are already plain non-negative Python integers on the common runtime-event path, but the helper still routed them through `int(value or 0)` inside a `try` block. This slice adds an exact-`int` fast path while preserving the existing fallback behavior for negative integers, strings, `None`, and invalid values.

No protobuf schema, runtime contract, or generated artifact changes are included.

## Registered Performance Probe

The affected path is covered by the registered PR-scoped probe `engine-generate-usage-token-elision` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries covering:

- `services/mlx-worker-python/worker/engine/engine_core.py`
- `services/mlx-worker-python/tests/test_generate_stream.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/engine_generate_usage_token_probe.py`

## Verification Plan

Run the focused local Linux verification before opening the PR:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_generate_stream.py::test_text_native_mtp_parser_metrics_fast_paths_empty_events
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/pr_scoped_performance_run.py --registry infra/perf/pr_scoped_probes.json --probe-id engine-generate-usage-token-elision --base-repo <baseline-worktree> --head-repo "$PWD" --output /tmp/engine_usage_probe.json
```

GitHub Actions PR-scoped performance remains the merge gate after the PR is opened.

## Success Criteria

- Focused generate usage tests pass.
- Changed-scope coverage for the touched engine lines is at least 95%.
- The registered probe remains behaviorally equivalent: prompt token fallback calls and request-state append calls stay at zero per request.
- The registered CI PR-scoped performance report completes successfully before merge.
