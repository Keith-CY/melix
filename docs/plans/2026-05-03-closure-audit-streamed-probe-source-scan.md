# Closure Audit Streamed Probe-Source Scan

## Goal

Reduce redundant memory pressure in `services/mlx-worker-python/worker/productization/closure_audit.py` when scanning probe-source text files by avoiding full-file `read_text()` materialization and by stopping the scan once all pending probe names have been found for the current file.

## Linux Constraint

This is a Python-only optimization slice that is fully verifiable on Linux. No macOS or Swift behavior is changed.

## Touched Files

- `services/mlx-worker-python/worker/productization/closure_audit.py`
- `services/mlx-worker-python/tests/test_closure_audit.py`
- `services/mlx-worker-python/worker/productization/pr_scoped_performance.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`

## Planned Change

1. Replace the full-file `Path.read_text(..., errors="ignore")` scan in `_scan_probe_source_file(...)` with a streamed reader that checks only unresolved probe names.
2. Stop reading the current file as soon as every still-pending probe name for that file has either matched or cannot improve the current pass further.
3. Keep relative-path ordering, duplicate suppression, preferred-file precedence, and three-source saturation behavior unchanged.
4. Update the registered `closure-audit-probe-source-short-circuit` PR-scoped probe so CI also measures traced peak memory on the closure-audit path.

## Performance Probe

Registered probe: `closure-audit-probe-source-short-circuit`

Probe adjustments:
- Seed one large preferred evidence file so the probe exercises the hot path on a large text input.
- Record:
  - `elapsed_ms_mean`
  - `probe_file_reads_mean`
  - `peak_bytes_mean`

## Success Metrics

- Behavior remains identical for probe-source discovery and closure-audit findings.
- Changed-scope automated coverage is at least 95%.
- Local probe shows lower `peak_bytes_mean` than `origin/main`.
- No regression in `probe_file_reads_mean`.
- Elapsed time should improve or remain within normal probe tolerance.

## Verification Commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q \
  services/mlx-worker-python/tests/test_closure_audit.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_only_matching_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_smokes_return_metrics_against_current_repo \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dispatch_probe_impl_supports_evaluation_job_id_probe

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q \
  services/mlx-worker-python/tests/test_closure_audit.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_only_matching_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_smokes_return_metrics_against_current_repo \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dispatch_probe_impl_supports_evaluation_job_id_probe
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python scripts/changed_scope_coverage.py --coverage-json coverage.json \
  services/mlx-worker-python/worker/productization/closure_audit.py \
  services/mlx-worker-python/worker/productization/pr_scoped_performance.py \
  services/mlx-worker-python/tests/test_closure_audit.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python scripts/pr_scoped_performance_run.py \
  --probe-id closure-audit-probe-source-short-circuit --output /tmp/closure-audit-head.json

git diff --check
```
