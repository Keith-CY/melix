# Model Registry Cached Runtime Rebuild Elision

## Goal

Avoid rebuilding `WorkerModelCatalog` runtime model dictionaries on repeated cached `registry_snapshot()` and `registry_snapshot_payload()` calls when the active snapshot object and overlay model set have not changed.

## Scope

- `services/mlx-worker-python/worker/model_registry/catalog.py`
- `services/mlx-worker-python/tests/test_model_registry_catalog.py`

## Linux Constraint

This is a Python-only worker optimization and can be verified on Linux with focused pytest, changed-scope coverage, and a synthetic cached-snapshot performance probe.

## Probe Definition

The local probe builds a synthetic registry with many plain-local models, warms one snapshot, then repeatedly calls cached `registry_snapshot_payload()` while counting runtime rebuild invocations and timing the loop against `origin/main` and the branch.

Success metrics:

- Preserve identical payload model counts.
- Reduce cached-loop runtime rebuild calls from once per cached snapshot call to zero after warm-up.
- Reduce elapsed time for repeated cached snapshot payload calls.

## Verification Commands

- Focused pytest for model registry tests covering overlay mutation, rescan, and cached no-op behavior.
- Focused coverage plus changed-scope coverage from the uncommitted diff; require >=95%.
- Explicit local base-vs-head probe with concrete elapsed/rebuild-count metrics.
- `git diff --check`.
