# Issue 1761 Local Compute Timeout Receipt

## Goal

Extend the deterministic Python worker `local_compute` timeout path with a
source-specific `tool_output` untrusted-context receipt.

## Scope

This slice is limited to native `local_compute` timeout observations produced
when the deterministic fixture code argument is `timeout`.

In scope:

- keep the existing timeout payload and metrics unchanged;
- attach one source-specific `tool_output` receipt beside the generic
  `tool_observation` receipt;
- use stable metadata: `segment_id = <tool_call_id>:compute-timeout`,
  `source_field = timeout`, and `source_id = <tool_call_id>`;
- keep timeout text, tool arguments, result values, prompt text, and private
  context out of receipt JSON;
- update the unified agentic tool runtime contract.

Out of scope:

- changing deterministic arithmetic parsing;
- changing status override receipts;
- changing failed arithmetic exception payloads;
- changing registry selection, replay hashing, or observation byte metrics.

## Performance Probes And Metrics

The implementation adds one in-memory prompt-context admission on the existing
local timeout path. There is no filesystem, network, model, or scheduler work.

Verification must include:

- focused red/green pytest for the timeout receipt behavior;
- full related Python worker `test_agentic_tools.py`;
- changed-line coverage for touched Python scope at 95 percent or higher;
- `git diff --check`;
- scoped performance report with status `ok`;
- the required pre-commit gate before PR creation.

## Implementation Steps

1. Add a failing test in
   `services/mlx-worker-python/tests/test_agentic_tools.py` proving native
   `local_compute` timeout observations emit one source-specific `tool_output`
   receipt with `segment_id = compute-timeout:compute-timeout`, `source_field =
   timeout`, `source_id = compute-timeout`, and no timeout text copied into
   receipt JSON.
2. Run the focused test and confirm it fails because the timeout source receipt
   is absent.
3. Add a small helper in
   `services/mlx-worker-python/worker/runtime/agentic_tools.py` that admits the
   timeout payload through `PromptContextSourceEvidence(source_type =
   tool_output)`.
4. Attach that helper from `_local_compute_payload` only for the native
   `code == "timeout"` branch.
5. Update `docs/unified-agentic-tool-runtime-contract.md` to describe native
   `local_compute` timeout receipts separately from fixture-driven status
   overrides.
6. Run focused tests, full related tests, coverage, diff check, scoped
   performance, and the pre-commit gate.

## Success Criteria

- Native `local_compute` timeout observations report exactly two receipts: the
  generic `tool_observation` receipt and the source-specific `tool_output`
  timeout receipt.
- Timeout receipt metadata is stable and does not include timeout text or tool
  arguments.
- Existing completed `local_compute` result receipts and fixture-driven status
  override receipts remain unchanged.
