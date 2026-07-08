# Maintenance capability single-value cache

## Scope

This Python-only performance slice is limited to capability metadata parsing in
`services/mlx-worker-python/worker/engine/maintenance_core.py`. The change keeps
`_split_capability_values()` returning a fresh mutable `list[str]` for every
call while reusing the existing cached tuple helper for repeated single-value
capability metadata such as `" qwen "`.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe
`maintenance-capability-split-single-strip` in `infra/perf/pr_scoped_probes.json`.
The registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries for:

- `services/mlx-worker-python/worker/engine/maintenance_core.py`
- `services/mlx-worker-python/tests/test_maintenance_service.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/maintenance_capability_split_probe.py`

## Implementation Plan

1. Add a small bounded scalar cache for single-value capability strings so
   repeated model metadata avoids repeated `.strip()` work on cache hits.
2. Preserve the existing cached tuple path for comma-separated values.
3. Preserve isolated list semantics by allocating a fresh list at the public
   helper boundary.
4. Add regression coverage proving single-value cache hits do not leak mutable
   list state between callers.

## Verification

Run the registered focused tests, changed-scope coverage command, `git diff --check`,
and the registered `maintenance-capability-split-single-strip` probe locally on
Linux before opening the PR. GitHub Actions PR-scoped performance remains the
final registered probe validation and merge gate.
