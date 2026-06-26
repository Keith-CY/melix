# Retrieval lookup metadata single-pass validation

This Python-only performance slice is limited to `worker.runtime.retrieval_context.project_retrieval_lookup_result`.

## Scope

The lookup-result projection path accepts optional wrapper metadata (`lookup_source_id`, `lookup_segment_id`, and `lookup_source_field`) that is used when malformed lookup records need a wrapper-level refusal receipt. The previous implementation validated that metadata through `_lookup_result_metadata_refusal`, then normalized the same values through `_lookup_metadata_text_or_default`, causing repeated string checks/strips on the valid-metadata path measured by the registered retrieval-context probe.

This slice keeps refusal semantics unchanged while validating and normalizing wrapper metadata in one pass inside `project_retrieval_lookup_result`. It does not change retrieval record projection, payload copying, receipt copying, or store-record validation behavior.

## Registered probe

The affected path is covered by the registered PR-scoped probe `retrieval-context-projection-fastpath` in `infra/perf/pr_scoped_probes.json`.

The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/runtime/retrieval_context.py`
- `services/mlx-worker-python/tests/test_retrieval_context.py`
- `scripts/retrieval_context_projection_probe.py`

## Local verification plan

Run on Linux before opening the PR:

1. Focused retrieval-context tests from the registered probe.
2. Changed-scope coverage from the registered probe.
3. The registered retrieval-context projection probe locally with repeated samples.

GitHub Actions PR-scoped performance remains the final registered probe validation and merge gate.
