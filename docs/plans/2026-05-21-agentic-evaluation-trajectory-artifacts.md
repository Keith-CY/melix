# Agentic Evaluation Trajectory Artifacts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist the per-sample trajectory artifact fields required by issue #720: raw tool calls, observations, final answer, parse status, and failure stage.

**Architecture:** `EvaluationCore` already replays deterministic `tool_calls` through the unified agentic tool runtime and stores normalized registry, call, observation, and metric evidence. This slice makes the persisted evaluation sample row self-contained by adding additive `EvaluationSample` fields for the raw input `tool_calls`, the final parsed answer, and the parser status. Existing `agentic_tool_observations` remains the observation evidence field, and existing `failure_stage` remains the failure classification field.

**Tech Stack:** Python worker evaluation schemas, `EvaluationCore`, evaluation store/export artifacts, pytest, coverage.py.

---

## Scope

This plan covers issue #720, milestone 2 unit 2 under the OpenSearch-VL alignment agentic multimodal evaluation suite work.

In scope:

- Persist raw sample `tool_calls` in each evaluation sample JSONL row when present.
- Persist `final_answer` as the extracted final answer used for scoring.
- Persist `parse_status` as the parser/extraction status that produced the final answer.
- Preserve existing `agentic_tool_observations` and `failure_stage` evidence.
- Keep the CSV/export field lists documented for the added scalar fields.
- Keep the evaluation PR-scoped performance probes covering the trajectory artifact regression.

Out of scope:

- Changing deterministic tool execution semantics.
- Adding new judge-backed metrics.
- Changing scorer dispatch or score thresholds.
- Adding a separate report artifact beyond the existing sample JSONL/CSV/export paths.

## Files

- Modify: `services/mlx-worker-python/worker/productization/evaluation_schemas.py`
  - Add additive `tool_calls`, `final_answer`, and `parse_status` fields to `EvaluationSample`.
  - Include those fields in `to_dict()` and `build_evaluation_sample_record(...)`.
- Modify: `services/mlx-worker-python/worker/engine/evaluation_core.py`
  - Preserve raw sample `tool_calls` before deterministic replay.
  - Pass `final_answer` and `parse_status` through successful and unsupported offline sample records.
- Modify: `services/mlx-worker-python/worker/productization/evaluation_store.py`
  - Add scalar artifact fields to the sample CSV header and row.
- Modify: `services/mlx-worker-python/worker/productization/benchmark_export.py`
  - Keep export sample normalization and canonical columns aware of the additive scalar fields.
- Modify: `services/mlx-worker-python/tests/test_evaluation_core.py`
  - Add a focused regression test for persisted agentic trajectory artifact fields.
- Modify: `services/mlx-worker-python/tests/test_evaluation_schemas.py`
  - Lock schema serialization for the additive fields.
- Modify: `infra/perf/pr_scoped_probes.json`
  - Include the trajectory artifact regression in evaluation probe commands.
- Modify: `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
  - Require selected evaluation probes to keep covering trajectory artifact persistence.
- Modify: `docs/benchmark-evaluation-contract.md`
  - Document the self-contained per-sample trajectory artifact fields.

## Task 1: Add Failing Artifact Persistence Tests

- [x] Add `EvaluationSample` serialization coverage for `tool_calls`, `final_answer`, and `parse_status`.
- [x] Add an `EvaluationCore` test that runs one sample with deterministic `tool_calls` and asserts the persisted `evaluation-samples.jsonl` row includes:
  - raw `tool_calls`
  - `agentic_tool_observations`
  - `final_answer`
  - `parse_status`
  - `failure_stage`
- [x] Run the focused tests and verify they fail before implementation.

Observed RED on 2026-05-21:

```text
FAILED test_build_evaluation_sample_record_preserves_agentic_tool_evidence
TypeError: build_evaluation_sample_record() got an unexpected keyword argument 'tool_calls'

FAILED test_run_local_suite_persists_agentic_tool_evidence
AttributeError: 'EvaluationSample' object has no attribute 'tool_calls'
```

## Task 2: Persist Additive Sample Fields

- [x] Add the schema fields and builder parameters.
- [x] Pass raw tool calls, final answer, and parse status from `EvaluationCore`.
- [x] Add scalar CSV/export fields without changing existing field names.
- [x] Run focused tests and verify they pass.

Observed GREEN on 2026-05-21:

```text
2 passed in 0.37s
10 passed in 0.03s
```

## Task 3: Update Contract And Probe Coverage

- [x] Document the per-sample artifact fields in `docs/benchmark-evaluation-contract.md`.
- [x] Add the artifact regression test to evaluation PR-scoped probe commands.
- [x] Update the probe registry test to require that regression.
- [x] Run focused probe-registry verification.

Observed on 2026-05-21:

```text
python3 -m json.tool infra/perf/pr_scoped_probes.json >/dev/null
1 passed in 0.22s
```

## Task 4: Verify, Commit, And Open PR

- [x] Run focused evaluation/schema tests.
- [x] Run changed-scope coverage and record the coverage percentage.
- [x] Run `git diff --check`.
- [x] Run the relevant Python gate.
- [x] Commit the focused slice.
- [ ] Open a PR that closes #720 and monitor review, CI, and the PR performance report until terminal.

Observed on 2026-05-21:

```text
200 passed in 17.87s
TOTAL 30 0 100%
git diff --check exited 0
make py-test: 2947 passed, 14 skipped, 2 warnings in 129.04s
```

Commit completed on 2026-05-21:

```text
0dac9692 feat: persist agentic evaluation trajectory artifacts
```

Pre-commit verification on 2026-05-21:

```text
make swift-test: passed
make py-test: 2947 passed, 14 skipped, 2 warnings
make integration-test: 114 passed, 1 skipped
PR scoped performance report: Status ok, direct/gated regressions 0, context regressions 7
```

Pre-commit performance follow-up on 2026-05-21:

```text
Initial commit attempt blocked on direct probe:
Evaluation store samples CSV streaming elapsed_ms_mean +5.22%

After CSV hot-path optimization:
evaluation-store-samples-csv-streaming head verification: 9 passed, TOTAL 0 0 100%
base elapsed_ms_mean 1068.864820
head elapsed_ms_mean 1106.996416
delta +3.57%, below the 5% regression gate
```
