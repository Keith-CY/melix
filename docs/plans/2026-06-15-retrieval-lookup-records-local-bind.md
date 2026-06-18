# Retrieval lookup records local bind

This Python-only performance slice is limited to `worker.runtime.retrieval_context.project_retrieval_lookup_result`.

## Scope

The lookup-result projection path previously fetched `lookup_result.get("records")` once to project store records and again when deciding whether malformed wrapper records should be reclassified with lookup-wrapper metadata.

This slice keeps the existing behavior while binding the records payload once and reusing that local value for both the store projection and malformed-record metadata decision. It uses a private sentinel for the missing-key case so the missing-key and non-list-records refusal branches remain distinct from a valid empty list without adding a separate mapping membership check.

No retrieval admission, payload-copy, receipt-copy, lookup-message construction, or malformed-wrapper metadata semantics change.

## Registered probe

The affected path is covered by the registered PR-scoped probe `retrieval-context-projection-fastpath` in `infra/perf/pr_scoped_probes.json`.

The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/runtime/retrieval_context.py`
- `services/mlx-worker-python/tests/test_retrieval_context.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/retrieval_context_projection_probe.py`

This slice extends the probe's focused tests with a regression assertion that a metadata-refusal lookup wrapper reads `records` through the mapping `get` path once. It also extends `scripts/retrieval_context_projection_probe.py` with lookup-wrapper timing and `records` get-call metrics so the registered probe directly measures the optimized `project_retrieval_lookup_result` path.

## Local verification plan

Run on Linux before opening the PR:

1. Focused retrieval-context tests from the registered probe.
2. Changed-scope coverage from the registered probe.
3. The registered probe command locally with repeated samples.

GitHub Actions PR-scoped performance remains the final registered probe validation and merge gate.
