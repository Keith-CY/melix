# Retrieval lookup payload tuple-pair copy fast path

## Scope

This Python performance slice is limited to `worker.runtime.retrieval_context._copy_payload_value`.
The registered PR-scoped probe `retrieval-context-projection-fastpath` already covers this path with focused tests, coverage, and a local probe command.

## Plan

- Preserve retrieval lookup projection behavior and defensive copying semantics.
- Add a small exact-tuple length-two copy branch for the common lookup metadata label shape used by retrieval context payloads.
- Keep longer tuple behavior on the existing list-comprehension path.
- Verify with the focused retrieval context tests, changed-scope coverage, and the registered retrieval context projection probe on Linux.

## Metrics

The local probe source is `scripts/retrieval_context_projection_probe.py` via the `retrieval-context-projection-fastpath` registry entry. The expected effect is lower `lookup_copy_optimized_elapsed_ms_mean` without changing projection/store metrics semantics.
