# LoRA Release Gate Verdict Policy

## Goal

Complete issue #732 by making the Phase 8 release gate enforce the compare
verdict policy for every selected LoRA release suite.

Parent direction: issue #724, "OpenSearch-VL alignment: gate LoRA release with
paired compare evidence". Milestone direction: issue #731, "enforce
release-gate verdicts".

## Current Shipped Surface

- `eval compare` persists per-suite paired compare evidence with release
  verdicts.
- The Phase 8 release-gate policy has an `evaluation_compare` suite map.
- The current gate can fail a single suite when its verdict does not exactly
  match `required_verdict`.

## Gap

The policy map cannot yet express mixed release intent across selected suites:

- target-domain suites should require a statistically supported `improvement`
- guard suites should require `non_regression`, meaning `regression` is
  blocking while an `improvement`, `inconclusive`, or tie-like neutral verdict
  remains acceptable

The collector also only loads one preferred compare suite, so a multi-suite
policy does not fail closed when another selected suite is missing.

## Scope

This slice adds a backward-compatible compare verdict policy mode:

- keep `required_verdict` for exact verdict requirements
- add `required_verdict_mode: non_regression` for guard suites
- treat each suite key under `evaluation_compare` as selected release evidence
- collect persisted compare evidence for every selected suite
- fail closed when a selected suite is missing, malformed, regressed, or does
  not satisfy its policy mode
- document the policy modes in the benchmark/evaluation contract and release
  gate runbook

Out of scope:

- adding the human report grouping requested by issue #733
- changing statistical verdict derivation
- changing compare execution
- changing protobuf schemas

## Performance And Metrics

The implementation adds bounded policy iteration over selected suite ids and
reads the same persisted compare artifacts already scanned by the release gate.
It must not add model execution, dataset materialization, or statistical
resampling.

Measurement points:

- focused release-gate tests for single-suite compatibility, multi-suite
  selected evidence, missing selected suite evidence, and non-regression verdict
  mode
- `git diff --check`
- changed-scope coverage for modified Python executable files
- PR-scoped performance report; this code path is release-gate focused, so a
  release-gate probe may be selected and must remain non-regressing

Success metrics:

- policies with one `evaluation_compare` suite preserve the existing report
  shape
- policies with multiple selected suites emit one release-gate evidence object
  per suite
- `required_verdict_mode: non_regression` rejects `regression` and missing
  verdicts, but accepts `improvement`, `inconclusive`, and `tie`
- changed-scope coverage for modified executable Python files is at least 95
  percent before handoff

## Implementation Plan

- [x] Update this plan and the governing contracts before broad code changes.
- [x] Extend the release-gate collector to gather every selected compare suite.
- [x] Extend evaluation compare policy enforcement with verdict modes.
- [x] Update tests for exact improvement and non-regression suite policies.
- [x] Run focused verification and changed-scope coverage.

## Verification

- `python3 -m py_compile services/mlx-worker-python/worker/productization/release_gates.py services/mlx-worker-python/tests/test_release_gates.py`
  - Result: passed.
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_release_gates.py -k "evaluation_compare or evaluation_section or release_gate_fails_on_compare"`
  - Result: 16 passed, 47 deselected.
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python coverage run --data-file=/tmp/lora_release_gate_verdict_policy.coverage -m pytest -q services/mlx-worker-python/tests/test_release_gates.py`
  - Result: 64 passed.
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python python scripts/changed_scope_coverage.py --coverage-json /tmp/lora_release_gate_verdict_policy_coverage.json services/mlx-worker-python/worker/productization/release_gates.py`
  - Result: `TOTAL 69 2 97%`.
- `git diff --check`
  - Result: passed.
- Local PR-scoped performance via `scripts.pre_commit_gate.run_performance_report(...)` against `origin/main`
  - Result: generated `.runtime/pre-commit-performance/20260521-200743-ce9e3421/report/report.md` with `Status: ok`, 2 selected direct probes, 0 regressions, 0 verification failures.
  - Note: the wrapper command exited non-zero after report generation because it attempted to read a nonexistent `PerformanceOutcome.ok` attribute. The generated report and probe JSON are the performance evidence.
- Current local disk state during verification:
  - `df -h .`: about 3.2 GiB available, so full local Swift rebuild gates are high risk on this host.
