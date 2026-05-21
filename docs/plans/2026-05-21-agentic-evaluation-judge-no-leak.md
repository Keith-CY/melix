# Agentic Evaluation Judge No-Leak Checks Implementation Plan

**Goal:** Add the issue #723 no-leak contract for agentic evaluation judge prompt
snapshots so hidden gold, answer-key shortcuts, provider configuration, and
credentials cannot enter the judge context beyond the explicit scoring rubric
and expected-answer boundary.

**Architecture:** Agentic multimodal evaluation suites already write audit-only
judge prompt snapshots and judge audit rows after deterministic trajectory
execution. This slice keeps scorer dispatch and remote judge behavior unchanged.
It adds a pre-persistence validator at the judge prompt snapshot boundary. The
validator enforces the supported user payload fields and recursively rejects
forbidden context keys inside sample-derived media refs, raw tool calls, and
executed tool observations before the snapshot JSONL is written.

**Tech Stack:** Python worker evaluation core, evaluation artifact persistence,
pytest, coverage.py, PR-scoped performance probe registry.

---

## Scope

This plan covers issue #723, milestone 3 unit 2 under the OpenSearch-VL
alignment agentic multimodal evaluation suite work.

In scope:

- Define the judge no-leak boundary in the benchmark/evaluation contract.
- Reject unsupported judge user-payload fields before prompt snapshot
  persistence.
- Reject forbidden nested context keys such as hidden gold, answer keys,
  provider credentials, API keys, tokens, passwords, and remote base URLs inside
  the judge user payload.
- Preserve legitimate answer text in `expected_answer`, `final_answer`, and
  executed tool observation values.
- Add focused regression tests for both valid answer-bearing observations and
  hidden-gold/credential key rejection.
- Keep evaluation PR-scoped performance probes covering the no-leak regression.

Out of scope:

- Calling a remote or local LLM judge.
- Changing final-result scorer dispatch, exact-match score semantics,
  thresholds, or summary metrics.
- Scanning arbitrary text values for answer leakage. Dataset construction uses
  the separate `leakage_terms` controls for value-level prompt/trajectory
  leakage.
- Rewriting existing agentic suite fixtures.

## Performance Probes And Success Metrics

Measurement points:

- Existing evaluation PR-scoped probes that watch
  `services/mlx-worker-python/worker/engine/evaluation_core.py`.
- Focused pytest coverage for the judge snapshot no-leak helper and artifact
  path.
- Changed-scope coverage for touched Python lines.

Success metrics:

- The focused no-leak regression passes.
- `infra/perf/pr_scoped_probes.json` remains valid JSON and every evaluation
  probe covering agentic trajectory execution includes the no-leak regression.
- Changed-scope coverage for touched Python lines is at least 95 percent.
- `make py-test` passes before handoff.
- The PR performance report has no direct/gated regression for the touched
  evaluation probes.

## Files

- Modify: `docs/benchmark-evaluation-contract.md`
  - Document the judge no-leak boundary and allowed user payload fields.
- Modify: `services/mlx-worker-python/worker/engine/evaluation_core.py`
  - Add the no-leak validator and call it before prompt snapshot persistence.
- Modify: `services/mlx-worker-python/tests/test_evaluation_core.py`
  - Add focused regression coverage for valid observations and forbidden
    hidden-gold/credential context keys.
- Modify: `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
  - Require evaluation probe commands to include the no-leak regression.
- Modify: `infra/perf/pr_scoped_probes.json`
  - Include the no-leak regression in evaluation probe commands.

## Task 1: Add Contract And RED Tests

- [x] Document the no-leak judge context boundary.
- [x] Add focused tests that fail before implementation:
  - valid observations may contain the expected answer as a value
  - hidden-gold, answer-key, provider credential, API key, token, password, and
    base-url keys are rejected with a field path
- [x] Run the focused tests and capture the RED failure.

Observed RED on 2026-05-21:

```text
Failed: DID NOT RAISE <class 'ValueError'>
```

## Task 2: Implement No-Leak Validation

- [x] Add explicit allowed judge user-payload fields.
- [x] Add normalized forbidden context keys and a recursive key walker.
- [x] Validate the judge user payload before serializing it into `messages`.
- [x] Verify the focused no-leak tests pass.

Observed GREEN on 2026-05-21:

```text
9 passed in 0.26s
```

## Task 3: Update Probe Coverage

- [x] Add the no-leak regression test to evaluation PR-scoped probe commands.
- [x] Update the probe registry test so future probe edits keep the regression
  covered.
- [x] Validate the probe registry JSON and focused registry test.

Observed on 2026-05-21:

```text
python3 -m json.tool infra/perf/pr_scoped_probes.json >/dev/null
1 passed in 0.20s
```

## Task 4: Verify, Commit, And Open PR

- [x] Run focused evaluation tests.
- [x] Run changed-scope coverage and record the coverage percentage.
- [x] Run `git diff --check`.
- [x] Run `make py-test`.
- [ ] Commit the focused slice.
- [ ] Open a PR that closes #723 and monitor review, CI, and the PR performance
  report until terminal.

Observed on 2026-05-21:

```text
10 passed in 0.31s
TOTAL 43 0 100%
git diff --check exited 0
python3 -m json.tool infra/perf/pr_scoped_probes.json >/dev/null exited 0
11 passed in 0.30s
make py-test: 2962 passed, 14 skipped, 2 warnings in 128.31s
```
