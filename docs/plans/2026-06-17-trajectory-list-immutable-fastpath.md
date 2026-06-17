# Trajectory provenance scalar list copy fast path

## Scope

This slice keeps trajectory provenance normalization behavior unchanged while
extending the existing JSON scalar-list copy fast path beyond lists of four
items. The target path is `services/mlx-worker-python/worker/trajectory_provenance.py`.

## Probe coverage

The affected path is covered by the registered PR-scoped probe
`trajectory-provenance-copy-elision` in `infra/perf/pr_scoped_probes.json`. The
probe has focused `test_command`, `coverage_command`, and `probe_command`
entries and exercises trajectory quality component labels.

## Implementation plan

- Preserve deep-copy isolation for nested mutable containers.
- Detect all-immutable JSON lists with one linear scan and copy them directly
  with `list.copy()` instead of recursive per-item dispatch.
- Extend focused tests so scalar lists longer than four items avoid recursive
  copy dispatch.
- Use the existing registered probe fixture to verify the scalar list copy path
  still improves the trajectory normalization workload without widening the PR
  scope.

## Verification

Run the registered test command, changed-scope coverage command, and probe
command locally on Linux before opening the PR. GitHub Actions remains the
registered PR-scoped performance gate before merge.
