# Agentic Evaluation Trajectory Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `EvaluationCore` so evaluation samples with deterministic `tool_calls` execute their tool trajectory before final model generation and scoring.

**Architecture:** `EvaluationCore` already executes deterministic tool calls and persists registry, call, observation, and metric evidence. This change reuses `AgenticToolRun.trace_turns`, projects each trace turn into text-only `ChatMessage` entries, and appends those entries after the scored sample prompt so the final model response is generated with the executed observations in context. Sample evidence persistence remains unchanged and continues to be the metrics source of truth.

**Tech Stack:** Python worker, protobuf `ChatMessage`/`MessagePart`, deterministic agentic tool runtime, pytest, coverage.py.

---

## Files

- Modify: `services/mlx-worker-python/worker/engine/evaluation_core.py`
  - Capture `AgenticToolRun.trace_turns` after deterministic tool execution.
  - Add a small helper that converts trace dictionaries into `ChatMessage` values with compact JSON payloads.
  - Append converted trace messages to `_evaluation_messages(...)`.
- Modify: `services/mlx-worker-python/tests/test_evaluation_core.py`
  - Add a focused regression test proving executed tool-call and observation turns are present in the live prompt before generation.
- Modify: `infra/perf/pr_scoped_probes.json`
  - Add the trajectory regression test to evaluation PR-scoped performance probe verification so direct probes cover this changed scope.
- Modify: `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
  - Lock the evaluation probe verification commands to include the trajectory regression test.
- Modify: `docs/benchmark-evaluation-contract.md`
  - Document that agentic evaluation execution replays deterministic trajectories into the final generation context and records the existing tool metrics.

## Task 1: Add A Failing Trajectory Prompt Test

- [x] **Step 1: Write the failing test**

Add `test_run_local_suite_injects_agentic_tool_trace_before_scoring` near `test_run_local_suite_persists_agentic_tool_evidence` in `services/mlx-worker-python/tests/test_evaluation_core.py`.

The test should:

- materialize one text evaluation sample with `tool_calls` using the built-in `visit` tool,
- run with a loaded text model through `EvaluationCore.run_local_suite(...)`,
- inspect `ScriptedComparisonRuntime.prompts[0]`,
- assert the prompt contains `Agentic tool call`, the call id, `Agentic tool observation`, the observation status, and the deterministic page text before scoring.

Expected failing assertion before implementation: the prompt only contains the system instruction and user prompt, not the executed tool trace.

- [x] **Step 2: Run the focused test to verify RED**

Run:

```bash
uv run pytest services/mlx-worker-python/tests/test_evaluation_core.py::test_run_local_suite_injects_agentic_tool_trace_before_scoring -q
```

Expected: FAIL because the prompt is missing the agentic tool trace text.

Observed on 2026-05-21:

```text
AssertionError: assert 'Agentic tool call:' in 'Return only the final short answer. Do not include reasoning or explanation.\nWhich codename appears in the source?'
```

## Task 2: Inject Executed Trajectory Turns Into Evaluation Messages

- [x] **Step 1: Implement the minimal production change**

In `services/mlx-worker-python/worker/engine/evaluation_core.py`:

- initialize `agentic_tool_trace_turns: tuple[dict[str, object], ...] = ()`,
- assign it from `tool_run.trace_turns`,
- pass it to `_evaluation_messages(...)`,
- add `agentic_trace_turns` as an optional `_evaluation_messages(...)` argument,
- append `_agentic_trace_messages(agentic_trace_turns)` after the final user message,
- add `_agentic_trace_messages(...)` and `_compact_json_text(...)`.

The helper should format two deterministic text message types:

- assistant trace turn:

```text
Agentic tool call: {"arguments":{...},"id":"...","name":"..."}
```

- tool trace turn:

```text
Agentic tool observation: {"observation":{...},"tool_call_id":"..."}
```

Use `json.dumps(..., sort_keys=True, ensure_ascii=False, separators=(",", ":"))` so prompts and tests are stable.

- [x] **Step 2: Run the focused test to verify GREEN**

Run:

```bash
uv run pytest services/mlx-worker-python/tests/test_evaluation_core.py::test_run_local_suite_injects_agentic_tool_trace_before_scoring -q
```

Expected: PASS.

Observed on 2026-05-21:

```text
1 passed in 0.38s
```

## Task 3: Update The Evaluation Contract

- [x] **Step 1: Document execution behavior**

Update `docs/benchmark-evaluation-contract.md` under `Agentic Multimodal Sample Field Contract` with a short subsection explaining:

- samples with `tool_calls` replay those calls through the unified deterministic agentic tool runtime before live model inference,
- the resulting assistant/tool trace turns are appended to the evaluation prompt before final generation and scoring,
- existing `agentic_tool.*` metrics remain the measurement points for call count, status count, observation bytes, and tool latency.

- [x] **Step 2: Run documentation diff check**

Run:

```bash
git diff --check
```

Expected: no whitespace errors.

Observed on 2026-05-21: `git diff --check` exited 0.

## Task 4: Verify Changed Scope And Commit

- [x] **Step 1: Run focused EvaluationCore tests**

Run:

```bash
uv run pytest services/mlx-worker-python/tests/test_evaluation_core.py -q
```

Expected: all tests in the file pass.

Observed on 2026-05-21:

```text
98 passed in 18.41s
```

- [x] **Step 2: Run changed-line coverage**

Run the repository changed-line coverage command for the touched Python scope. If no existing wrapper applies, use `coverage run` for the focused test file and compute changed-line coverage for `evaluation_core.py` plus the touched tests.

Expected: at least 95 percent coverage for changed lines.

Observed on 2026-05-21:

```text
TOTAL 37 0 100%
```

- [x] **Step 3: Fix PR-scoped performance probe verification**

The pre-commit performance report initially failed with `Status: verification_failed` because the selected evaluation probes reused narrow focused coverage commands that did not include the new trajectory execution regression test.

Add `test_run_local_suite_injects_agentic_tool_trace_before_scoring` to the relevant evaluation probe `test_command` and `coverage_command` entries in `infra/perf/pr_scoped_probes.json`, and add a registry regression test that requires those commands to keep covering the trajectory execution path.

Observed RED on 2026-05-21:

```text
FAILED test_evaluation_probe_commands_cover_agentic_trajectory_execution
assert 'services/mlx-worker-python/tests/test_evaluation_core.py::test_run_local_suite_injects_agentic_tool_trace_before_scoring' in probe.test_command
```

Observed GREEN on 2026-05-21:

```text
1 passed in 0.03s
```

- [x] **Step 4: Re-run changed-scope coverage after probe registry update**

Run the focused changed-scope coverage command in a pre-commit-equivalent head snapshot so staged changes are visible to `scripts/changed_scope_coverage.py`.

Expected: at least 95 percent coverage for changed lines.

Observed on 2026-05-21:

```text
3 passed in 2.50s
TOTAL 45 0 100%
```

- [x] **Step 5: Run Python worker test gate**

Run:

```bash
make py-test
```

Expected: all Python tests pass.

Observed on 2026-05-21:

```text
2946 passed, 14 skipped, 2 warnings in 134.61s
```

- [ ] **Step 6: Commit the implementation**

Stage only the plan, docs, implementation, and test files. Commit with:

```bash
git commit -m "feat: execute agentic evaluation trajectories"
```

Include verification and metrics in the commit context and later PR evidence.
