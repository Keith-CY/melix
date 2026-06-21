# Issue 1387 Agent Reliability Track Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a first repository-owned agent reliability benchmark/evaluation track with guardrail ablations, stateful scenario validation, resumable JSONL rows, and Markdown/JSON summaries.

**Architecture:** Keep the first slice in the Python worker productization layer so it can reuse existing deterministic agentic tool contracts and export/report conventions without changing the public Swift CLI in the same PR. A new `agent_reliability` module owns scenario loading, ablation preset expansion, deterministic execution, resume handling, aggregation, and report rendering. A small script exposes the runner for local evidence. Checked-in fixture scenarios prove stateful validation and wrong-argument failure behavior.

**Tech Stack:** Python dataclasses, JSON/JSONL fixtures, deterministic pytest coverage, `services/mlx-worker-python` productization modules, repository docs under `docs/benchmark-evaluation-contract.md`.

---

## Scope

In scope for this PR:

- Guardrail ablation preset expansion for:
  - `baseline`
  - `no_response_rescue`
  - `no_retry_nudges`
  - `no_step_enforcement`
  - `no_tool_error_recovery`
  - `no_context_compaction`
  - `all_guardrails_disabled`
- Scenario tags for plumbing, model quality, advanced reasoning, compaction pressure, stateful behavior, and error recovery.
- Stateful deterministic scenario execution where final validation checks both model-facing output and backend state changes.
- Metrics for accuracy, completeness, wasted tool calls, retry count, nudge count, validation errors, compaction events, elapsed time, and token/cost estimates when supplied.
- Resumable JSONL rows keyed by model/backend/profile/ablation/scenario.
- Markdown and JSON summaries with per-ablation deltas for completion and wasted calls.
- Docs describing artifact shape and first-slice command usage.

Out of scope for this PR:

- Public Swift `melix bench` or `melix eval` command surface.
- Public leaderboard or community submissions.
- Live model/provider execution.
- Replacing existing benchmark/eval commands or artifacts.

## Files

- Create: `services/mlx-worker-python/worker/productization/agent_reliability.py`
  - Own schemas, preset expansion, scenario loading, deterministic execution, resume handling, aggregation, report rendering, and artifact persistence.
- Create: `services/mlx-worker-python/tests/test_agent_reliability.py`
  - Focused unit tests for all issue acceptance requirements.
- Create: `services/mlx-worker-python/fixtures/evaluation/agent-reliability.dev.v1/manifest.json`
  - Fixture package metadata and supported tag/preset documentation.
- Create: `services/mlx-worker-python/fixtures/evaluation/agent-reliability.dev.v1/scenarios.jsonl`
  - Small initial scenario set, including a stateful wrong-argument failure case.
- Create: `scripts/agent_reliability_eval.py`
  - Local deterministic runner that writes artifacts under a requested output directory.
- Modify: `docs/benchmark-evaluation-contract.md`
  - Add the agent reliability track artifact and report contract.
- Modify: `services/mlx-worker-python/worker/productization/benchmark_export.py`
  - Include discovered agent reliability rows and summaries in existing benchmark export bundles.
- Modify: `services/mlx-worker-python/tests/test_benchmark_export.py`
  - Cover agent reliability artifact collection and export bundle integration.

## Task 1: Ablation Presets And Scenario Loader

- [x] **Step 1: Write failing schema and loader tests**

Add tests in `services/mlx-worker-python/tests/test_agent_reliability.py`:

- `test_expand_ablation_presets_returns_issue_required_guardrail_switches`
  - Assert every required preset exists.
  - Assert baseline enables all guardrails.
  - Assert `all_guardrails_disabled` disables all tracked guardrails.
  - Assert each single-disable preset disables exactly one guardrail.
- `test_load_agent_reliability_scenarios_preserves_tags_and_stateful_validator`
  - Load the fixture package.
  - Assert at least one scenario has `stateful_behavior`.
  - Assert at least one scenario has `error_recovery`.
  - Assert each scenario has stable id, tags, expected output, expected backend state, and model responses keyed by ablation preset.

