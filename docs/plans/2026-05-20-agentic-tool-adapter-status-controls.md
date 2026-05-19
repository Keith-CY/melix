# Agentic Tool Adapter Status Controls

## Goal

Complete issue #680 by making timeout, cancellation, and failure-stage behavior
testable for every deterministic built-in agentic tool adapter.

## Scope

- Add fixture-driven status overrides to the deterministic agentic tool runtime.
- Support `timeout`, `failed`, and cancellation aliases for all built-in tools.
- Map cancellation to the existing observation status model as `failed` with an
  explicit `failure_stage: cancelled` payload marker.
- Keep the observation status enum unchanged: `completed`, `timeout`, and
  `failed`.

## Non-Goals

- No network-backed providers.
- No asynchronous process cancellation.
- No protocol schema changes.
- No benchmark or evaluation schema changes.

## Design

Fixture runs may provide `tool_status_overrides` in the tool fixture context.
The runtime checks overrides before executing a concrete adapter payload. The
lookup order is:

1. exact tool call id
2. tool name
3. `*`

Override values may be a string status or an object with `status`, `message`,
and `failure_stage` fields. Cancellation aliases (`cancelled`, `canceled`, and
`cancel`) are normalized to observation status `failed` and preserve
`cancelled: true` in the payload.

This keeps the production observation contract stable while making failure and
timeout states deterministic in focused tests for every adapter.

## Verification

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_agentic_tools.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" COVERAGE_FILE=/tmp/agentic-tool-status.coverage uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_agentic_tools.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" COVERAGE_FILE=/tmp/agentic-tool-status.coverage uv run --project services/mlx-worker-python coverage json -o /tmp/agentic-tool-status-coverage.json
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python scripts/python_changed_line_coverage.py --coverage-json /tmp/agentic-tool-status-coverage.json --diff-from origin/main services/mlx-worker-python/worker/runtime/agentic_tools.py services/mlx-worker-python/tests/test_agentic_tools.py
git diff --check
```

## Success Metrics

- Six built-in tool adapters covered by timeout assertions.
- Six built-in tool adapters covered by failure-stage assertions.
- Six built-in tool adapters covered by cancellation assertions.
- Changed-line coverage for touched Python files is at least 95 percent.

## Known Gaps

- Real asynchronous cancellation of external providers remains out of scope
  because the deterministic runtime has no external provider processes.
- Future network-backed adapters must convert provider-level cancellation into
  the same observation payload fields.
