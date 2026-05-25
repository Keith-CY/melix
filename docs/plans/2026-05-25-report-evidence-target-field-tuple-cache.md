# Report evidence target-field tuple cache

## Scope

This Python-only performance slice is limited to release evidence matrix rule
matching in `services/mlx-worker-python/worker/productization/report_evidence_gate.py`.

The optimization preserves existing report-evidence semantics while reusing the
existing tuple-normalization cache for tuple-valued `target_fields` rules. It
keeps mutable non-tuple inputs uncached so list/set-style rule updates continue
to be reflected on the next match.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe
`report-evidence-gate-run-kind-set-membership` in
`infra/perf/pr_scoped_probes.json`.

This slice extends the existing focused probe and registry metrics with a
`target_fields` workload so the changed path has local Linux and CI-visible
performance evidence. The registry entry continues to provide focused
`test_command`, `coverage_command`, and `probe_command` entries for the touched
worker path, tests, and probe script.

## Plan

1. Add regression tests proving tuple-valued target-field rules reuse the cached
   tuple normalization while mutable list rules still reflect mutation.
2. Replace per-call `tuple(str(...))` materialization for target fields with the
   existing `_string_tuple()` helper.
3. Extend the registered report-evidence probe with target-field timing metrics.
4. Run focused pytest, changed-scope coverage, and the registered probe locally
   on Linux before opening the PR.
5. Use GitHub Actions and the registered PR-scoped performance report as the
   merge gate.

## Verification

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_report_evidence_gate.py::test_report_evidence_gate_run_kind_rules_accept_non_tuple_iterables services/mlx-worker-python/tests/test_report_evidence_gate.py::test_report_evidence_gate_run_kind_tuple_rules_reuse_normalized_set services/mlx-worker-python/tests/test_report_evidence_gate.py::test_report_evidence_gate_metric_prefix_tuple_rules_reuse_normalized_tuple services/mlx-worker-python/tests/test_report_evidence_gate.py::test_report_evidence_gate_metric_prefix_list_rules_reflect_mutation services/mlx-worker-python/tests/test_report_evidence_gate.py::test_report_evidence_gate_target_field_tuple_rules_reuse_normalized_tuple services/mlx-worker-python/tests/test_report_evidence_gate.py::test_report_evidence_gate_target_field_list_rules_reflect_mutation services/mlx-worker-python/tests/test_report_evidence_gate.py::test_report_evidence_gate_target_field_preserves_stringified_presence services/mlx-worker-python/tests/test_report_evidence_gate.py::test_report_evidence_gate_run_kind_list_rules_reflect_mutation services/mlx-worker-python/tests/test_report_evidence_gate.py::test_report_evidence_gate_passes_complete_release_matrix services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_report_evidence_gate_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_report_evidence_gate_run_kind_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_report_evidence_gate.py::test_report_evidence_gate_run_kind_rules_accept_non_tuple_iterables services/mlx-worker-python/tests/test_report_evidence_gate.py::test_report_evidence_gate_run_kind_tuple_rules_reuse_normalized_set services/mlx-worker-python/tests/test_report_evidence_gate.py::test_report_evidence_gate_metric_prefix_tuple_rules_reuse_normalized_tuple services/mlx-worker-python/tests/test_report_evidence_gate.py::test_report_evidence_gate_metric_prefix_list_rules_reflect_mutation services/mlx-worker-python/tests/test_report_evidence_gate.py::test_report_evidence_gate_target_field_tuple_rules_reuse_normalized_tuple services/mlx-worker-python/tests/test_report_evidence_gate.py::test_report_evidence_gate_target_field_list_rules_reflect_mutation services/mlx-worker-python/tests/test_report_evidence_gate.py::test_report_evidence_gate_target_field_preserves_stringified_presence services/mlx-worker-python/tests/test_report_evidence_gate.py::test_report_evidence_gate_run_kind_list_rules_reflect_mutation services/mlx-worker-python/tests/test_report_evidence_gate.py::test_report_evidence_gate_passes_complete_release_matrix services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_report_evidence_gate_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_report_evidence_gate_run_kind_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/productization/report_evidence_gate.py services/mlx-worker-python/tests/test_report_evidence_gate.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/report_evidence_gate_run_kind_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" MELIX_REPORT_EVIDENCE_GATE_REPO_ROOT="$PWD" uv run --project services/mlx-worker-python python3 scripts/report_evidence_gate_run_kind_probe.py
```
