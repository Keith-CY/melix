# Issue 1761 Agentic Judge Prompt Boundary Receipt Plan

## Goal

Add the first prompt-construction receipt slice for untrusted agentic
evaluation context. Agentic judge prompt snapshots must make the trust boundary
machine-readable for each sample-derived segment projected into the judge user
message.

## Scope

This slice covers `agentic-judge-prompt-snapshots.jsonl` rows written by the
Python worker evaluation core for agentic evaluation suites.

The slice records receipts for the existing user-payload fields:

- `question`
- `expected_answer`
- `final_answer`
- `parse_status`
- `scoring_mode`
- `evidence_ids`
- `media_refs`
- `tool_calls`
- `tool_observations`

This slice does not change judge scoring, prompt wording, remote judge calls,
generic chat prompt assembly, skill entrypoints, memory entrypoints, or
background-job continuation behavior. Those remain follow-up #1761 surfaces.

## Architecture

The best end-state architecture is that every untrusted segment included in a
prompt is accompanied by a receipt that explains why it is safe to include as
data and which trusted role, if any, it can influence. This slice adds that
receipt at an already persisted prompt snapshot boundary without changing model
runtime behavior.

Each receipt uses a stable shape:

- `schema_version = melix.untrusted_context_receipt.v1`
- `segment_id`
- `source_type`
- `source_field`
- `message_role`
- `trust_level = untrusted`
- `policy = data_only`
- `boundary_checked = true`
- `included = true`
- `owner_scope_checked = false`
- `reason`
- `corrective_action`

The prompt snapshot row also records:

- `untrusted_context_receipt_count`
- `untrusted_context_receipts`

The existing no-leak validator remains the fail-closed gate for forbidden
nested keys. These receipts document admitted untrusted segments; they do not
weaken that validator or turn sample content into trusted instructions.

## Performance Probes And Metrics

The receipt builder is a small fixed loop over the existing judge user payload
fields. The affected path already has registered evaluation scoped performance
coverage because `evaluation_core.py` changes select evaluation probes.

Verification will include:

- focused pytest for agentic judge prompt snapshot receipts
- changed-line coverage for modified Python and test lines with a target of at
  least 95 percent
- local PR-scoped performance report with `Status: ok`

## Implementation Steps

1. Add failing tests proving prompt snapshots include one receipt per admitted
   user-payload segment and that persisted rows expose receipt counts.
2. Implement a small helper in `EvaluationCore` that builds deterministic
   untrusted-context receipts from the judge user payload keys.
3. Add the receipt fields to agentic judge prompt snapshot rows.
4. Update `docs/benchmark-evaluation-contract.md` and
   `docs/unified-agentic-tool-runtime-contract.md` with the prompt-construction
   boundary receipt.
5. Run focused tests, changed-line coverage, scoped performance, and PR gates.

## Success Criteria

- Agentic judge prompt snapshots expose `untrusted_context_receipts` with one
  receipt for every user-payload segment admitted into the user message.
- Receipts identify each segment as untrusted, data-only, checked, included,
  and projected only into the user role.
- Existing no-leak rejection behavior remains unchanged.
- The contract documents this as the first prompt-construction receipt slice,
  with broader skill, memory, RAG, chat prompt assembly, and background-job
  surfaces left for later #1761 work.
