# Report evidence probe-phase tuple cache

## Scope

This Python-only performance slice is limited to release evidence matrix rule
matching in `services/mlx-worker-python/worker/productization/report_evidence_gate.py`.

The optimization preserves existing release-matrix semantics while reusing the
existing tuple-normalization cache for tuple-valued `probe_phases` rules. Mutable
non-tuple inputs remain uncached so list/set-style rule updates continue to be
reflected on the next match.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe
`report-evidence-gate-run-kind-set-membership` in
`infra/perf/pr_scoped_probes.json`.

The registry entry already provides focused `test_command`, `coverage_command`,
and `probe_command` entries for the touched worker path. To avoid mixing probe
registration with the runtime optimization, this slice keeps the registered
probe definition stable and uses an additional local same-script microbenchmark
for the tuple-valued `probe_phases` path.

## Plan

1. Add regression tests proving tuple-valued probe-phase rules reuse the cached
   normalized set while mutable list rules still reflect mutation.
2. Replace per-call `set(str(...))` materialization for probe phases with the
   existing `_string_frozenset()` helper.
3. Keep the registered report-evidence probe stable and use it as the CI guard.
4. Run focused pytest, changed-scope coverage, the registered probe, and a
   local same-script probe-phase microbenchmark on Linux before opening the PR.
5. Use GitHub Actions and the registered PR-scoped performance report as the
   merge gate.

## Verification

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_report_evidence_gate.py::test_report_evidence_gate_run_kind_rules_accept_non_tuple_iterables services/mlx-worker-python/tests/test_report_evidence_gate.py::test_report_evidence_gate_run_kind_tuple_rules_reuse_normalized_set services/mlx-worker-python/tests/test_report_evidence_gate.py::test_report_evidence_gate_metric_prefix_tuple_rules_reuse_normalized_tuple services/mlx-worker-python/tests/test_report_evidence_gate.py::test_report_evidence_gate_metric_prefix_list_rules_reflect_mutation services/mlx-worker-python/tests/test_report_evidence_gate.py::test_report_evidence_gate_target_field_tuple_rules_reuse_normalized_tuple services/mlx-worker-python/tests/test_report_evidence_gate.py::test_report_evidence_gate_target_field_list_rules_reflect_mutation services/mlx-worker-python/tests/test_report_evidence_gate.py::test_report_evidence_gate_target_field_preserves_stringified_presence services/mlx-worker-python/tests/test_report_evidence_gate.py::test_report_evidence_gate_probe_phase_tuple_rules_reuse_normalized_set services/mlx-worker-python/tests/test_report_evidence_gate.py::test_report_evidence_gate_probe_phase_list_rules_reflect_mutation services/mlx-worker-python/tests/test_report_evidence_gate.py::test_report_evidence_gate_run_kind_list_rules_reflect_mutation services/mlx-worker-python/tests/test_report_evidence_gate.py::test_report_evidence_gate_passes_complete_release_matrix services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_report_evidence_gate_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_report_evidence_gate_run_kind_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_report_evidence_gate.py::test_report_evidence_gate_run_kind_rules_accept_non_tuple_iterables services/mlx-worker-python/tests/test_report_evidence_gate.py::test_report_evidence_gate_run_kind_tuple_rules_reuse_normalized_set services/mlx-worker-python/tests/test_report_evidence_gate.py::test_report_evidence_gate_metric_prefix_tuple_rules_reuse_normalized_tuple services/mlx-worker-python/tests/test_report_evidence_gate.py::test_report_evidence_gate_metric_prefix_list_rules_reflect_mutation services/mlx-worker-python/tests/test_report_evidence_gate.py::test_report_evidence_gate_target_field_tuple_rules_reuse_normalized_tuple services/mlx-worker-python/tests/test_report_evidence_gate.py::test_report_evidence_gate_target_field_list_rules_reflect_mutation services/mlx-worker-python/tests/test_report_evidence_gate.py::test_report_evidence_gate_target_field_preserves_stringified_presence services/mlx-worker-python/tests/test_report_evidence_gate.py::test_report_evidence_gate_probe_phase_tuple_rules_reuse_normalized_set services/mlx-worker-python/tests/test_report_evidence_gate.py::test_report_evidence_gate_probe_phase_list_rules_reflect_mutation services/mlx-worker-python/tests/test_report_evidence_gate.py::test_report_evidence_gate_run_kind_list_rules_reflect_mutation services/mlx-worker-python/tests/test_report_evidence_gate.py::test_report_evidence_gate_passes_complete_release_matrix services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_report_evidence_gate_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_report_evidence_gate_run_kind_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/productization/report_evidence_gate.py services/mlx-worker-python/tests/test_report_evidence_gate.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/report_evidence_gate_run_kind_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" MELIX_REPORT_EVIDENCE_GATE_REPO_ROOT="$PWD" uv run --project services/mlx-worker-python python3 scripts/report_evidence_gate_run_kind_probe.py
```