Run:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_agent_reliability.py::test_expand_ablation_presets_returns_issue_required_guardrail_switches services/mlx-worker-python/tests/test_agent_reliability.py::test_load_agent_reliability_scenarios_preserves_tags_and_stateful_validator
```

Expected: FAIL because the module and fixture do not exist yet.

- [x] **Step 2: Implement minimal presets, dataclasses, loader, and fixture package**

Create:

- `AgentReliabilityAblation`
- `AgentReliabilityScenario`
- `expand_ablation_presets()`
- `load_agent_reliability_scenarios(package_root: Path)`

Fixture rows must be deterministic JSON objects with:

- `id`
- `title`
- `tags`
- `input`
- `tool_backend`
- `expected_output_contains`
- `expected_backend_state`
- `responses_by_ablation`
- optional `metric_hints`

- [x] **Step 3: Run the focused tests to verify GREEN**

Run the same command and expect PASS.

## Task 2: Stateful Execution And Metrics

- [x] **Step 1: Write failing execution tests**

Add tests:

- `test_stateful_scenario_fails_when_tool_argument_does_not_update_backend_state`
  - Run the stateful scenario under an ablation response that uses the correct tool name with the wrong argument.
  - Assert `accuracy == 0.0`, `completeness == 0.0`, `validation_error_count == 1`, and backend state mismatch details are present.
- `test_run_agent_reliability_track_records_required_metrics_per_row`
  - Run two scenarios across baseline and `no_tool_error_recovery`.
  - Assert each JSONL row includes model/backend/profile/ablation/scenario identity and required metrics.
  - Assert wasted tool calls, retry count, nudge count, validation errors, compaction events, elapsed time, token estimate, and cost estimate are numeric.

Run:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_agent_reliability.py::test_stateful_scenario_fails_when_tool_argument_does_not_update_backend_state services/mlx-worker-python/tests/test_agent_reliability.py::test_run_agent_reliability_track_records_required_metrics_per_row
```

Expected: FAIL until execution and metric aggregation exist.

- [x] **Step 2: Implement deterministic scenario execution**

Implement:

- `AgentReliabilityRunConfig`
- `run_agent_reliability_track(config, scenarios, ablations)`
- deterministic response parsing for tool-call JSON/XML using the existing tool-call parser where practical
- an in-memory stateful backend for fixture tools
- final validation that checks expected output fragments and expected backend state
- per-row metrics and row schema `melix.agent_reliability_row.v1`

- [x] **Step 3: Run the focused tests to verify GREEN**

Run the same command and expect PASS.

## Task 3: Resume JSONL And Report Artifacts

- [x] **Step 1: Write failing artifact tests**

Add tests:

- `test_agent_reliability_resume_skips_completed_jsonl_rows`
  - Pre-seed `agent-reliability-rows.jsonl` with one completed row.
  - Run with `resume=True`.
  - Assert the completed row is preserved once and only missing identities are executed.
- `test_agent_reliability_summary_reports_per_ablation_deltas`
  - Persist a run.
  - Assert `agent-reliability-summary.json` includes aggregate metrics grouped by ablation.
  - Assert `agent-reliability-report.md` includes per-ablation completion-rate and wasted-call deltas versus baseline.

Run:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_agent_reliability.py::test_agent_reliability_resume_skips_completed_jsonl_rows services/mlx-worker-python/tests/test_agent_reliability.py::test_agent_reliability_summary_reports_per_ablation_deltas
```

Expected: FAIL until resume and artifact persistence exist.

- [x] **Step 2: Implement artifact persistence**

Implement:

- `persist_agent_reliability_run(...)`
- row identity function
- resume row loading/deduplication
- aggregate summary `melix.agent_reliability_summary.v1`
- Markdown report with baseline deltas

- [x] **Step 3: Run the focused tests to verify GREEN**

Run the same command and expect PASS.

## Task 4: Script And Contract Documentation

- [x] **Step 1: Write failing script smoke test**

Add a test that invokes `scripts/agent_reliability_eval.py` with fixture provider and `--output-dir`, then asserts the JSONL, summary JSON, and Markdown report exist and decode.

Run:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_agent_reliability.py::test_agent_reliability_script_writes_fixture_report
```

