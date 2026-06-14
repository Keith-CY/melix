# Retrieval Lookup Payload Copy Fast Path

This Python-only performance slice is limited to `worker.runtime.retrieval_context._copy_payload`, which is used by `project_retrieval_lookup_result(...)` when it defensively copies prompt payloads produced from retrieval store records.

## Probe Coverage

The affected production file is already covered by the PR-scoped registered probe `retrieval-context-projection-fastpath` in `infra/perf/pr_scoped_probes.json`. This slice extends the checked-in probe script to report lookup payload copy metrics in addition to the existing projection/store projection metrics:

- `lookup_copy_baseline_elapsed_ms_mean`
- `lookup_copy_optimized_elapsed_ms_mean`
- `lookup_copy_delta_ms`
- `lookup_copy_speedup`

The registry already provides focused `test_command`, `coverage_command`, and `probe_command` entries for the changed path, tests, and probe script.

## Implementation Plan

1. Preserve lookup-result defensive copy semantics for nested JSON containers and custom mutable fallback values.
2. Replace the generic `deepcopy(dict(payload))` path with a JSON-container-aware copier that returns immutable scalar values directly, recursively copies `dict`/`list`/`tuple`, and falls back to `deepcopy(...)` for custom mutable objects.
3. Extend focused tests to prove nested containers and custom mutable fallback values remain isolated from the source store projection.
4. Extend `scripts/retrieval_context_projection_probe.py` to compare the historical `deepcopy(dict(payload))` baseline against the optimized copier.
5. Run focused pytest, changed-scope coverage, and the registered probe locally on Linux before opening the PR. CI remains the final registered PR-scoped performance gate.

## Success Criteria

- Focused retrieval context tests pass.
- Changed-scope coverage remains at or above the repository threshold for the changed files.
- The local registered probe shows improved lookup payload copy mean time without regressing projection behavior.
