# Maintenance capability split single-strip performance

## Scope

This slice targets capability metadata parsing in `services/mlx-worker-python/worker/engine/maintenance_core.py`, specifically `_split_capability_values()` used by model-info capability lists.

## Probe coverage

`infra/perf/pr_scoped_probes.json` registers `maintenance-capability-split-single-strip` for the touched maintenance-core path. The entry includes focused `test_command`, `coverage_command`, and `probe_command` values, with `scripts/maintenance_capability_split_probe.py` measuring baseline list-comprehension splitting against the current implementation.

## Implementation plan

- Preserve comma-separated capability parsing semantics: trim whitespace, drop empty segments, keep order.
- Replace the list comprehension that calls `strip()` in both the expression and filter with a small loop that strips each segment once.
- Validate locally on Linux with the registered focused tests, changed-scope coverage, and the registered Python probe.

## Validation boundary

This is a Python-only Linux-verifiable slice. No Swift runtime effect is claimed.
