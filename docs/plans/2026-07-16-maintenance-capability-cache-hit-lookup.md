# Maintenance capability cache-hit lookup fast path

## Scope

This Python-only performance slice is limited to the single-value capability
metadata parser in `services/mlx-worker-python/worker/engine/maintenance_core.py`.
The parser already keeps a bounded cache for repeated scalar capability values
and an LRU-cached tuple for comma-separated values. This slice narrows the hot
cache-hit branch from `dict.get(..., sentinel)` plus an identity check to direct
`dict.__getitem__` with a `KeyError` miss path, and uses list-unpack
materialization for cached comma-separated tuples.

Behavior stays unchanged: comma-separated capability values still use the cached
tuple splitter, scalar values still return a fresh mutable `list[str]`, blank
scalar values still return an empty list, and the bounded cache is still cleared
before inserting after it reaches its maximum size.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe
`maintenance-capability-split-single-strip` in
`infra/perf/pr_scoped_probes.json`. The entry includes focused
`test_command`, `coverage_command`, and `probe_command` values for:

- `services/mlx-worker-python/worker/engine/maintenance_core.py`
- `services/mlx-worker-python/tests/test_maintenance_service.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/maintenance_capability_split_probe.py`

## Implementation Plan

1. Keep the existing cache and list-returning contract intact.
2. Use direct dictionary indexing on the scalar cache-hit path, falling back to
   the existing strip/cache-insert logic only on `KeyError`.
3. Materialize cached comma-separated tuples with list-unpack syntax while still
   returning an isolated list.
4. Run the registered focused test command, changed-scope coverage command,
   `git diff --check`, and the registered probe locally on Linux before opening
   the PR.
5. Use GitHub Actions PR-scoped performance as the final registered probe gate
   before merge.

## Expected Signal

The registered probe reports both comma-separated split performance and repeated
single-value split performance. This slice targets `single_elapsed_ms_mean` and
should keep `elapsed_ms_mean` neutral-to-improved for the comma-separated cached
tuple path.
