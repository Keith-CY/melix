# Issue 1382 Tool Schema Consistency Preflight Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a worker-owned preflight that compares prompt-visible or context-referenced tool affordances against the actual callable agentic tool schema list before generation starts, with sanitized receipts for mismatches.

**Architecture:** `worker.runtime.tool_registry` remains the owner for agentic tool schema, index metadata, selection, and policy decisions. This slice adds a pure preflight helper at the same boundary so workflow-selected tools, retrieved procedure references, and injected/admin affordances can be checked against the selected `ToolRegistry.names()` snapshot before the model sees instructions that mention unavailable tools.

**Tech Stack:** Python worker runtime, dataclasses, deterministic tool registry, pytest, coverage.

---

## Governing Documents

- `AGENTS.md`
- `docs/unified-agentic-tool-runtime-contract.md`
- `docs/plans/2026-06-23-issue-1382-tool-registry-parity.md`
- `docs/plans/2026-07-12-issue-1382-tool-healing-receipts.md`
- GitHub issue #1382, especially the 2026-06-15 watch finding for `toolSchemaConsistency` preflight diagnostics.

## Scope

This slice covers:

- a worker-owned `ToolSchemaConsistencyDecision` result;
- a `preflight_agentic_tool_schema_consistency(...)` helper that accepts sanitized tool affordance records and a selected `ToolRegistry`;
- a new `melix.agentic_tool_schema_consistency.v1` receipt that snapshots referenced tool ids, callable tool ids, missing tool ids, invalid affordance count, and the allowed next step;
- tests for a workflow affordance that names a tool absent from the selected schema list, a procedure/viewed-context tool becoming available, a policy-disabled tool referenced by retrieved context, and invalid affordance names being counted without raw text leakage;
- canonical runtime contract documentation for the preflight receipt.

This slice does not implement prompt assembly, full workflow execution, retrieved procedure loading, Swift request shaping, or live agent loop retries.

## Receipt Contract

`melix.agentic_tool_schema_consistency.v1` records whether pre-generation tool affordances match the callable schema list. The receipt includes:

- `schema_version`
- `toolset_version`
- `outcome = consistent|mismatch`
- `source`
- `referenced_tools`
- `callable_tools`
- `missing_tools`
- `invalid_affordance_count`
- `checked_affordance_count`
- `allowed_next_step`
- `corrective_action`

Receipts must not include raw prompts, retrieved text, procedure bodies, URLs, workspace paths, tool arguments, observation payloads, or account identifiers. The helper may inspect caller-provided values in memory, but serialized receipts expose only canonical tool identifiers, source labels, counts, and typed corrective metadata.

## Performance Probes And Metrics

The changed path is Python-only pre-generation validation. The helper performs one bounded pass over caller-provided affordances and compares them against cached registry names. No external I/O is introduced.

Success metrics:

- focused changed-scope coverage for touched Python files remains at least 95 percent;
- focused tool registry tests pass;
- PR-scoped performance report has no in-scope regression;
- full local pre-commit gate passes before pushing the PR.

## File Structure

- Modify `services/mlx-worker-python/worker/runtime/tool_registry.py`.
  Add the schema-consistency receipt version, `ToolSchemaConsistencyDecision`, `preflight_agentic_tool_schema_consistency(...)`, and small sanitization helpers.
- Modify `services/mlx-worker-python/tests/test_tool_registry.py`.
  Add focused TDD tests near the existing registry parity and policy selection tests.
- Modify `docs/unified-agentic-tool-runtime-contract.md`.
  Document the new preflight receipt near the tool selection and policy receipt contracts.
- Create this plan file.

## Task 1: Add RED Tests For Schema Consistency Preflight

**Files:**

- Modify: `services/mlx-worker-python/tests/test_tool_registry.py`

- [x] **Step 1: Add failing tests for consistent and mismatched affordances**

Add tests that call the intended public helper before it exists:

- selected schema only includes `local_compute`; a workflow affordance references `visit`; receipt reports `mismatch`, `missing_tools=["visit"]`, and no raw procedure text;
- selected schema includes `local_compute` and `visit`; a viewed-procedure affordance references `visit`; receipt reports `consistent`;
- `allow_web=False` selection omits `visit`; retrieved context references `visit`; receipt reports the policy-disabled mismatch through the callable schema snapshot;
- invalid affordance values are counted and omitted from the receipt rather than echoed.

