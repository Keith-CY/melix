# Phase 8 Release Gate Evidence Repair Plan

## Goal

Restore the `release-gates` workflow on `main` by making the deterministic
Phase 8 gate emit complete release-owned evidence in clean CI workspaces.

## Diagnosis

The README `release gates` badge was reporting a real workflow failure after
the workflow was re-enabled. The Phase 8 gate failed closed because a clean
release-gate workspace had no persisted evidence for selected compare suites,
real-workload family receipts, or the Gemma E4B profile gate.

The standalone collectors should keep failing closed when those artifacts are
missing. The issue is that the full release-gate command owns a deterministic
release run and should prepare its own release evidence before evaluating the
policy.

## Scope

- Prepare release-owned evaluation-compare evidence for selected suites when no
  persisted compare artifact already exists.
- Prepare deterministic real-workload family evidence for the policy-selected
  families when no artifact already exists.
- Prepare deterministic Gemma E4B profile evidence when no artifact already
  exists.
- Preserve fail-closed behavior for standalone collectors that are called
  directly against an empty jobs root.
- Add focused regression coverage proving the full release-gate report prepares
  the evidence it later evaluates.
- Keep the Gemma E4B PR-scoped performance probe's focused test and coverage
  command aligned with the release-gate regression test, because changes in
  `release_gates.py` select that direct probe.

## Verification

- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_release_gates.py::test_build_release_gate_report_prepares_release_owned_evidence services/mlx-worker-python/tests/test_release_gates.py::test_collect_evaluation_compare_evidence_fails_closed_without_persisted_compare_artifacts -q`
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_release_gates.py services/mlx-worker-python/tests/test_gemma_e4b_profile_gate.py -q`
- `make swift-test`
- `make phase8-release-gate PHASE8_RELEASE_GATE_ARGS="--json"`
- Gemma E4B PR-scoped performance probe coverage command from
  `infra/perf/pr_scoped_probes.json`
- `.githooks/pre-commit`
- GitHub Actions `release-gates` on `main` after merge

## Coverage and Metrics

- Coverage: focused release-gate regression coverage in `test_release_gates.py`.
- Metrics: Phase 8 release-gate JSON must report `passed=true`,
  `failure_count=0`, selected evaluation compare verdict `improvement`, real
  workload `family_count=3`, and Gemma E4B profile `passed`.
- Performance: no request-serving runtime path changes. The only added work is
  deterministic evidence preparation inside the release-gate command.
