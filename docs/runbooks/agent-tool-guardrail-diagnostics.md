# Agent Tool Guardrail Diagnostics

## Purpose

Use this runbook to produce deterministic evidence for the worker-owned agent
tool guardrail loop. The fixture exercises:

- a premature terminal response followed by successful recovery;
- matching-argument prerequisite admission;
- repeated prerequisite rejection and malformed-budget exhaustion;
- 100 bounded approval waits with two executor slots retained;
- cancel, timeout, resume, and runtime-reload lifecycle release;
- sanitized event and final diagnostic serialization.

The command does not start a model, network service, command tool server,
approval UI, or production executor. It exercises the shipped selected-registry
and deterministic runtime boundaries with an in-process fixture executor.

## Generate The Bundle

From the repository root:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" \
  uv run --project services/mlx-worker-python \
  python scripts/agentic_tool_guardrail_diagnostics.py \
  --output .runtime/diagnostics/agent-tool-guardrail.json
```

The output path is printed after the write succeeds. The `.runtime` tree is
ignored by git and is the expected location for local evidence.

## Inspect The Result

```bash
jq '{schema_version, runs: [.runs[] | {
  scenario,
  outcome,
  turn_actions,
  diagnostics,
  event_count: (.events | length)
}], parking: {
  approval_wait_count: .parking.approval_wait_count,
  executor_capacity_available_min: .parking.executor_capacity_available_min,
  diagnostics: .parking.diagnostics,
  event_count: (.parking.events | length)
}}' .runtime/diagnostics/agent-tool-guardrail.json
```

The successful fixture should report:

- `outcome = completed`
- `tool_execution_count = 2`
- `completed_required_tools = ["text_search", "image_search"]`
- `last_nudge_type = required_steps_completed`
- `terminal_failure_count = 0`

The exhaustion fixture should report:

- `outcome = failed`
- `admission_rejection_count = 2`
- `consecutive_malformed_responses = 2`
- `tool_execution_count = 0`
- `final_failure_reason = malformed_response_budget_exhausted`
- `terminal_failure_count = 1`

The parking fixture should report:

- `approval_wait_count = 100`
- `executor_capacity_available_min = 2`
- `executor_leases_used = 0` after cleanup
- `parking_permits_used = 0` after cleanup
- release reasons split across `cancelled = 33`, `timed_out = 33`, and
  `runtime_reload = 34`
- `release_suppression_count = 1` for the deliberate duplicate reload release
- `retained_released_tombstone_count <= max_released_tombstones`

The parking helper is the production extension boundary for a future approval
surface. A scheduler starts a lifecycle with `begin_turn`, parks only after it
has acquired a bounded permit, resumes only after reacquiring an executor
lease, and calls `release` for completion, cancellation, or timeout. Runtime
reload restores the v1 lifecycle state and calls
`release_all_for_runtime_reload`. Python owns these state transitions; Swift
validates and shapes the matching Codable contract. The repository still has no
approval UI or concrete executor integration, so this fixture is capacity-safety
evidence rather than approval-flow evidence.

The CLI keeps this lifecycle fixture sequential so repeated diagnostic bundles
have stable event ordering. The real concurrency proof is the 100-thread barrier
test in `test_agentic_tool_parking_budget.py` and the registered
`agentic-tool-guardrail-loop` performance probe; both exercise concurrent wait,
resume, and release operations against the process-wide lock.

## Redaction Check

The bundle contains turn actions, sanitized events, and diagnostics. It excludes
prompts, tool arguments, tool observation payloads, and restorable guardrail
state. Confirm the fixture's sensitive sentinels and excluded field names are
absent:

```bash
if rg -n 'SENSITIVE_|"arguments"|"observation"' \
  .runtime/diagnostics/agent-tool-guardrail.json; then
  printf 'unexpected sensitive guardrail evidence\n' >&2
  exit 1
fi
```

Do not add state snapshots to this bundle. Completed-call arguments are required
inside protected state for prerequisite matching and replay identity, but they
are not operator diagnostics.

## Verification

Run the focused Python and Swift contract suites:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" \
  uv run --project services/mlx-worker-python pytest -q \
  services/mlx-worker-python/tests/test_agentic_tool_guardrail_loop.py \
  services/mlx-worker-python/tests/test_agentic_tool_parking_budget.py \
  services/mlx-worker-python/tests/test_agentic_tool_guardrail_diagnostics.py

CLANG_MODULE_CACHE_PATH="$PWD/.runtime/swift-module-cache" \
  xcrun swift test --no-parallel \
  --package-path services/control-plane-swift \
  --scratch-path "$PWD/.runtime/swift-guardrail-build" \
  --filter AgenticToolGuardrailContractTests
```

For repository handoff, also run the full command contract and the versioned
pre-commit hook described in `AGENTS.md`.