- [x] **Step 2: Run focused tests to verify RED**

Run:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_tool_registry.py -q
```

Result: RED verified. The focused suite reported 4 failures because
`worker.runtime.tool_registry` did not yet expose
`preflight_agentic_tool_schema_consistency`, while the existing 113 tests
passed.

## Task 2: Implement Preflight Helper And Receipt

**Files:**

- Modify: `services/mlx-worker-python/worker/runtime/tool_registry.py`

- [x] **Step 1: Add result and receipt version**

Add `TOOL_SCHEMA_CONSISTENCY_RECEIPT_SCHEMA_VERSION = "melix.agentic_tool_schema_consistency.v1"` and a frozen `ToolSchemaConsistencyDecision` with `consistent`, `receipt`, `missing_tools`, and `referenced_tools`.

- [x] **Step 2: Normalize affordances without leaking raw text**

Accept strings and mapping objects with `tool_id`, `tool_name`, or `name`. Keep only values matching the canonical tool-name regex. Count invalid or blank affordances without serializing their raw values.

- [x] **Step 3: Compare against callable schema names**

Use `registry.names()` as the authoritative callable snapshot. Preserve canonical selectable-tool ordering for receipt arrays, dedupe referenced tools, and surface missing canonical tool ids.

## Task 3: Document Contract And Verify

**Files:**

- Modify: `docs/unified-agentic-tool-runtime-contract.md`
- Modify: `docs/plans/2026-07-12-issue-1382-tool-schema-consistency-preflight.md`

- [x] **Step 1: Document the receipt**

Add a short schema-consistency preflight section that states the guard runs before generation and strips or blocks mismatched affordances before prompt assembly proceeds.

- [x] **Step 2: Run focused verification**

Run the focused test and coverage commands for the touched Python scope. Update this plan with the result.

Focused verification result:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_tool_registry.py -q
# 118 passed
```

Changed-scope coverage result:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx coverage run -m pytest -q services/mlx-worker-python/tests/test_tool_registry.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx coverage json -o coverage.json
UV_PYTHON=3.12 uv run python scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/runtime/tool_registry.py services/mlx-worker-python/tests/test_tool_registry.py
# TOTAL 106 0 100%
```

- [x] **Step 3: Run full PR gate**

Run the Melix local gate before opening the PR:

```bash
make bootstrap
make proto
make swift-test
make py-test
make integration-test
.githooks/pre-commit
```

Current full-gate result:

```bash
make bootstrap
# passed
make proto
# passed
make swift-test
# passed
make py-test
# 4939 passed, 14 skipped
make integration-test
# 123 passed, 1 skipped
```

Pre-commit result and performance analysis:

```bash
.githooks/pre-commit
# make swift-test: passed
# make py-test: 4939 passed, 14 skipped, 2 warnings
# make integration-test: 123 passed, 1 skipped
# PR-scoped performance report: Status regression
```

Report path:

```text
.runtime/pre-commit-performance/20260711-204420-d221088f/report/report.md
```

The report selected five direct/gated probes. The four tool-registry probes were
`ok` with targeted tests passing and changed-scope coverage at 100 percent. The
single reported regression was `local-job-followup-scan-scandir` on
`scalar_copy_delta_ms`, from `-426.515` to `-418.411` ms.

Analysis: that probe was selected because this slice changes the shared
`docs/unified-agentic-tool-runtime-contract.md`, which is in the local-job
probe watch list. This slice does not change
`worker/runtime/local_job_continuation.py`, its tests, the probe script, or the
probe registry. Local-job behavioral metrics were neutral or improved:
`elapsed_ms_mean` stayed within the 5 percent threshold, scan counters were
unchanged, and `projection_elapsed_ms_mean` improved slightly. Re-running the
same scalar-copy subprobe against the unchanged head code produced
`scalar_copy_delta_ms` values of `-419.068`, `-437.020`, and `-445.679` ms,
showing the `+8.104` ms report delta is within local measurement noise rather
than an in-scope regression. The commit hook is rerun with
`MELIX_PRE_COMMIT_ALLOW_PERF_REGRESSION=1` and this explicit rationale.
