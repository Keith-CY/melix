# Issue 1663 Gemma E4B Profile Gate

Date: 2026-06-02

## Context

Issue #1642 tracks the remaining release Gemma E4B serving gap against OMLX
and SwiftLM. The recent child slices added profile proof receipts, same-cohort
batching evidence, batch metric attribution, output overhead counters, and
worker prefill-window metrics. Issue #1663 is the release boundary that prevents
Gemma E4B serving profile selection from promoting optimistic acceleration
defaults without matching capability and benchmark evidence.

The existing control plane already emits capability and profile admission
metadata for request dispatch:

- `melix.acceleration.requested_acceleration_mode`
- `melix.acceleration.resolved_acceleration_mode`
- `melix.acceleration.unsupported_reason`
- `melix.acceleration.profile.requested_profile`
- `melix.acceleration.profile.effective_profile`
- `melix.acceleration.profile.profile_admission_status`
- `melix.acceleration.profile.verification_status`
- `melix.acceleration.profile.proof_matrix_id`

This slice adds a release-gate evaluator that consumes those selected-profile
receipts together with the existing peer benchmark threshold artifact.

## Goal

Make the release benchmark gate fail closed unless the selected Gemma E4B
serving profile has:

1. explicit capability/profile receipt evidence,
2. acceleration mode and batch-size evidence,
3. no selected unsupported acceleration route, and
4. peer benchmark threshold status that passes the current baseline comparison.

## Scope

- Add a productization gate for Gemma E4B profile evidence.
- Load persisted gate evidence from the jobs root when the main release gate
  runs.
- Add a PR-scoped performance probe that exercises the gate with deterministic
  evidence and reports flat metrics.
- Keep the selected profile conservative: unsupported speculative,
  active-KV, sparse, or accelerated-prefill routes must either be refused with a
  reason or remain unselected.
- Reuse the existing OMLX/Melix benchmark threshold semantics:
  total latency must not exceed the best peer by more than 25 percent and
  decode throughput must not fall more than 25 percent below the best peer.

Out of scope:

- Running a live Gemma E4B, OMLX, or SwiftLM benchmark in this slice.
- Promoting speculative decode, active-KV, sparse prefill, or accelerated
  prefill as Gemma E4B defaults.
- Changing the existing request-coordinate capability receipt schema.

## Evidence Contract

The persisted gate input is JSON with schema
`melix.gemma_e4b_profile_gate.v1`. It records:

- `model_id`
- `selected_profile`
  - `requested_profile`
  - `effective_profile`
  - `acceleration_mode`
  - `resolved_acceleration_mode`
  - `prefill_batch_size`
  - `completion_batch_size`
  - `profile_receipt.profile_admission_status`
  - `profile_receipt.verification_status`
  - `profile_receipt.proof_matrix_id`
  - `capability_receipt.state`
  - `capability_receipt.unsupported_reason`
- `unsupported_routes`
  - each experimental or unsupported route and its `status`, `reason`, and
    `selected` flag
- `benchmark`
  - the `comparison_validity` object from the benchmark bundle
  - the `threshold_status` object from the benchmark bundle

## Implementation Steps

1. Add `worker.productization.gemma_e4b_profile_gate`.
   - Normalize gate evidence into flat numeric metrics.
   - Fail when selected-profile receipt fields are missing or rejected.
   - Fail when an unsupported route is selected instead of refused or skipped.
   - Fail when benchmark comparison validity is not valid or threshold status is
     not `ok`.
2. Wire the gate into `release_gates`.
   - Add a default `gemma_e4b_profile` policy.
   - Load persisted evidence from the jobs root.
   - Evaluate the section through the existing release-gate failure surface.
3. Add `scripts/gemma_e4b_profile_gate_probe.py`.
   - Support `--input` for persisted evidence.
   - Support `--metrics` for PR-scoped performance.
   - Use deterministic built-in passing evidence when no input is provided.
4. Register `gemma-e4b-profile-release-gate` in
   `infra/perf/pr_scoped_probes.json`.
5. Verify with focused Python tests, changed-scope coverage, the probe command,
   and the PR-scoped performance report.

## Success Metrics

- `release_gate_passed` is `1.0` only when the selected profile has admitted
  profile receipt evidence, supported capability receipt, explicit batch sizes,
  valid peer comparison metadata, and an `ok` threshold status. Default
  baseline profiles may use `verification_status=not_required`; optimized
  profiles must provide `verification_status=passed` and a proof matrix id.
- `unsupported_selected_route_count` remains `0.0`.
- `benchmark_threshold_failure_count` remains `0.0`.
- The PR-scoped probe emits numeric gate metrics and fails on regressions in
  gate behavior.

## Verification

