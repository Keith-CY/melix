# Retrieval Public Source ID Fast Path

## Scope

This Python-only performance slice is limited to public source-id classification used by retrieval context receipt projection. It keeps the existing public-source semantics while adding a direct fast path for Melix-generated numeric `source:<digits>` identifiers before falling back to the compiled public-source regex.

The slice does not change redaction behavior for non-public source IDs, segment-id redaction, retrieval payload projection, duplicate-field handling, or lookup/store projection semantics.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe `retrieval-context-projection-fastpath` in `infra/perf/pr_scoped_probes.json`.

The probe provides:

- `test_command` for focused retrieval projection tests and probe-registry tests.
- `coverage_command` for changed-scope coverage across retrieval context, untrusted context, focused tests, the registry, and the probe script.
- `probe_command` that measures direct retrieval context projection, store projection, and lookup-copy projection with baseline-vs-optimized timing metrics.

This slice updates the probe watch list and focused commands to include the numeric `source:<digits>` fast-path regression test.

## Implementation plan

1. Add constants for the `source:` prefix and prefix length in `worker/runtime/untrusted_context.py`.
2. In `_is_public_source_id()`, short-circuit numeric `source:<digits>` IDs at length <= 96 before invoking the compiled regex.
3. Add a focused regression test that monkeypatches the regex object to fail if the numeric source-id path falls through.
4. Run focused tests, changed-scope coverage, and the registered local probe on Linux before PR creation.

## Verification plan

Run the registered focused command set locally on Linux. GitHub Actions PR-scoped performance remains the merge gate after push.
