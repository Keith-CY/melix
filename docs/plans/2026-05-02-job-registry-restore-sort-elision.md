# Job registry restore sort-elision performance slice

## Goal

Reduce cold `ModelOpsJobRegistry(jobs_root=...)` restore overhead by removing redundant sorting of restore manifest paths after `_collect_restore_manifest_paths()` already returns each operation list in sorted order, while preserving restore ordering, duplicate handling, and restored job contents.

## Linux-only constraint

This slice is Python-only under `services/mlx-worker-python`, so it can be fully verified from this Linux host without relying on macOS or Swift execution.

## Touched files

- `services/mlx-worker-python/worker/model_ops/job_registry.py`
- `services/mlx-worker-python/tests/test_model_ops_job_registry.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`
- `scripts/job_registry_restore_probe.py`

## Optimization hypothesis

`_collect_restore_manifest_paths()` sorts the `train_lora`, `activate_adapter`, and `remove_derived_model` manifest lists before returning them. `_restore_manifest_jobs()` then re-sorts each already-sorted list before reading manifests. On large cold restore inputs this adds avoidable comparison work for every operation bucket without changing restore semantics.

This slice removes the second sort, adds a regression test that fails if `_restore_manifest_jobs()` falls back to `sorted(...)`, and registers a dedicated PR-scoped restore probe so the cold-restore path is measured directly instead of inferred from the unrelated active-derived-model probe.

## Registered scoped probe

Add a dedicated PR-scoped probe for the restore path:

- Probe ID: `job-registry-restore-sort-elision`
- Measured metrics:
  - `restore_elapsed_ms_mean` (lower is better)
  - `per_manifest_ms_mean` (lower is better)
- Probe workload:
  - seed a synthetic `jobs_root` with many `train_lora`, `activate_adapter`, and `remove_derived_model` manifests
  - instantiate `ModelOpsJobRegistry(jobs_root=...)`
  - assert restored job count matches the seeded manifest count before timing is accepted

## Verification commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q \
  services/mlx-worker-python/tests/test_model_ops_job_registry.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_job_registry_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_job_registry_probe_script_emits_metrics \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_job_registry_restore_probe_script_emits_metrics

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q \
  services/mlx-worker-python/tests/test_model_ops_job_registry.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_job_registry_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_job_registry_probe_script_emits_metrics \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_job_registry_restore_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json \
  services/mlx-worker-python/worker/model_ops/job_registry.py \
  services/mlx-worker-python/tests/test_model_ops_job_registry.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py \
  scripts/job_registry_restore_probe.py

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/job_registry_restore_probe.py

git diff --check
```

## Success criteria

- Focused tests pass.
- Changed-scope automated coverage is at least 95%.
- The dedicated restore probe emits concrete restore metrics and validates the expected restored job count.
- Local base-vs-head restore probe numbers show the branch faster than `origin/main`.
- PR-scoped CI runs the dedicated restore probe before merge.
