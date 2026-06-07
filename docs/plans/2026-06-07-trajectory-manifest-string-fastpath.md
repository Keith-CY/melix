# Trajectory Manifest String Fast Path

## Scope

This Python-only performance slice is limited to `worker.trajectory_provenance._trajectory_provenance_from_snapshot_manifest()` and its JSON-load caller. The slice keeps the manifest provenance contract unchanged while reducing repeated `str(...).strip()` work for the common normalized manifest case where string fields are already plain, non-empty, and whitespace-free.

## Registered Probe

The affected path is covered by the existing registered PR-scoped probe `trajectory-manifest-json-load` in `infra/perf/pr_scoped_probes.json`. That probe already declares focused `test_command`, `coverage_command`, and `probe_command` entries, and watches:

- `services/mlx-worker-python/worker/trajectory_provenance.py`
- `services/mlx-worker-python/tests/test_trajectory_provenance.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/trajectory_manifest_json_load_probe.py`
- `infra/perf/pr_scoped_probes.json`

## Plan

1. Add a narrow regression assertion that whitespace-padded manifest strings are still trimmed.
2. Introduce a small string normalization fast path that returns already-clean exact `str` values without allocating a stripped copy.
3. Use the helper only inside snapshot manifest provenance extraction and keep nested provenance copy behavior unchanged.
4. Run focused pytest, changed-scope coverage, and the registered probe locally on Linux.
5. Use GitHub Actions plus the registered PR-scoped performance report as the merge gate.

## Metrics

Local Linux verification uses the registered command-json probe:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" MELIX_TRAJECTORY_MANIFEST_JSON_REPO_ROOT="$PWD" uv run --project services/mlx-worker-python bash -c 'SCRIPT="scripts/trajectory_manifest_json_load_probe.py"; if [ -f "$SCRIPT" ]; then python3 "$SCRIPT"; else for CANDIDATE in "../head/$SCRIPT" "${GITHUB_WORKSPACE:-}/head/$SCRIPT"; do if [ -f "$CANDIDATE" ]; then python3 "$CANDIDATE"; exit $?; fi; done; echo "missing probe script fallback for $SCRIPT" >&2; exit 2; fi'
```

CI remains the authoritative base-vs-head validation source for the registered PR-scoped performance report.
