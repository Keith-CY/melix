# Retrieval source length local binding performance slice

This Python-only performance slice is limited to the retrieval-context projection hot path in `services/mlx-worker-python/worker/runtime/retrieval_context.py`.

## Registered probe

The affected path is covered by the registered PR-scoped probe `retrieval-context-projection-fastpath` in `infra/perf/pr_scoped_probes.json`. The registry entry exposes focused `test_command`, `coverage_command`, and `probe_command` entries for local Linux verification and CI reporting.

## Slice

The hot direct-projection loops already special-case public `source:<digits>` identifiers before falling back to the shared source-id validator. This slice keeps that behavior unchanged and binds `str.isdigit` plus `len` once per projection loop so the numeric-source fast path avoids repeated method and builtin lookups for every accepted retrieval entry and store record.

## Verification plan

1. Run the focused retrieval-context tests and registered probe selection tests.
2. Run changed-scope coverage through the registered coverage command and require at least 95% on the touched scope.
3. Run the registered probe locally on Linux and compare the projection elapsed metrics with the same probe captured on `origin/main`.
4. Use the PR-scoped performance workflow as the merge gate for the registered probe.
