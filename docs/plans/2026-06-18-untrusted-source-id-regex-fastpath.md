# Untrusted context public source-id regex fast path

This Python-only performance slice covers public source-id detection inside
`worker.runtime.untrusted_context.untrusted_context_receipt(...)`, with the
registered retrieval-context projection probe as the measurement surface.

## Scope

The receipt builder previously validated public source IDs by UTF-8 encoding the
normalized value and then scanning every character through a Python-level
membership loop. Retrieval context projection calls the receipt builder for every
admitted retrieved document/image entry, so that per-character loop appears on
the hot path for complete entry and store-record projections.

This slice replaces the per-call encode-plus-`all(...)` scan with a precompiled
ASCII regex that preserves the same public-source contract:

- 1 to 96 ASCII characters
- characters limited to letters, digits, `.`, `_`, `-`, and `:`
- empty, non-ASCII, too-long, or otherwise non-public source IDs still redact
  through the existing SHA-256 digest path
- segment-id redaction behavior remains unchanged

No protobuf, Swift, prompt payload, or receipt schema behavior changes.

## Registered PR-scoped probe

The affected retrieval projection path is covered by the registered PR-scoped
performance probe `retrieval-context-projection-fastpath` in
`infra/perf/pr_scoped_probes.json`. This slice extends that probe's watch and
changed-scope coverage paths to include
`services/mlx-worker-python/worker/runtime/untrusted_context.py` and this plan
document, while keeping its focused `test_command`, `coverage_command`, and
`probe_command` entries.

## Verification plan

1. Run the focused redaction regression test for the retrieval projection path.
2. Run the registered focused pytest command for
   `retrieval-context-projection-fastpath`.
3. Run the registered changed-scope coverage command and require at least 95%
   coverage for the touched Python scope.
4. Run the registered local Linux probe and compare base vs head metrics.
5. Use GitHub Actions PR-scoped performance as the final base-vs-head merge gate
   before merging.

## Linux validation boundary

This is a Python-only slice and is locally verifiable on Linux. No Swift runtime
behavior is changed or claimed.
