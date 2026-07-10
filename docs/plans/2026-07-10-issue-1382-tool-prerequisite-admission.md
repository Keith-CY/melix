# Issue 1382 Tool Prerequisite Admission

## Goal

Extend the agentic tool-call guardrail admission boundary so a caller can keep
required-step state outside the model context and block a tool call until its
declared prerequisite tool has already run.

## Governing Documents

- `AGENTS.md`
- `docs/unified-agentic-tool-runtime-contract.md`
- `docs/plans/2026-07-09-issue-1382-tool-guardrail-admission-receipts.md`

## Scope

This slice covers:

- a worker-owned prerequisite descriptor for admission-time tool ordering;
- optional completed-step state passed into `admit_agentic_tool_calls(...)`;
- prerequisite checks for both "tool A before tool B" and matching argument
  keys;
- sanitized `melix.agentic_tool_guardrail.v1` receipt fields that explain the
  blocked tool, required prior tool, and argument keys without recording raw
  arguments, prompts, URLs, paths, or retrieved content;
- focused Python tests for missing, mismatched, and satisfied prerequisites.

This slice does not add a full live agent loop, execute retry prompts, persist
step state, or change the default deterministic tool runtime execution path.
Later slices can persist the same completed-step state beside live agent loops
and pass it into admission before tool execution.

## Architecture

`AgenticToolPrerequisite` declares that a target tool requires a prior tool to
have completed. The descriptor can name argument keys that must match between
the target call and the prior completed call. Callers pass these descriptors
plus completed normalized tool calls into `admit_agentic_tool_calls(...)`.

Admission first validates the target tool-call shape, tool name, argument
object, known tool, and required arguments. After those checks pass, it applies
the prerequisite list for that target tool. If no completed call satisfies the
prerequisite, admission returns one retry/terminal guardrail receipt with:

- `failure_class = tool_prerequisite_violation`
- `nudge_type = tool_prerequisite_required`
- `required_prior_tool`
- `argument_match_keys`
- `allowed_next_step = retry_with_prerequisite_tool`

Receipts expose only tool IDs and argument key names. Argument values are used
only for equality checks in memory and are not serialized.

## Performance Probes And Metrics

The prerequisite check is O(candidate tool calls * prerequisite count *
completed step count) for the caller-provided slice. The expected caller state
is small per agent turn, and no external I/O is introduced.

Metrics for this slice:

- prerequisite violations produce typed retry receipts;
- matching prerequisites admit the target call without adding raw argument
  values to receipts;
- focused changed-scope coverage for the touched Python files is at least 95
  percent before commit;
- PR-scoped performance report shows no in-scope regression.

## TDD Plan

1. Add failing tests in `services/mlx-worker-python/tests/test_agentic_tools.py`
   for missing, mismatched, and satisfied prerequisites.
2. Implement the prerequisite descriptor and admission checks in
   `services/mlx-worker-python/worker/runtime/agentic_tools.py`.
3. Update `docs/unified-agentic-tool-runtime-contract.md` with the sanitized
   prerequisite receipt fields.
4. Run focused tests, changed-scope coverage, `git diff --check`, scoped
   performance report, and the relevant local gate before opening the PR.

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
