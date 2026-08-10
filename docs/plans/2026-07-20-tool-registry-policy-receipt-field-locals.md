# Tool registry policy receipt field locals

## Goal

Reduce repeated list construction in policy-aware agentic tool-selection receipts while preserving receipt isolation and selection semantics.

## Scope

This Python-only slice is limited to `services/mlx-worker-python/worker/runtime/tool_registry.py` and the registered PR-scoped probe script `scripts/tool_registry_select_probe.py`.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe `tool-registry-select-name-index-cache` in `infra/perf/pr_scoped_probes.json`. The probe already includes focused `test_command`, `coverage_command`, and `probe_command` entries for the tool registry path, focused tests, and `scripts/tool_registry_select_probe.py`.

This slice extends that probe with a policy-aware selection case so `allow_web=False` receipt assembly has an explicit machine-readable metric: `policy_planning_elapsed_ms_mean`.

## Implementation

`_agentic_tool_policy_receipt()` now reuses cached single-field list templates for the stable web policy fields and copies the already-deduplicated denied-tool accumulator directly. The common `allow_web=False` path also copies the cached network-capable tool list instead of scanning all selectable tool names for each receipt. Returned receipts still contain fresh mutable lists, so callers cannot mutate cached state.

## Verification

- Run the focused registered test command locally on Linux.
- Run the changed-scope coverage command locally on Linux.
- Run the registered probe locally on Linux and compare `policy_planning_elapsed_ms_mean` before/after the production change.
- Let the PR-scoped performance workflow validate the registered probe in CI before merging.

## Follow-up Slice: Preflight Callable Tools List Copy

The 2026-08-10 follow-up keeps agentic tool schema-consistency receipts isolated
and behavior-compatible, but reuses the registry's cached tool-name list snapshot
when building `callable_tools`. `preflight_agentic_tool_schema_consistency()` is
called repeatedly by the registered selector probe and no longer needs to rebuild
a list from the canonical tuple for every receipt.

Expected effect:

- reduce `tool-registry-select-name-index-cache` `preflight_consistency_elapsed_ms_mean`;
- preserve fresh mutable `callable_tools` receipt lists for callers;
- leave referenced-tool ordering, missing-tool detection, registry selection, and
  tool config serialization unchanged.
