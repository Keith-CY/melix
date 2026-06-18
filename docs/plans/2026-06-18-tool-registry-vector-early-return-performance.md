# Tool Registry Vector Selection Early Return Performance Slice

## Scope

This slice optimizes `select_agentic_tools_for_turn()` when vector routing yields
at least one valid tool. In that path the selected tool set is already final:
keyword fallback is intentionally bypassed, so the function can build and return
the selection receipt immediately instead of carrying vector state through the
remaining fallback branch and final dispatch.

Behavior remains unchanged: selected tools keep the same registry order, source
receipts, fallback reasons, vector availability, and schema-byte accounting.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`tool-registry-select-name-index-cache` in `infra/perf/pr_scoped_probes.json`.
That registry entry includes focused tool-registry behavior tests,
changed-scope coverage, and `scripts/tool_registry_select_probe.py`. The probe
reports `selector_planning_elapsed_ms_mean`, whose mixed selection workload
includes the vector-hit path optimized by this slice.

## Verification plan

- Run the registered focused test command for the tool-registry selection probe.
- Run the registered changed-scope coverage command for the same probe.
- Run `scripts/tool_registry_select_probe.py` locally on Linux against the base
  and head implementations with repeated samples, comparing selector planning
  metrics and ensuring selected schema bytes remain stable.
- Use the GitHub Actions PR-scoped performance workflow as the final registered
  probe validation before merge.

## Expected outcome

Returning immediately after a valid vector selection avoids one extra branch and
the final shared return path for vector-hit requests. The expected benefit is
primarily visible in `selector_planning_elapsed_ms_mean`; unrelated selection
and config metrics may remain within normal measurement noise.
