# Issue 1761 lookup wrapper receipt metadata

## Summary

This slice extends the side-effect-free retrieval and skill/memory lookup-result
projection helpers with optional wrapper-level receipt metadata. Concrete live
or durable lookup entrypoints can pass stable lookup source IDs and segment IDs
when the wrapper itself is malformed or when the wrapper delegates to missing
or malformed `records` evidence.

## Scope

- Add optional `lookup_source_id`, `lookup_segment_id`, and
  `lookup_source_field` keyword-only arguments to:
  - `worker.runtime.retrieval_context.project_retrieval_lookup_result`
  - `worker.runtime.skill_memory_context.project_skill_memory_lookup_result`
- Keep current behavior unchanged when callers omit the metadata.
- Fail closed when wrapper metadata is malformed, with no prompt payload, no
  admitted receipts, and no lookup message.
- Use the wrapper metadata for malformed top-level wrapper refusal receipts and
  for missing/malformed `records` refusal receipts.
- Keep the helpers side-effect-free: no store lookup, ranking, filesystem IO,
  session mutation, or raw payload copying into receipt JSON.

## Verification

- Focused TDD tests in:
  - `services/mlx-worker-python/tests/test_retrieval_context.py`
  - `services/mlx-worker-python/tests/test_skill_memory_context.py`
- Changed-line coverage for:
  - `services/mlx-worker-python/worker/runtime/retrieval_context.py`
  - `services/mlx-worker-python/worker/runtime/skill_memory_context.py`
  - the focused tests above
- Existing PR-scoped performance coverage remains the repository merge gate for
  retrieval projection paths. The retrieval projection fast-path probe must
  replay the wrapper metadata lookup tests so changed-line coverage stays
  aligned with the behavior slice.