Focused checks:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q \
  services/mlx-worker-python/tests/test_m9_release_gate_smoke.py \
  services/mlx-worker-python/tests/test_gemma_e4b_profile_gate.py \
  services/mlx-worker-python/tests/test_release_gates.py::test_build_release_gate_report_records_packaged_launch_passed_state \
  services/mlx-worker-python/tests/test_release_gates.py::test_collect_gemma_e4b_profile_gate_evidence_reports_selected_profile \
  services/mlx-worker-python/tests/test_release_gates.py::test_gemma_e4b_profile_gate_fails_closed_for_missing_or_regressed_evidence \
  services/mlx-worker-python/tests/test_release_gates.py::test_build_release_gate_report_includes_m9_summary_when_collectors_pass \
  services/mlx-worker-python/tests/test_release_gates.py::test_build_release_gate_report_passes_with_supplied_recovery_evidence \
  services/mlx-worker-python/tests/test_release_gates.py::test_build_release_gate_report_uses_temp_jobs_root_and_reports_type_errors \
  services/mlx-worker-python/tests/test_release_gates.py::test_default_policy_includes_gemma_e4b_profile_gate \
  services/mlx-worker-python/tests/test_release_gates.py::test_checked_in_release_gate_policy_includes_evaluation_thresholds \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_release_gates_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_gemma_e4b_profile_gate_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_gemma_e4b_profile_gate_probe_script_emits_metrics \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_gemma_e4b_profile_gate_probe_script_main_covers_checked_in_file \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_gemma_e4b_profile_gate_probe_rejects_non_object_input \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run --branch -m pytest -q \
  services/mlx-worker-python/tests/test_m9_release_gate_smoke.py \
  services/mlx-worker-python/tests/test_gemma_e4b_profile_gate.py \
  services/mlx-worker-python/tests/test_release_gates.py::test_build_release_gate_report_records_packaged_launch_passed_state \
  services/mlx-worker-python/tests/test_release_gates.py::test_collect_gemma_e4b_profile_gate_evidence_reports_selected_profile \
  services/mlx-worker-python/tests/test_release_gates.py::test_gemma_e4b_profile_gate_fails_closed_for_missing_or_regressed_evidence \
  services/mlx-worker-python/tests/test_release_gates.py::test_build_release_gate_report_includes_m9_summary_when_collectors_pass \
  services/mlx-worker-python/tests/test_release_gates.py::test_build_release_gate_report_passes_with_supplied_recovery_evidence \
  services/mlx-worker-python/tests/test_release_gates.py::test_build_release_gate_report_uses_temp_jobs_root_and_reports_type_errors \
  services/mlx-worker-python/tests/test_release_gates.py::test_default_policy_includes_gemma_e4b_profile_gate \
  services/mlx-worker-python/tests/test_release_gates.py::test_checked_in_release_gate_policy_includes_evaluation_thresholds \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_release_gates_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_gemma_e4b_profile_gate_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_gemma_e4b_profile_gate_probe_script_emits_metrics \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_gemma_e4b_profile_gate_probe_script_main_covers_checked_in_file \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_gemma_e4b_profile_gate_probe_rejects_non_object_input \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json \
  scripts/m9_release_gate_smoke.py \
  scripts/gemma_e4b_profile_gate_probe.py \
  services/mlx-worker-python/worker/productization/gemma_e4b_profile_gate.py \
  services/mlx-worker-python/worker/productization/release_gates.py \
  services/mlx-worker-python/tests/test_gemma_e4b_profile_gate.py \
  services/mlx-worker-python/tests/test_release_gates.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py

python3 scripts/gemma_e4b_profile_gate_probe.py --metrics
git diff --check
```

Result on 2026-06-02:

- Focused pytest: 32 passed.
- Expanded release-gate pytest after scoped probe repair: 91 passed.
- Changed-line coverage: `TOTAL 0 0 100%`.
- Probe metrics: `release_gate_passed=1.0`,
  `selected_profile_receipt_passed=1.0`,
  `profile_proof_satisfied=1.0`,
  `capability_receipt_supported=1.0`,
  `unsupported_selected_route_count=0.0`,
  `benchmark_threshold_passed=1.0`, and
  `benchmark_threshold_failure_count=0.0`.
- PR-scoped single-probe performance report:
  `gemma-e4b-profile-release-gate` status `ok`, direct gate coverage `98.0%`, no
  regressions, base fallback metrics at `release_gate_passed=0.0` and head
  metrics at `release_gate_passed=1.0`.
- Expanded M9 release-gate scoped coverage after sharing
  `test_release_gates.py`: 70 passed, `TOTAL 0 0 100%`.

The final PR gate must still follow the repository default test, coverage, and
performance-report rules before PR readiness is claimed.
