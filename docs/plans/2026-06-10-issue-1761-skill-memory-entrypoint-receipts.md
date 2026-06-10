# Issue 1761 Skill And Memory Entrypoint Receipt Metadata Plan

## Goal

Make the Python worker skill and memory prompt-context admission primitive
ready for concrete skill-store and memory-store entrypoints by routing admitted
evidence through the source-evidence helper and allowing entrypoint-local
receipt metadata.

## Scope

This slice covers:

- `worker.runtime.skill_memory_context` support for optional entrypoint-local
  `segment_id`, `source_field`, `reason`, and `corrective_action` values.
- Reuse of `PromptContextSourceEvidence` and
  `admit_prompt_context_source_evidence` for admitted skill and memory
  evidence.
- Focused Python tests proving that concrete callers can keep stable public
  receipt fields without exposing raw skill or memory payloads.
- Runtime contract documentation for the entrypoint-ready skill/memory
  admission surface.

This slice does not implement a skill store, memory store, skill lookup,
memory persistence, chat/session wiring, or retrieval ranking. Future callers
must still perform lookup, redaction, and owner-scope checks before calling
these helpers.

## Best End-State Architecture

Concrete skill and memory entrypoints should hand already-redacted source
evidence to a single prompt-context admission surface. The entrypoint may need
stable public receipt IDs or source fields that differ from the generic
`skill` and `memory` defaults, but the actual receipt construction should stay
centralized in `worker.runtime.prompt_context`.

The skill/memory helper should therefore match the retrieval helper shape:
validate source IDs, payloads, owner-scope evidence, and optional entrypoint
receipt fields; emit refused receipts before prompt assembly when malformed;
and admit valid evidence through `PromptContextSourceEvidence`.

## Performance Probes And Metrics

The changed path performs a small constant amount of string validation and
constructs one `PromptContextSourceEvidence` object per admitted skill or
memory payload. It adds no filesystem scans, store lookups, network calls,
model inference, scheduler work, or tool execution.

Verification must include:

- focused red/green tests for `test_skill_memory_context.py`;
- adjacent prompt-context tests;
- changed-line coverage for the touched Python files with at least 95 percent
  coverage;
- full local pre-commit gate before commit on this host;
- PR-scoped performance report with status `ok`, regressions `0`, context
  regressions `0`, and verification failures `0`.

## Implementation Steps

1. Add failing tests proving `admit_skill_context` and `admit_memory_context`
   accept optional entrypoint receipt metadata:
   - custom `segment_id`;
   - custom `source_field`;
   - custom `reason`;
   - custom `corrective_action`.
2. Add failing tests proving malformed optional entrypoint text values produce
   refused receipts with `included = false`, `source_type = skill|memory`, and
   the existing `invalid_skill_context_field` or
   `invalid_memory_context_field` reason.
3. Migrate admitted skill and memory evidence to
   `PromptContextSourceEvidence` and `admit_prompt_context_source_evidence`.
4. Preserve existing default payloads, default receipt shape, source ID
   normalization, owner-scope handling, and refusal behavior.
5. Update the unified runtime contract to document the entrypoint-local fields
   and the fact that this is still not a concrete store implementation.

## Success Criteria

- Existing skill and memory admission behavior remains backward compatible.
- Concrete future entrypoints can preserve stable receipt IDs and source
  fields without bypassing the shared source-evidence helper.
- Malformed entrypoint receipt metadata fails closed before prompt assembly.
- Receipt JSON remains redacted from raw skill and memory payload text.
