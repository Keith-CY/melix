# Tool Registry Single Select Direct Path

## Context

The registered PR-scoped probe `tool-registry-select-name-index-cache` covers
`services/mlx-worker-python/worker/runtime/tool_registry.py` with focused tests,
changed-scope coverage, and `scripts/tool_registry_select_probe.py`.

Baseline probe on Linux from `origin/main` (`833522dc`):

```json
{"elapsed_ms_mean": 21.74097859824542, "raw_single_config_elapsed_ms_mean": 16.803036801866256, "missing_selection_elapsed_ms_mean": 17.886221403023228, "selector_planning_elapsed_ms_mean": 39.658428795519285}
```

## Slice

Optimize only the exact single-tool `ToolRegistry.select()` path. When the
single requested name is already an exact registry key, skip the `str.strip()`
normalization and go directly through the existing name index, cache lookup, and
single-tool registry construction.

## Behavior Contract

- Exact tool names keep the same selection result.
- Whitespace-padded names continue to normalize through the existing fallback.
- Missing names keep raising `ToolRegistryError`.
- Returned configs and registries remain isolated snapshots.

## Verification Plan

1. Add a focused regression test using a string subclass whose `strip()` raises
   to prove exact single names bypass normalization.
2. Run the registered focused test command for `tool-registry-select-name-index-cache`.
3. Run the registered changed-scope coverage command.
4. Run `scripts/tool_registry_select_probe.py` locally on Linux before and after
   the change and accept only if the direction is positive or bounded and
   explainable.

## Local Results

Post-change registered coverage command passed with 86 tests and 100% changed-line
coverage for the touched scope.

Post-change probe on Linux:

```json
{"elapsed_ms_mean": 21.13232919946313, "raw_single_config_elapsed_ms_mean": 14.889508800115436, "missing_selection_elapsed_ms_mean": 15.133375799632631, "selector_planning_elapsed_ms_mean": 37.36919840448536}
```

Primary registered probe metric improved from `21.74097859824542 ms` to
`21.13232919946313 ms` (`-0.60864939878229 ms`, about `2.80%` faster). The
raw single-config submetric improved from `16.803036801866256 ms` to
`14.889508800115436 ms` (`-1.91352800175082 ms`, about `11.39%` faster).
