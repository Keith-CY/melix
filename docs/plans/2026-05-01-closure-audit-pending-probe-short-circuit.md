# Closure Audit Pending-Probe Short-Circuit Optimization Plan

## Goal

Reduce redundant probe-name substring checks in `worker/productization/closure_audit.py` by removing already-saturated probe names from later file scans while preserving retained source ordering and probe-gap behavior.

## Constraints

- Host verification is Linux-only.
- The touched runtime path is Python under `services/mlx-worker-python`.
- The change must remain small, behavior-preserving, and locally verifiable.
- Pull request evidence must include focused tests, changed-scope coverage, and a measurable performance probe.
- The change must stay compatible with the existing `closure-audit-probe-source-short-circuit` PR-scoped performance probe.

## Touched Files

- `docs/plans/2026-05-01-closure-audit-pending-probe-short-circuit.md`
- `services/mlx-worker-python/worker/productization/closure_audit.py`
- `services/mlx-worker-python/tests/test_closure_audit.py`

## Proposed Change

1. Track the still-unsatisfied probe names during `_collect_probe_sources(...)`.
2. Update `_scan_probe_source_file(...)` so it only checks substring membership for probes that have not yet reached their retained-source cap.
3. Keep retained source ordering, duplicate suppression, and full-scan fallback behavior unchanged.
4. Add a focused regression test proving saturated probe names are not re-checked on later files.

## Performance Probe

### Probe name

`closure-audit-probe-source-short-circuit`

### Measurement path

- Seed a synthetic repository with closure-audit evidence files.
- Run the existing PR-scoped closure-audit probe against `origin/main` and the branch worktree.
- Compare `elapsed_ms_mean` while preserving `probe_file_reads_mean` and `finding_count` semantics.

### Success metric

- Lower `elapsed_ms_mean` is better.
- `probe_file_reads_mean` should stay the same or lower.
- `finding_count` must remain unchanged.

## Local Verification Commands

```text
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_closure_audit.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_only_matching_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_smokes_return_metrics_against_current_repo services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dispatch_probe_impl_supports_evaluation_job_id_probe
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_closure_audit.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_only_matching_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_smokes_return_metrics_against_current_repo services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dispatch_probe_impl_supports_evaluation_job_id_probe
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/productization/closure_audit.py services/mlx-worker-python/tests/test_closure_audit.py
python3 scripts/pr_scoped_performance_run.py --registry infra/perf/pr_scoped_probes.json --probe-id closure-audit-probe-source-short-circuit --base-repo /root/.openclaw/workspace/melix --head-repo . --output /tmp/closure-audit-probe-run
git diff --check
```