# Tool Registry Raw Selection Config Cache Slice

## Scope

This Python performance slice is limited to the built-in agentic tool config
selection path in `services/mlx-worker-python/worker/runtime/tool_registry.py`.
It preserves tool selection semantics, protobuf schemas, and copy-on-return
isolation while reducing repeated normalized-selection work for raw selection
inputs that differ from their canonical registry names only by whitespace.

## Registered Probe

The affected path is covered by the registered PR-scoped probe
`tool-registry-select-name-index-cache` in `infra/perf/pr_scoped_probes.json`.
That entry has focused `test_command`, `coverage_command`, and `probe_command`
commands and watches `tool_registry.py`, `test_tool_registry.py`, and
`scripts/tool_registry_select_probe.py`.

This slice extends the probe script with a raw single-name config selection
metric so CI and local Linux validation measure the path optimized here.

## Implementation Plan

1. Add a regression test proving repeated raw built-in config selections cache
   the serialized selection under both the raw and normalized keys without
   weakening copy isolation.
2. Store the raw requested-name tuple as an alias when `built_in_tool_config()`
   normalizes a selection through the registry.
3. Extend `scripts/tool_registry_select_probe.py` with
   `raw_single_config_elapsed_ms_mean`.
4. Run focused tests, changed-scope coverage, and the registered probe locally.

## Success Metrics

- `raw_single_config_elapsed_ms_mean` decreases on the local Linux probe.
- Existing `tool-registry-select-name-index-cache` metrics remain stable.
- Changed-scope coverage for touched Python paths remains at least 95%.
