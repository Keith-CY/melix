# Issue 1761 Runtime GRPO Candidate Receipt Summary Plan

## Goal

Preserve untrusted-context receipt evidence for every runtime-generated GRPO
candidate that executes agentic tools, without copying full tool observations
for non-selected candidates.

## Scope

This slice is limited to Python worker GRPO runtime-generation trace evidence in
`worker.model_ops.rl_alignment_training`:

- keep selected candidate rows unchanged: selected candidates still carry full
  `agentic_tool_observations`;
- add scalar receipt evidence to each generated candidate and candidate reward
  trace row that has a tool run;
- preserve the existing omission of full non-selected tool observations;
- avoid copying tool payloads, retrieved text, page content, media refs, prompt
  text, or receipt bodies into the new scalar fields;
- update this plan and focused tests for the runtime GRPO tool trajectory path.

Out of scope:

- changing agentic tool execution, reward scoring, fatal-state masking, or
  candidate selection;
- storing full non-selected observations;
- adding live RAG, skill, memory, MCP, workflow, or local-job execution wiring;
- changing benchmark request-row receipt evidence.

## Architecture

`_attach_runtime_candidate_tool_evidence` already records candidate-local tool
calls, tool metrics, and observation counts. It does not expose whether those
observations carried untrusted-context receipts unless the candidate later
becomes the selected trace row and receives full `agentic_tool_observations`.

This slice derives a small receipt summary from the existing
`tool_run.observations` payloads:

- `agentic_tool_untrusted_context_receipt_schema`
- `agentic_tool_untrusted_context_receipt_count`

The schema is the first string `schema_version` found on a mapping-shaped
receipt. The count is the total number of mapping-shaped receipts across all
candidate observations. Malformed receipt values are ignored for the summary so
they do not inflate evidence counts. The summary is attached to
`generated_candidates` entries and copied into candidate reward trace rows.
Selected rows still attach the full tool run through `_attach_agentic_tool_run`.

## Performance Probes And Metrics

The changed path adds a linear scan over already-materialized candidate tool
observation receipt lists. It adds no model inference, filesystem access,
network access, scheduler work, retrieval ranking, or persistent store access.

Verification must include:

- focused pytest for `test_rl_alignment_runtime_tool_trajectories.py`;
- changed-line coverage for touched Python files at 95 percent or higher;
- `git diff --check`;
- scoped performance report with status `ok`, regressions `0`, context
  regressions `0`, and verification failures `0`;
- the required local gate before opening the PR.

## Implementation Steps

1. Add a failing regression test proving selected and non-selected runtime GRPO
   candidates expose receipt schema/count summary fields while non-selected
   candidate reward trace rows still omit full `agentic_tool_observations`.
2. Implement a small summary helper in `rl_alignment_training.py` that scans
   mapping-shaped `untrusted_context_receipts` values from tool observations.
3. Attach the summary in `_attach_runtime_candidate_tool_evidence`.
4. Copy the summary into `_runtime_candidate_reward_trace_rows`.
5. Run focused tests, changed-line coverage, diff checks, scoped performance,
   and the required local gate before opening the PR.

## Success Criteria

- Every runtime-generated candidate with a tool run exposes receipt schema and
  receipt count summary evidence.
- Candidate reward trace rows expose the same summary for selected and
  non-selected candidates.
- Non-selected trace rows still omit full `agentic_tool_observations`.
- New scalar fields do not include tool payloads, retrieved text, page content,
  media references, prompt text, or receipt bodies.
