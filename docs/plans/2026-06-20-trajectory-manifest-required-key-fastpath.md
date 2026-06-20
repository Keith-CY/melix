# Trajectory Manifest Required-Key Fast Path Slice

## Scope

This slice keeps trajectory provenance behavior unchanged and narrows one Python
hot path in `services/mlx-worker-python/worker/trajectory_provenance.py`.
The target is the clean JSON manifest branch used by
`load_trajectory_provenance_from_snapshot_manifest` after parsing a snapshot
`manifest.json` from bytes.

## Registered Probe

The affected path is covered by the registered PR-scoped probe
`trajectory-manifest-json-load` in `infra/perf/pr_scoped_probes.json`. The
registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries for:

- `services/mlx-worker-python/worker/trajectory_provenance.py`
- `services/mlx-worker-python/tests/test_trajectory_provenance.py`
- `scripts/trajectory_manifest_json_load_probe.py`

## Implementation Plan

1. Preserve the bytes-based JSON load and existing fallback behavior for dirty,
   missing, subclassed, or defaulted manifest fields.
2. Narrow `_is_clean_manifest_text` to avoid the generic `bool(...)` call on the
   common exact-string path while keeping empty-string rejection intact.
3. Replace the clean-manifest required-key loop with direct local bindings for
   the five required text fields, avoiding the hot-loop tuple iteration and the
   second dictionary lookup when building the provenance payload.
4. Replace the optional-field tuple loop with explicit local bindings for the
   seven optional manifest fields, preserving empty-string filtering while
   removing per-call tuple iteration in the same clean-manifest branch.
5. Add a regression test proving the fast path still falls back to defaulted
   required fields when the manifest omits `trajectory_schema_version` and
   `trajectory_split`.
6. Run the registered focused tests, changed-scope coverage, and local Linux
   registered probe before opening the PR.
7. Use the PR-scoped performance workflow as the merge gate for the registered
   probe.

## Linux Probe Notes

Pre-change local probe from synced `origin/main` in the task worktree:

```text
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" \
MELIX_TRAJECTORY_MANIFEST_JSON_REPO_ROOT="$PWD" \
MELIX_TRAJECTORY_MANIFEST_JSON_PROBE_SAMPLES=5 \
MELIX_TRAJECTORY_MANIFEST_JSON_PROBE_ITERATIONS=2000 \
uv run --project services/mlx-worker-python python3 scripts/trajectory_manifest_json_load_probe.py

old_mean_ms=1382.439, new_mean_ms=712.650, speedup=1.940x, delta_ms=-669.790
```

Post-change local probe will be recorded in the PR evidence after implementation
verification. The authoritative merge gate remains the registered PR-scoped
performance CI report.
