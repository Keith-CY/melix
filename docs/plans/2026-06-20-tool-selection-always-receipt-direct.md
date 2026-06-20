# Tool selection always-only direct receipt slice

## Scope

This Python-only performance slice is limited to `select_agentic_tools_for_turn(...)` in `services/mlx-worker-python/worker/runtime/tool_registry.py` when `max_selected_tools` clamps to one.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe `tool-registry-select-name-index-cache` in `infra/perf/pr_scoped_probes.json`.

The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/runtime/tool_registry.py`
- `services/mlx-worker-python/tests/test_tool_registry.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/tool_registry_select_probe.py`

The primary metric for this slice is `always_only_planning_elapsed_ms_mean`; the broader selector metrics should remain neutral.

## Optimization plan

1. Keep the existing always-only behavior: `local_compute` remains the only selected tool, vector availability is still reported, and keyword/vector scans are skipped.
2. Replace the generic receipt builder call on the always-only branch with a direct helper that avoids allocating the transient selected-name list and source map.
3. Run focused tool-registry tests, changed-scope coverage, and the registered probe locally on Linux.
4. Use GitHub Actions PR-scoped performance as the merge gate.

## Expected performance signal

The expected directional signal is lower `always_only_planning_elapsed_ms_mean` from removing per-call transient collection allocation on the `max_selected_tools == 1` hot path. Overall selector metrics may remain neutral because the probe also exercises vector, keyword, registry-selection, and config-template paths.
