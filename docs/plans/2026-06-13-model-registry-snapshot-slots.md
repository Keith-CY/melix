# Model Registry Snapshot Slots Slice

## Scope

Reduce per-snapshot allocation overhead in `WorkerModelCatalog.registry_snapshot()` by
slotting the two immutable snapshot container dataclasses:

- `RegistryRootSnapshot`
- `RegistrySnapshot`

The affected path is covered by the registered PR-scoped performance probe
`model-registry-plain-local-manifest-stat-elision` in
`infra/perf/pr_scoped_probes.json`. The registry entry already includes focused
`test_command`, `coverage_command`, and `probe_command` values for
`worker/model_registry/catalog.py`.

## Plan

1. Keep the existing registry probe unchanged.
2. Add `slots=True` to the immutable snapshot dataclasses only.
3. Run the registered focused tests, changed-scope coverage, and local Linux
   registered probe against `origin/main` and this branch.
4. Accept only if behavior remains unchanged and the probe does not regress.

## Validation Boundary

This is a Python-only slice and is locally verifiable on Linux. GitHub Actions
PR-scoped performance remains the merge gate after push.