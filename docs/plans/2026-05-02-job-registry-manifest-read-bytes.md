# Job registry restore manifest byte reads

## Scope

This slice targets `services/mlx-worker-python/worker/model_ops/job_registry.py`
restore manifest decoding only. The restore path loads many small JSON manifest
files from the model-ops jobs root when rebuilding registry state, so it should
avoid an intermediate UTF-8 text decode before handing the payload to
`json.loads`.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`job-registry-derived-model-single-pass` in `infra/perf/pr_scoped_probes.json`.
This slice extends the existing probe payload with restore-from-disk metrics:

- `restore_elapsed_ms_mean`
- `restore_elapsed_ms_min`
- `restored_job_count`

The registry entry keeps focused `test_command`, `coverage_command`, and
`probe_command` entries for the job registry, its probe script, PR-scoped probe
selection, and changed-scope coverage.

## Verification plan

This slice is Python-only and locally verifiable on Linux:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_model_ops_job_registry.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_job_registry_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_job_registry_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_model_ops_job_registry.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_job_registry_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_job_registry_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/model_ops/job_registry.py services/mlx-worker-python/tests/test_model_ops_job_registry.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/job_registry_derived_model_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/pr_scoped_performance_run.py --registry infra/perf/pr_scoped_probes.json --probe-id job-registry-derived-model-single-pass --base-repo <baseline-worktree> --head-repo "$PWD" --output /tmp/job_registry_manifest_read_bytes_probe.json
```

## Success criteria

- Restore manifest parsing continues to reject invalid/missing JSON as before.
- Regression coverage proves restore manifests are read with `Path.read_bytes()`
  and do not call `Path.read_text()` for manifest payloads.
- The registered probe reports a nonzero `restore_elapsed_ms_mean` and does not
  regress relative to the synced `origin/main` baseline.
