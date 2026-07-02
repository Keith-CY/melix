# Tool registry keyword lower fast path

## Scope

This Python-only performance slice is limited to
`services/mlx-worker-python/worker/runtime/tool_registry.py`, specifically
`_keyword_tool_matches(...)` in agentic tool selection.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`tool-registry-select-name-index-cache` in `infra/perf/pr_scoped_probes.json`.
The probe includes focused `test_command`, `coverage_command`, and
`probe_command` entries for:

- `services/mlx-worker-python/worker/runtime/tool_registry.py`
- `services/mlx-worker-python/tests/test_tool_registry.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/tool_registry_select_probe.py`

## Implementation plan

The built-in keyword hints matched by `_keyword_tool_matches(...)` are ASCII
strings. The registered select probe repeatedly routes common English user turns
through this matcher, so full Unicode `str.casefold()` is unnecessary on this
hot path. The slice uses `str.lower()` for normalization; this preserves matching
for the ASCII hint set, including when surrounding user text contains non-ASCII
characters.

A focused regression test keeps mixed non-ASCII input covered so ASCII hints
continue to match inside Unicode text.

## Verification plan

1. Run the registered focused test command for
   `tool-registry-select-name-index-cache` locally on Linux.
2. Run the registered changed-scope coverage command locally on Linux and verify
   touched Python scope remains at least 95% covered.
3. Run the registered probe locally through `scripts/pr_scoped_performance_run.py`
   against `origin/main` and this branch.
4. Use GitHub Actions PR-scoped performance as the merge gate.

## Boundary

This is a Python worker slice and is fully locally verifiable on Linux. No Swift
runtime effect is claimed.
