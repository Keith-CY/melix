# Issue 1382 Tool Guardrail Admission Receipts

## Goal

Add a focused agentic tool-call guardrail admission helper that turns malformed
or non-executable model tool calls into typed retry-nudge receipts before tool
execution.

## Governing Documents

- `AGENTS.md`
- `docs/unified-agentic-tool-runtime-contract.md`
- `docs/plans/2026-06-23-issue-1382-tool-registry-parity.md`
- `docs/plans/2026-07-09-issue-1382-network-tool-consent.md`

## Scope

This slice covers:

- a worker-owned `melix.agentic_tool_guardrail.v1` receipt for tool-call
  admission decisions;
- typed retry-nudge outcomes for unknown tools, malformed tool-call objects,
  non-object arguments, and missing required arguments;
- bounded retry metadata through `attempt_index`, `max_retry_nudges`, and
  `terminal_after_budget`;
- focused Python tests proving receipts do not include raw prompt text or raw
  tool arguments.

This slice does not add a full agent loop, execute retry prompts, alter the
default fail-fast `execute_agentic_tool_calls(...)` behavior, or change live
tool execution policy. Later slices can call this helper from CLI/app agent
loops before executing model-emitted tool calls.

## Architecture

The end-state #1382 guardrail layer should validate model tool calls before any
adapter can execute, produce a precise nudge for the next model turn, and leave
operator-visible evidence when retries are exhausted.

This slice establishes that boundary without changing current callers:

- `admit_agentic_tool_calls(...)` normalizes the candidate call list against a
  registry and returns an admission result.
- Valid calls return an admitted receipt plus normalized calls for downstream
  execution.
- Invalid calls return exactly one retry/terminal receipt with a stable
  `failure_class` and `nudge_type`.
- Receipts include tool IDs, required argument names, retry indexes, and an
  allowed next step. They intentionally exclude raw arguments, prompt text,
  URLs, file paths, or retrieved content.

## Performance Probes And Metrics

The helper is O(number of tool calls + selected tool count) and runs before
tool execution. It only inspects call shape, declared tool IDs, and required
argument names.

Metrics for this slice:

- unknown-tool and invalid-argument admissions produce typed retry receipts;
- admitted receipts expose call/tool counts without raw arguments;
- focused changed-scope coverage for `agentic_tools.py` and
  `test_agentic_tools.py` is at least 95 percent before commit;
- PR-scoped performance report shows no in-scope regression.

## TDD Plan

1. Add failing tests in `services/mlx-worker-python/tests/test_agentic_tools.py`
   for admitted calls, unknown tools, invalid argument roots, and missing
   required arguments.
2. Implement `AgenticToolGuardrailAdmission` and
   `admit_agentic_tool_calls(...)` in
   `services/mlx-worker-python/worker/runtime/agentic_tools.py`.
3. Update `docs/unified-agentic-tool-runtime-contract.md` with the guardrail
   receipt contract.
4. Run focused tests, changed-scope coverage, `git diff --check`, scoped
   performance report, and the full relevant local gate before opening the PR.

## Verification Commands

Focused tests:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_agentic_tools.py
```

Changed-scope coverage:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx coverage run -m pytest -q services/mlx-worker-python/tests/test_agentic_tools.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx coverage json -o coverage.json
UV_PYTHON=3.12 uv run python scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/runtime/agentic_tools.py services/mlx-worker-python/tests/test_agentic_tools.py
```

General checks:

```bash
git diff --check
```
