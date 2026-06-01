# Trajectory provenance exact-type copy fast path

## Scope

This performance slice narrows the already-registered trajectory provenance copy
path to a single local optimization: exact built-in JSON container and scalar
checks before the generic `isinstance` fallbacks in
`worker/trajectory_provenance.py`.

## Registered probe

The affected path is covered by `trajectory-provenance-copy-elision` in
`infra/perf/pr_scoped_probes.json`.

- `test_command`: focused trajectory provenance tests plus PR-scoped probe
  selection/script tests.
- `coverage_command`: changed-scope coverage for
  `services/mlx-worker-python/worker/trajectory_provenance.py`.
- `probe_command`: `scripts/trajectory_provenance_copy_elision_probe.py` with
  JSON metrics for elapsed time, peak bytes, delta, and speedup.

## Implementation plan

1. Preserve existing recursive copy behavior for built-in `dict`, `list`, and
   `tuple` values.
2. Check exact built-in JSON types before generic `isinstance` fallback paths so
   the common JSON provenance payload avoids repeated subclass-aware checks.
3. Keep fallback handling for custom mappings/mutables unchanged through the
   existing `isinstance` branches and `copy.deepcopy` fallback.
4. Validate locally on Linux with focused tests, changed-scope coverage, and the
   registered probe.

## Validation boundary

This is a Python worker path and is locally verifiable on Linux. Swift runtime
validation is not involved.

## Adjacent probe noise guard

Because `trajectory-manifest-json-load` watches the same implementation file, it
runs as an adjacent direct probe for this slice. Its actionable gates remain
`new_mean_ms` and `new_peak_bytes_mean`; the derived `speedup` ratio is now
informational so base-side timing variance cannot block an unrelated copy-path
improvement when the head runtime and peak memory metrics remain neutral.
