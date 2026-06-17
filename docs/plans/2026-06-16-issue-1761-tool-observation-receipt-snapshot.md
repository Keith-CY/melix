# Issue 1761 Tool Observation Receipt Snapshot

## Goal

Freeze Python worker tool-observation untrusted-context receipts at observation
creation time so prompt-boundary evidence is a stable audit snapshot even when
callers read the same observation multiple times.

## Scope

This slice is limited to `worker.runtime.tool_observation`.

In scope:

- build the generic `tool_observation` prompt-boundary receipt during
  `normalize_tool_observation`;
- copy source-specific receipts into the same immutable snapshot;
- keep receipt JSON metadata-only, including when payload text contains
  prompt-injection phrases;
- keep sanitized payloads, replay hashes, byte metrics, timeout metadata, and
  source receipt normalization behavior unchanged;
- document the snapshot boundary in the unified agentic tool runtime contract.

Out of scope:

- changing deterministic tool execution payloads;
- adding new tool kinds or prompt assembler surfaces;
- changing source-specific receipt schemas for retrieval, skill, memory, visual,
  local compute, status override, or session owner-scope slices.

## Performance Probes And Metrics

Receipt construction already happens whenever callers serialize an observation.
This slice moves that constant-size work to observation normalization and avoids
repeat admission on later reads. Expected runtime impact is neutral to slightly
positive for repeated observation serialization.

Verification must include:

- focused RED/GREEN pytest for receipt snapshot behavior;
- full related `test_tool_observation.py` and `test_agentic_tools.py`;
- changed-line coverage for touched Python scope at 95 percent or higher;
- `git diff --check`;
- scoped performance report with status `ok`;
- full repository pre-commit gate before PR creation.

## Implementation Steps

1. Add a failing test in
   `services/mlx-worker-python/tests/test_tool_observation.py` that monkeypatches
   `admit_prompt_context_segments`, creates an observation whose payload contains
   prompt-injection text, changes the monkeypatched admission response, then
   asserts `record.untrusted_context_receipts` and
   `record.as_agentic_trace_observation()["untrusted_context_receipts"]` still
   expose the original metadata-only snapshot.
2. Run the focused test and confirm it fails because the current property
   rebuilds receipts on each access.
3. Add an immutable `untrusted_context_receipts` tuple field to
   `ToolObservationRecord` and remove the computed admission property.
4. In `normalize_tool_observation`, build the generic prompt-boundary receipt
   once from the sanitized payload, append normalized source receipts, and pass
   the tuple into `ToolObservationRecord`.
5. Update `docs/unified-agentic-tool-runtime-contract.md` to state that
   `melix.agentic_tool_observation.v1` receipts are a normalization-time
   snapshot, not lazily regenerated evidence.
6. Run focused tests, related tests, changed-line coverage, diff check, scoped
   performance, and the full pre-commit gate.

## Success Criteria

- Tool-observation receipt lists are stable across repeated property and trace
  serialization reads.
- Prompt-injection text may remain in sanitized payload data, but receipt JSON
  contains only source metadata and policy text.
- Source-specific receipt normalization still redacts private identifiers and
  malformed source receipts still become refusal receipts.
- Replay payload hashes and fingerprints remain independent of attached source
  receipts.
