# Issue 1761 Agentic Judge Tool Observation Receipts Plan

## Goal

Continue #1761 by carrying existing tool-observation untrusted-context receipts
into agentic judge prompt snapshot evidence.

## Scope

This slice covers the Python worker agentic judge prompt snapshot path in
`worker.engine.evaluation_core`.

It will:

- keep the persisted judge prompt user payload unchanged;
- keep each admitted user-payload field receipt generated through
  `worker.runtime.prompt_context.admit_prompt_context_segments`;
- copy any existing `untrusted_context_receipts` attached to executed
  `agentic_tool_observations` into the snapshot-level
  `untrusted_context_receipts` list;
- preserve tool observation receipt dictionaries without copying raw tool
  payload text into receipt metadata;
- update the governing benchmark/evaluation and unified runtime contracts.

This slice does not add new live RAG stores, skill entrypoints, memory
entrypoints, background-continuation linking, or prompt wording changes.

## Best End-State Architecture

Prompt snapshots should expose every prompt-boundary decision needed to audit
the final model-visible user payload without making downstream readers parse
untrusted payload content. The agentic judge prompt snapshot already admits each
top-level user-payload field as data-only user context. Tool observations inside
that payload are themselves shared trace objects that now carry generic
tool-output and retrieval-source receipts.

The best end state is a layered receipt list:

- first, one admission receipt per top-level judge user-payload field;
- then, the already-emitted receipts from each executed tool observation.

This preserves the prompt text and observation replay semantics while making
tool output, retrieved document, and retrieved image boundaries visible at the
snapshot level.

## Performance Probes And Metrics

The changed path performs a deterministic linear scan over the already-built
tool observation dictionaries and copies receipt dictionaries. It introduces no
model inference, no tool execution, and no filesystem IO.

Local pre-commit verification exposed the existing
`evaluation-sample-probe-aggregation` microbenchmark as a direct gate for
`evaluation_core.py`. This slice therefore also keeps that established helper
within the zero-regression envelope by adding an exact-field fast path for the
registered evaluation sample probe fields. The fast path preserves falsey-value
handling, missing-field defaults, empty-sample output, and rounding semantics.
The same pre-commit gate also selects `evaluation-job-id-high-water-mark`, so
the run-id allocation hot path keeps its existing one-time scan semantics while
using direct directory creation for cached subsequent allocations.

Verification must include:

- focused pytest for agentic judge prompt-context receipt propagation;
- focused pytest for the agentic judge prompt snapshot artifact;
- changed-line coverage for the touched Python scope with at least 95 percent
  changed-line coverage;
- full local pre-commit gate on this host;
- PR-scoped performance report with `Status: ok` and zero regressions.

## Implementation Steps

1. Add a focused failing test proving
   `_agentic_judge_untrusted_context_receipts` appends existing tool observation
   receipts after the top-level user-payload field receipts.
2. Update the existing prompt snapshot artifact test to expect the generic
   `tool_observation` receipt from the executed `image_crop` observation.
3. Add a small helper in `evaluation_core.py` that extracts mapping receipts
   from `tool_observations[*].untrusted_context_receipts` and returns defensive
   copies.
4. Append those extracted receipts after the shared prompt-context admission
   receipts.
5. Update contract docs and run focused tests, changed-line coverage, full gate,
   and scoped performance before committing.

## Success Criteria

- Snapshot-level `untrusted_context_receipts` includes top-level judge
  user-payload field receipts plus nested tool observation receipts.
- The judge prompt `messages` payload is unchanged.
- Tool observation receipt values are copied as metadata only, and raw tool
  payload text is not introduced into receipt metadata.
- Receipt count matches the complete snapshot-level receipt list.
