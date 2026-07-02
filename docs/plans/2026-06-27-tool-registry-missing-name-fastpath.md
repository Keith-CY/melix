# Tool registry missing-name fast path

## Scope

This Python performance slice is limited to the single-name missing selection branch in `services/mlx-worker-python/worker/runtime/tool_registry.py`.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe `tool-registry-select-name-index-cache` in `infra/perf/pr_scoped_probes.json`. The probe watches `tool_registry.py`, focused tool registry tests, `test_pr_scoped_performance.py`, and `scripts/tool_registry_select_probe.py`, and includes focused `test_command`, `coverage_command`, and `probe_command` entries.

## Slice

For a single requested tool name that misses the registry and has no leading or trailing whitespace, `ToolRegistry.select(...)` can raise the same `ToolRegistryError` immediately. This avoids the extra `strip()` normalization branch used only for names that may trim to a valid known tool or to an empty selection.

Whitespace-padded valid names, blank names, duplicate handling, cache aliasing, and multi-name normalization remain unchanged.

## Validation plan

1. Run the registered focused `test_command` for `tool-registry-select-name-index-cache`.
2. Run the registered changed-scope `coverage_command` and require at least 95% for touched scope.
3. Run `scripts/tool_registry_select_probe.py` locally on Linux before and after the change and compare `missing_selection_elapsed_ms_mean` and overall `elapsed_ms_mean` while preserving checksum and selection counts.
4. Use GitHub Actions PR-scoped performance as the merge gate.
