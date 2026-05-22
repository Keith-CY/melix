# Serving diagnostics queue append local binding

## Scope

This Python-only performance slice is limited to the debug serving diagnostics
queue append path in
`services/mlx-worker-python/worker/productization/serving_diagnostics.py`.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`serving-diagnostics-debug-queue-bounds` in
`infra/perf/pr_scoped_probes.json`. The registry entry defines focused
`test_command`, `coverage_command`, and `probe_command` values and reports queue
append elapsed time, serialization elapsed time, dropped/retained counts,
serialization checksum, and serialized byte count.

## Change

`BoundedServingDiagnosticsEventQueue.append()` now binds the deque append method
once per call before the saturated and unsaturated branches, and only writes the
saturation flag when the queue first reaches capacity. This keeps the existing
lock discipline, retained-count tracking, and bounded-drop semantics unchanged
while reducing repeated instance attribute work on the hot append path.

## Validation plan

1. Run the focused serving diagnostics tests plus the PR-scoped probe registry
   tests for this probe.
2. Run changed-scope coverage for the changed source path and probe/test files.
3. Run the registered probe locally on Linux against `origin/main` and this
   branch before pushing.
4. Use PR-scoped performance CI as the final registered probe gate before merge.

## Local result

Local Linux probe, `MELIX_SERVING_DIAGNOSTICS_QUEUE_SAMPLES=20`:

- base (`origin/main`, three runs): `elapsed_ms_mean=5.349750/5.420551/5.687914`,
  `serialization_elapsed_ms_mean=0.947616/0.946771/1.074048`
- head (three runs): `elapsed_ms_mean=5.501639/5.273962/5.428044`,
  `serialization_elapsed_ms_mean=0.960166/0.936282/0.979539`
- mean queue append delta: `-0.084857 ms` (`-1.55%`)
- mean serialization delta: `-0.030816 ms` (`-3.12%`), with unchanged
  `serialization_checksum=260064` and `serialized_bytes=10944`
