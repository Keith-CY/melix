# Report evidence matrix run-kind disjoint fast path

## Scope

This Python-only performance slice is limited to `_report_matrix_roles()` in
`services/mlx-worker-python/worker/productization/report_evidence_gate.py`.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`report-evidence-gate-run-kind-set-membership` in `infra/perf/pr_scoped_probes.json`. The
registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` fields and watches:

- `services/mlx-worker-python/worker/productization/report_evidence_gate.py`
- `services/mlx-worker-python/tests/test_report_evidence_gate.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/report_evidence_gate_run_kind_probe.py`
- `infra/perf/pr_scoped_probes.json`

## Optimization plan

`_report_matrix_roles()` already precomputes the observed report run kinds once
for run-kind-only release matrix rules. The prior membership check used set
intersection (`rule_run_kinds & report_run_kinds`), which allocates a temporary
intersection set for each rule. This slice replaces that with
`isdisjoint(...)`, preserving the same truth condition while avoiding the
per-rule temporary set allocation.

The change preserves non-string run-kind normalization, output ordering, and the
existing lazy probe-phase extraction behavior.

## Verification plan

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_report_evidence_gate.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_report_evidence_gate_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_report_evidence_gate_run_kind_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_report_evidence_gate.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_report_evidence_gate_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_report_evidence_gate_run_kind_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/productization/report_evidence_gate.py services/mlx-worker-python/tests/test_report_evidence_gate.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/report_evidence_gate_run_kind_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" MELIX_REPORT_EVIDENCE_GATE_REPO_ROOT="$PWD" uv run --project services/mlx-worker-python python3 scripts/report_evidence_gate_run_kind_probe.py
```

## Success criteria

- Focused report evidence gate tests pass.
- Changed-scope coverage for the touched files stays at or above the repository
  threshold.
- The registered probe reports a lower `matrix_roles_elapsed_ms_mean` on the
  synthetic release matrix role workload without introducing regressions in
  adjacent report evidence gate metrics.
