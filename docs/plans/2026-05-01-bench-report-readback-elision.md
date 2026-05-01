# Bench report readback elision for serving benchmark completion

## Goal

Remove the redundant `bench-report.md` readback in the serving benchmark completion path so the report markdown is rendered once, written once, and reused for persisted benchmark result records.

## Linux-only constraint

This cron run executes on Linux, so the change must stay inside Python paths that can be verified locally with targeted pytest, changed-scope coverage, and an explicit local performance probe.

## Touched files

- `services/mlx-worker-python/worker/engine/maintenance_core.py`
- `services/mlx-worker-python/tests/test_maintenance_service.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`

## Probe definition

### Local probe

Run a deterministic `RunBench` flow with `FastBenchmarkBackend`, count `Path.read_text()` calls against `bench-report.md`, and record elapsed wall time.

Success criteria:
- `bench_report_read_calls_mean` drops from `1.0` to `0.0`
- wall time does not regress materially
- emitted report content remains unchanged from the persisted file

### PR-scoped CI probe

Register a `command_json` probe that runs the same deterministic `RunBench` flow on base vs head, reporting:
- `elapsed_ms_mean`
- `bench_report_read_calls_mean`

## Verification commands

```text
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" python -m pytest -q \
  services/mlx-worker-python/tests/test_maintenance_service.py::test_run_bench_persists_report_without_reading_report_file \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_bench_report_probe

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" coverage run -m pytest -q \
  services/mlx-worker-python/tests/test_maintenance_service.py::test_run_bench_persists_report_without_reading_report_file \
  services/mlx-worker-python/tests/test_maintenance_service.py::test_run_bench_measures_runtime_behavior_from_loaded_backend \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_bench_report_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" coverage json -o /tmp/melix-bench-report-cover.json
python scripts/changed_scope_coverage.py --coverage-json /tmp/melix-bench-report-cover.json \
  services/mlx-worker-python/worker/engine/maintenance_core.py \
  services/mlx-worker-python/tests/test_maintenance_service.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" python - <<'PY'
# deterministic local perf probe for RunBench report readback
PY

git diff --check
```
