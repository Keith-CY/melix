# Agentic Evaluation Judge Audit Artifacts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the issue #722 audit artifact slice for agentic evaluation suites: judge prompt snapshots and judge audit JSONL rows.

**Architecture:** Agentic multimodal evaluation already executes deterministic tool trajectories and persists self-contained sample rows. This slice adds additive run artifacts for agentic suites, leaving final-result scorer dispatch unchanged. The prompt snapshot records the stable judge instruction, rubric, prompt hash, suite context, and per-sample prompt payload that a later judge-backed scorer can replay. The judge audit JSONL records one row per selected sample with the exact sample answer/evidence boundary and current deterministic exact-match score. No remote judge call is introduced in this unit.

**Tech Stack:** Python worker evaluation core, evaluation artifact persistence, pytest, coverage.py.

---

## Scope

This plan covers issue #722, milestone 3 unit 1 under the OpenSearch-VL alignment agentic multimodal evaluation suite work.

In scope:

- Detect agentic evaluation suites through the manifest `agentic_suite_family` field.
- Write `agentic-judge-prompt-snapshots.jsonl` under the evaluation run root for agentic suites.
- Write `agentic-judge-audit.jsonl` under the evaluation run root for agentic suites.
- Store artifact paths, judge prompt version, and judge prompt hash in evaluation job parameters.
- Include persisted artifact paths in run evidence when the job is persisted under `jobs_root`.
- Add focused tests for the artifact contract and persistence behavior.
- Keep evaluation PR-scoped performance probes covering the agentic artifact regression.

Out of scope:

- Calling a remote or local LLM judge.
- Changing final-result scorer dispatch, exact-match score semantics, thresholds, or summary metrics.
- Adding no-leak enforcement beyond the explicit artifact boundary; that is the next milestone unit.
- Changing event extraction semantic judge artifacts.

## Files

- Modify: `docs/benchmark-evaluation-contract.md`
  - Document the agentic judge prompt snapshot and audit JSONL contract.
- Modify: `services/mlx-worker-python/worker/engine/evaluation_core.py`
  - Add stable agentic judge prompt constants and helpers.
  - Write prompt snapshot and audit rows for agentic suites after sample scoring.
  - Attach artifact paths and prompt metadata to job parameters and persisted path maps.
- Modify: `services/mlx-worker-python/worker/productization/evaluation_store.py`
  - Include agentic judge artifact paths from job parameters in run evidence.
- Modify: `services/mlx-worker-python/tests/test_evaluation_core.py`
  - Add a focused regression test for agentic judge prompt snapshot and audit artifacts.
- Modify: `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
  - Require evaluation probe commands to include the new regression tests.
- Modify: `services/mlx-worker-python/tests/test_evaluation_store.py`
  - Cover extra artifact path inclusion in run evidence.
- Modify: `infra/perf/pr_scoped_probes.json`
  - Include the new artifact regression tests in evaluation probe commands.

## Task 1: Add Contract And RED Tests

- [x] Document the artifact schema and current no-remote-judge behavior.
- [x] Add a focused `EvaluationCore` test that runs an agentic suite and asserts:
  - `agentic_judge_prompt_snapshot` points to `agentic-judge-prompt-snapshots.jsonl`
  - `agentic_judge_audit` points to `agentic-judge-audit.jsonl`
  - the snapshot row includes prompt version/hash, suite id, sample id, rubric, and prompt messages
  - the audit row includes score, final answer, parse status, prompt hash, status, and no API key/base URL material
- [x] Run the focused test and capture the RED failure.

Observed RED on 2026-05-21:

```text
KeyError: 'agentic_judge_prompt_snapshot'
```

## Task 2: Write Agentic Judge Artifacts

- [x] Add stable prompt version/hash constants for agentic answer-equivalence judging.
- [x] Add helper functions to build per-sample prompt snapshot and audit rows.
- [x] Write the artifact JSONL files only for agentic suites.
- [x] Attach paths and prompt metadata to `job_parameters` before job construction.
- [x] Attach the extra artifacts to `persisted_paths` before run evidence is written.
- [x] Run the focused tests and verify they pass.

Observed GREEN on 2026-05-21:

```text
1 passed in 0.33s
```

## Task 3: Update Probe Coverage

- [x] Add the regression test to evaluation PR-scoped probe commands.
- [x] Update the probe registry test so future probe edits keep the new artifact test covered.
- [x] Run the focused probe-registry verification.

Observed on 2026-05-21:

```text
python3 -m json.tool infra/perf/pr_scoped_probes.json >/dev/null
1 passed in 0.20s
```

Initial pre-commit verification on 2026-05-21 failed before commit because the
probe registry covered the first judge artifact regression test but omitted the
no-`jobs_root` artifact-return branch and the evaluation-store extra-artifact
evidence branch from changed-scope coverage replay commands. The registry now
includes both regressions in the relevant evaluation probes.

## Task 4: Verify, Commit, And Open PR

- [x] Run focused evaluation tests.
- [x] Run changed-scope coverage and record the coverage percentage.
- [x] Run `git diff --check`.
- [x] Run the relevant Python gate.
- [ ] Commit the focused slice.
- [ ] Open a PR that closes #722 and monitor review, CI, and the PR performance report until terminal.

Observed on 2026-05-21:

```text
7 passed in 0.65s
TOTAL 100.00% 139/139
git diff --check exited 0
6 passed, 96 deselected in 0.57s
120 passed in 17.95s
make py-test: 2951 passed, 14 skipped, 2 warnings in 128.10s
3 passed in 0.36s
TOTAL 100.00% 161/161
```
