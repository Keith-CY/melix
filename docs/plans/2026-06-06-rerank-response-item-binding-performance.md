# Rerank response incremental assembly performance slice

## Scope

This slice keeps the existing rerank ranking semantics and focuses only on the
Python rerank response assembly path in
`services/mlx-worker-python/worker/engine/rerank_core.py`.

## Registered probe

The affected path is covered by the existing PR-scoped probe
`rerank-core-top-k-heap-selection` in `infra/perf/pr_scoped_probes.json`.
That registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` coverage for `RerankCore` and `scripts/rerank_top_k_probe.py`.

## Change

Build `RerankResponse.items` incrementally with the protobuf repeated-field
`add()` API instead of constructing an intermediate Python list of
`RerankItem` messages. This avoids the temporary list allocation and keeps the
existing top-k ranking algorithm and request document passthrough behavior.

## Validation plan

- Run the registered focused test command for `rerank-core-top-k-heap-selection`.
- Run the registered changed-scope coverage command and remove generated
  `coverage.json` afterwards.
- Run `scripts/rerank_top_k_probe.py` locally on Linux and compare against the
  `origin/main` baseline, focusing on the request-path metric that exercises
  response assembly.
- Use GitHub Actions PR-scoped performance workflow as merge validation.
