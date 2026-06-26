# Tool Registry Keyword Rule Item Snapshot

## Scope

This Python-only performance slice is limited to keyword selection planning in
`services/mlx-worker-python/worker/runtime/tool_registry.py`.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe
`tool-registry-select-name-index-cache` in `infra/perf/pr_scoped_probes.json`.
The probe watches `tool_registry.py`, `tests/test_tool_registry.py`,
`tests/test_pr_scoped_performance.py`, `scripts/tool_registry_select_probe.py`,
and the probe registry. It includes focused `test_command`, `coverage_command`,
and `probe_command` entries.

## Slice

`_keyword_tool_matches(...)` previously iterated the matchable tool-name tuple
and performed a dictionary lookup for each tool on every uncached keyword scan.
The compiled keyword rules are immutable after module initialization, so this
slice snapshots the ordered `(tool_name, literal_hints, boundary_hints)` pairs
once and iterates that tuple directly during selector planning.

The CI performance report also gates adjacent tool-registry probes when this
file changes, so the slice keeps the exact built-in full-selection config path
fast by checking the canonical `BUILTIN_AGENTIC_TOOL_NAMES` tuple identity before
falling back to tuple equality.

## Behavior Contract

- Tool match order stays tied to `_KEYWORD_MATCHABLE_TOOL_NAMES`.
- Literal and boundary keyword behavior is unchanged.
- Empty and whitespace-only context fast paths remain unchanged.
- The canonical full-selection `built_in_tool_config(BUILTIN_AGENTIC_TOOL_NAMES)` path returns the same isolated protobuf template copy.
- The selector receipt and selected registry outputs are unchanged.

## Verification Plan

1. Add a regression test proving `_keyword_tool_matches(...)` reads from the
   compiled rule-item snapshot rather than doing per-call rule dictionary
   lookups.
2. Run the registered focused test command for
   `tool-registry-select-name-index-cache` locally on Linux.
3. Run the registered changed-scope coverage command locally on Linux.
4. Run `scripts/tool_registry_select_probe.py` locally on Linux before and after
   the change and accept only if the registered metrics improve or remain within
   bounded noise.

## Local Results

Baseline registered probe on Linux from `origin/main` (`29eb8a26`):

```json
{"elapsed_ms_mean": 22.135713993338868, "selector_planning_elapsed_ms_mean": 34.62144880904816, "whitespace_turn_planning_elapsed_ms_mean": 30.75031420448795}
```

Post-change registered probe samples on Linux:

```json
{"elapsed_ms_mean": 21.18720880826004, "selector_planning_elapsed_ms_mean": 33.92944240476936, "whitespace_turn_planning_elapsed_ms_mean": 30.265651596710086}
{"elapsed_ms_mean": 21.33281960268505, "selector_planning_elapsed_ms_mean": 34.1142987832427, "whitespace_turn_planning_elapsed_ms_mean": 30.695827800082043}
{"elapsed_ms_mean": 22.3946534038987, "selector_planning_elapsed_ms_mean": 34.55278719775379, "whitespace_turn_planning_elapsed_ms_mean": 32.491148996632546}
```

The three post-change samples averaged `34.19884279525528 ms` for
`selector_planning_elapsed_ms_mean`, improving the baseline by
`0.42260601379287976 ms` (`1.2206479749698793%`). Changed-scope coverage was
`100%` for the touched Python scope.
