# Tool registry keyword matchable names tuple

## Summary

This Python-only performance slice keeps agentic tool selection behavior unchanged
while reducing per-call work in `_keyword_tool_matches(...)`. The current keyword
matcher loops over every built-in tool name and skips always-available tools with
a membership test on each call. This slice precomputes the keyword-matchable tool
names once at module import and iterates only over that tuple.

## Registered PR-scoped probe

The affected path is covered by the registered PR-scoped performance probe
`tool-registry-select-name-index-cache` in `infra/perf/pr_scoped_probes.json`.
The entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries for:

- `services/mlx-worker-python/worker/runtime/tool_registry.py`
- `services/mlx-worker-python/tests/test_tool_registry.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/tool_registry_select_probe.py`

No probe registry change is required for this slice because the registered probe
already measures selector planning through `selector_planning_elapsed_ms_mean`.

## Optimization slice

Scope is limited to the keyword matcher inside
`worker.runtime.tool_registry.select_agentic_tools_for_turn(...)`:

- precompute `_KEYWORD_MATCHABLE_TOOL_NAMES` from built-in names excluding
  `ALWAYS_AVAILABLE_AGENTIC_TOOL_NAMES`;
- iterate the precomputed tuple in `_keyword_tool_matches(...)`;
- preserve keyword matching, literal/boundary hint behavior, always-available
  tool admission, receipt ordering, and fallback semantics.

## Verification plan

Run the registered focused test command, changed-scope coverage command, and the
registered probe locally on Linux. The PR-scoped performance workflow remains the
merge gate for base-vs-head validation.

## Success criteria

- Focused Python tests pass.
- Changed-scope coverage for touched files remains at or above 95%.
- Registered probe shows non-regressing or improved selector planning metrics.
- GitHub Actions and the PR-scoped performance workflow are green before merge.
