# Trajectory manifest exact-dict load type fast path

This Python-only performance slice is limited to `worker.trajectory_provenance.load_trajectory_provenance_from_snapshot_manifest`.

## Scope

Snapshot manifest loading decodes JSON bytes and then rejects non-mapping payloads before extracting trajectory provenance. The normal hot path receives an exact `dict` from `json.loads`; dict subclasses remain supported for compatibility with monkeypatched loaders or custom decoders.

## Registered probe

The affected path is covered by the registered PR-scoped probe `trajectory-manifest-json-load` in `infra/perf/pr_scoped_probes.json`.

The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` values for:

- `services/mlx-worker-python/worker/trajectory_provenance.py`
- `services/mlx-worker-python/tests/test_trajectory_provenance.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/trajectory_manifest_json_load_probe.py`

## Implementation plan

1. Add focused regression coverage proving a dict subclass payload from the JSON loader is still accepted.
2. Fast-path exact `dict` decoded payloads before the generic `isinstance(payload, dict)` fallback.
3. Verify with the registered focused tests, changed-scope coverage, and local registered probe on Linux.
4. Use PR-scoped performance CI as the merge gate.

## Metrics

Target metric: lower `new_mean_ms` / `elapsed_ms_mean` in `trajectory-manifest-json-load` with unchanged iteration and component counts.
