# Job registry restore job-id path probe slice

## Scope

This Python-only performance validation slice targets `ModelOpsJobRegistry._resolved_job_id()`
when restore manifests omit an explicit `job_id` and the registry derives the job
ID from the manifest path. The behavior remains unchanged: the nearest
`model-ops-*` path component is still selected.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`job-registry-restore-sort-elision` in `infra/perf/pr_scoped_probes.json`.
This slice updates `scripts/job_registry_restore_probe.py` so the synthetic
restore payload omits `job_id`, forcing the benchmark to exercise path-derived
job IDs through `_resolved_job_id()`.

The registered probe already declares focused `test_command`, `coverage_command`,
and `probe_command` entries for:

- `services/mlx-worker-python/worker/model_ops/job_registry.py`
- `services/mlx-worker-python/tests/test_model_ops_job_registry.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/job_registry_restore_probe.py`

## Plan

1. Add regression tests proving restore derives the job ID from the manifest path
   when `job_id` is omitted, including top-level, missing, and deeper fallback
   path components.
2. Update the registered restore probe workload so it measures the fallback
   `_resolved_job_id()` path instead of bypassing it with explicit `job_id`
   payload fields.
3. Add a common-layout restore fast path that uses the manifest path string to
   read the expected parent/grandparent `model-ops-*` segment before falling
   back to the generic `Path.parts` reverse scan.
4. Do not keep the attempted full-path-only implementations: CI PR-scoped
   reports showed regressions for always using `reversed(parts)`, path-string
   scanning, and common-position indexed scans without the guarded fallback.
5. Run the registered focused tests, changed-scope coverage command, and local
   registered probe on Linux.
6. Use GitHub Actions PR-scoped performance as the merge gate after push.

## Validation boundary

This slice is Python-only and locally verifiable on Linux. No Swift runtime effect
is claimed.
