# Issue #1761: Local Compute Source Receipts

## Scope

Add source-specific untrusted-context receipt evidence for successful
`local_compute` observations in the Python worker deterministic agentic tool
runtime.

The shared `tool_observation` receipt already marks the full sanitized
observation payload as untrusted prompt data. This slice adds a narrower
`tool_output` receipt for the deterministic compute result itself so downstream
prompt assemblers can distinguish the generic observation boundary from the
tool-output source boundary.

## Non-Goals

- No behavior changes to arithmetic evaluation.
- No changes to timeout or failed local compute payloads.
- No raw code, result values, tool arguments, prompt text, or private context in
  receipt JSON.
- No control-plane prompt classification changes.

## Plan

1. Extend prompt-context source admission to support `tool_output` with the same
   data-only policy text used by live prompt classification.
2. Add a successful `local_compute` source receipt beside the generic
   observation receipt, outside the sanitized payload and replay hash.
3. Update the unified agentic tool runtime contract with the deterministic
   local compute receipt shape.
4. Verify focused tests and changed-scope coverage before committing.

## Performance Probes

- Focused pytest for `test_agentic_tools.py` and `test_prompt_context.py`.
- Changed-scope Python coverage for touched worker runtime and tests.
- Repository pre-commit performance report before PR creation.

## Success Criteria

- Successful `local_compute` observations include exactly one generic
  `tool_observation` receipt and one source-specific `tool_output` receipt.
- The `tool_output` receipt uses `segment_id = <tool_call_id>:compute-result`,
  `source_field = result`, and `source_id = <tool_call_id>`.
- Receipt JSON omits the arithmetic expression and result value.
- Existing payload shape stays backward compatible.
