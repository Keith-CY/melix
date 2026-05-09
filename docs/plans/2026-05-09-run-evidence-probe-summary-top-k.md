# Run Evidence Probe Summary Top-K Plan

## Goal

Reduce unnecessary work in `summarize_probe_timeline()` when rendering the `slowest_phases` summary. The current implementation sorts the full probe timeline even though the output keeps only the top five rows.

## Scope

- `services/mlx-worker-python/worker/productization/run_evidence.py`
- `services/mlx-worker-python/tests/test_run_evidence.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/run_evidence_probe_summary_probe.py`
- `infra/perf/pr_scoped_probes.json`

## Linux Constraint

This is a Python-only worker/productization slice and can be verified on Linux with focused pytest, changed-scope coverage, and a local PR-scoped performance probe.

## Performance Probe

Registered PR-scoped probe: `run-evidence-probe-summary-top-k`.

The probe builds a large synthetic probe timeline, calls `summarize_probe_timeline()` repeatedly, and reports:

- `elapsed_ms_mean`
- `peak_bytes_mean`
- `probe_count`
- `slowest_count`

## Success Metrics

- Preserve slowest phase output shape and stable ordering for ties.
- Achieve at least 95% changed executable line coverage for touched Python files.
- Improve or hold the local base-vs-head probe metrics while reducing full-list sort work.

## Verification Commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_run_evidence.py::test_probe_timeline_slowest_phases_preserve_stable_top_five_order services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_run_evidence_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_run_evidence_probe_summary_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_run_evidence.py::test_probe_timeline_slowest_phases_preserve_stable_top_five_order services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_run_evidence_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_run_evidence_probe_summary_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/productization/run_evidence.py services/mlx-worker-python/tests/test_run_evidence.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/run_evidence_probe_summary_probe.py
MELIX_RUN_EVIDENCE_PROBE_COUNT=100000 MELIX_RUN_EVIDENCE_PROBE_SAMPLES=5 PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python scripts/run_evidence_probe_summary_probe.py
python scripts/pr_scoped_performance_run.py --probe-id run-evidence-probe-summary-top-k --base-ref origin/main --head-ref HEAD --output-json /tmp/run-evidence-probe-summary.json
```