Expected: FAIL until the script exists.

- [x] **Step 2: Implement script**

Create `scripts/agent_reliability_eval.py` with:

- `--fixture-root`
- `--output-dir`
- `--model-id`
- `--backend`
- `--profile`
- repeatable `--ablation`
- `--resume`
- `--json`

- [x] **Step 3: Update docs**

Update `docs/benchmark-evaluation-contract.md` with:

- first-slice scope
- artifact names
- row and summary schema versions
- resume semantics
- stateful validator semantics
- expected command
- relationship to existing benchmark/eval exports

- [x] **Step 4: Run the focused script/doc checks**

Run the script smoke test and `git diff --check`.

## Task 4.5: Existing Export Bundle Integration

- [x] **Step 1: Write failing export collector tests**

Add tests in `services/mlx-worker-python/tests/test_benchmark_export.py`:

- `test_collect_agent_reliability_artifacts_finds_rows_and_summaries`
  - Assert top-level and `runs/` reliability artifacts are collected.
- `test_build_export_bundle_includes_agent_reliability_artifacts`
  - Assert existing export bundles include reliability rows and summaries.

Run:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_benchmark_export.py -k 'agent_reliability'
```

Expected: FAIL until the collector is exported and wired into the bundle.

- [x] **Step 2: Implement collector integration**

Implement:

- `collect_agent_reliability_artifacts(...)`
- `_collect_agent_reliability_run(...)`
- bundle keys `agent_reliability_rows` and `agent_reliability_summaries`

- [x] **Step 3: Run the focused export tests to verify GREEN**

Run the same command and expect PASS.

## Task 5: Verification, Coverage, Metrics, Commit, And PR

- [x] **Step 1: Run focused test file**

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_agent_reliability.py services/mlx-worker-python/tests/test_benchmark_export.py -k 'agent_reliability'
```

- [x] **Step 2: Run changed-scope coverage**

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx coverage run -m pytest -q services/mlx-worker-python/tests/test_agent_reliability.py services/mlx-worker-python/tests/test_benchmark_export.py -k 'agent_reliability'
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/productization/agent_reliability.py services/mlx-worker-python/worker/productization/benchmark_export.py services/mlx-worker-python/tests/test_agent_reliability.py services/mlx-worker-python/tests/test_benchmark_export.py
```

Expected: changed-scope coverage at least 95 percent.

- [x] **Step 3: Run PR-scoped metrics report or N/A**

If a registered probe is added, run the corresponding PR-scoped performance command. If no probe applies because the change is deterministic artifact/report logic with no hot runtime path, record `N/A: no runtime hot path changed; focused correctness and coverage were measured`.

- [x] **Step 4: Run broader Python gate as feasible**

At minimum:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_agent_reliability.py services/mlx-worker-python/tests/test_benchmark_export.py services/mlx-worker-python/tests/test_benchmark_evaluation_report.py
git diff --check
```

Prefer `make py-test` before final PR if runtime budget permits.

- [ ] **Step 5: Commit, push, and open PR**

Use one focused commit:

```bash
git add docs/plans/2026-06-21-issue-1387-agent-reliability-track.md docs/benchmark-evaluation-contract.md services/mlx-worker-python/worker/productization/agent_reliability.py services/mlx-worker-python/worker/productization/benchmark_export.py services/mlx-worker-python/tests/test_agent_reliability.py services/mlx-worker-python/tests/test_benchmark_export.py services/mlx-worker-python/fixtures/evaluation/agent-reliability.dev.v1 scripts/agent_reliability_eval.py
git commit -m "feat: add agent reliability ablation track"
git push -u origin codex/issue-1387-agent-reliability-bench-20260621
```

Open a PR for issue #1387 with the required template headings and evidence.
