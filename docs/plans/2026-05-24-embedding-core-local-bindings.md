# Embedding core local binding slice

## Scope

This Python-only performance slice is limited to `EmbeddingCore.embed()` in
`services/mlx-worker-python/worker/engine/embedding_core.py`.

## Registered probe

The affected path is covered by the existing PR-scoped performance probe
`embedding-core-inputs-view` in `infra/perf/pr_scoped_probes.json`. The probe
already includes focused `test_command`, `coverage_command`, and
`probe_command` entries for `embedding_core.py`, the embedding runtime tests,
the PR-scoped probe tests, and `scripts/embedding_core_inputs_probe.py`.

## Optimization hypothesis

`EmbeddingCore.embed()` touches `self._registry`, `request.inputs`, and the
loaded runtime model on every request. This slice keeps behavior unchanged while
binding those values to local variables before the hot runtime call and response
materialization loop. The goal is to remove repeated attribute lookups in the
probe path without materializing the protobuf repeated input container as a
list.

## Verification

Run the registered focused pytest command, changed-scope coverage command, and
`embedding-core-inputs-view` probe locally on Linux. Compare the local probe
against the synced `origin/main` baseline before pushing. CI remains the merge
gate for the registered PR-scoped performance report.
