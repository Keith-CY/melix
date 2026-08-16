# Vision family metadata empty fast path

## Scope

This Python-only performance slice is limited to the vision-family metadata
resolution helpers in `worker.runtime.vision_family_adapters`.

The current hot path already avoids copying non-empty metadata mappings. This
follow-up removes the remaining truthiness probe for `None` and empty custom
mappings by using an explicit shared empty metadata mapping only when callers pass
`None`.

## Registered performance probe

The affected path is covered by the registered PR-scoped probe
`vision-family-prompt-token-count-scan` in `infra/perf/pr_scoped_probes.json`.
The registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries and reports `config_resolve_elapsed_ms_mean`,
`metadata_iteration_calls_mean`, `empty_metadata_length_calls_mean`,
`peak_bytes_mean`, and token-count metrics for this path.

## Verification plan

1. Add focused regression tests proving empty metadata mappings no longer pay a
   `__len__` truthiness check while preserving the default family and processor
   metadata behavior.
2. Implement the single fast path: replace `metadata or {}` with an explicit
   `metadata is None` check and reuse a shared empty mapping.
3. Run the registered focused test command locally on Linux.
4. Run the registered coverage command locally on Linux and verify changed-scope
   coverage for touched Python paths.
5. Run the registered probe locally against `origin/main` and this branch with
   `scripts/pr_scoped_performance_run.py`.
6. Use GitHub Actions PR-scoped performance as the merge gate.

## Boundaries

No Swift runtime behavior changes are included. Local validation is Linux-only
for the Python worker path; CI remains the registered probe source of truth before
merge.
