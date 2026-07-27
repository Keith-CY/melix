# Embedding core response constructor binding

## Scope

This Python performance slice is limited to `EmbeddingCore.embed()` response and
error construction in `services/mlx-worker-python/worker/engine/embedding_core.py`.
It does not change runtime input forwarding, embedding vector construction, or
registry behavior.

## Registered probe

The affected path is already covered by the registered PR-scoped probe
`embedding-core-inputs-view` in `infra/perf/pr_scoped_probes.json`. The registry
entry has focused `test_command`, `coverage_command`, and `probe_command` entries
for embedding runtime behavior, changed-scope coverage, and the synthetic
embedding response workload.

## Plan

Bind the generated protobuf response and error constructors at module import time
so the hot `embed()` loop avoids repeated module-attribute lookups while creating
successful responses and defensive error responses. Preserve the existing
zero-copy request input view and per-vector repeated-field extension behavior.

## Verification

Run the registered focused tests, changed-scope coverage, and
`embedding-core-inputs-view` probe locally on Linux before pushing. GitHub Actions
PR-scoped performance remains the merge gate for the registered probe report.
