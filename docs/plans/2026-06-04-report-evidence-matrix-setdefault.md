# Report evidence matrix evidence-set reuse

## Scope

This Python-only performance slice is limited to release evidence matrix row
construction in `services/mlx-worker-python/worker/productization/report_evidence_gate.py`.

The optimization preserves existing release-matrix semantics while avoiding a
throwaway `set()` allocation on every repeated role update. The first evidence
hit for a role still materializes a set from the report evidence IDs; subsequent
hits update the existing set directly.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe
`report-evidence-gate-run-kind-set-membership` in
`infra/perf/pr_scoped_probes.json`.

The registry entry already provides focused `test_command`, `coverage_command`,
and `probe_command` entries for the touched worker path. This slice keeps the
probe definition stable and uses the registered probe locally on Linux before
opening the PR. CI remains the final base-vs-head validation source.

## Plan

1. Reuse the existing report-evidence matrix tests that cover role aggregation,
   evidence ID de-duplication, and invalid-role filtering.
2. Replace `setdefault(..., set()).update(...)` with an explicit get/first-set
   path so repeated role updates do not allocate unused empty sets.
3. Run focused pytest, changed-scope coverage, and the registered probe locally
   on Linux before creating the PR.
4. Use GitHub Actions and the registered PR-scoped performance report as the
   merge gate.

## Verification

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_report_evidence_gate.py::test_report_evidence_gate_passes_complete_release_matrix services/mlx-worker-python/tests/test_report_evidence_gate.py::test_report_evidence_gate_release_matrix_dedupes_evidence_ids services/mlx-worker-python/tests/test_report_evidence_gate.py::test_report_evidence_gate_release_matrix_ignores_invalid_cached_roles services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_report_evidence_gate_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_report_evidence_gate_run_kind_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_report_evidence_gate.py::test_report_evidence_gate_passes_complete_release_matrix services/mlx-worker-python/tests/test_report_evidence_gate.py::test_report_evidence_gate_release_matrix_dedupes_evidence_ids services/mlx-worker-python/tests/test_report_evidence_gate.py::test_report_evidence_gate_release_matrix_ignores_invalid_cached_roles services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_report_evidence_gate_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_report_evidence_gate_run_kind_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/productization/report_evidence_gate.py services/mlx-worker-python/tests/test_report_evidence_gate.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/report_evidence_gate_run_kind_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" MELIX_REPORT_EVIDENCE_GATE_REPO_ROOT="$PWD" uv run --project services/mlx-worker-python python3 scripts/report_evidence_gate_run_kind_probe.py
```
