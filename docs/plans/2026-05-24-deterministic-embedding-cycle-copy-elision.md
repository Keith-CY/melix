# Deterministic Embedding Cycle Copy Elision

## Scope

This Python-only performance slice is limited to the repeated-cycle fast path in
`worker.runtime.deterministic_embedding_runtime.DeterministicEmbeddingRuntime.embed_inputs()`.
The runtime already detects repeated input cycles and computes one cycle of vectors before
copying those vectors into the repeated output. This slice avoids materializing a temporary
list of all repeated vector copies before extending the output list.

## Registered probe

The affected path is already covered by the registered PR-scoped probe
`deterministic-embedding-duplicate-input-cache` in `infra/perf/pr_scoped_probes.json`.
That probe includes focused `test_command`, `coverage_command`, and `probe_command`
entries for:

- `services/mlx-worker-python/worker/runtime/deterministic_embedding_runtime.py`
- `services/mlx-worker-python/tests/test_embedding_runtime.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/deterministic_embedding_duplicate_probe.py`

The probe script now also emits `peak_bytes_mean` as local diagnostic evidence so the
copy-elision effect is visible during Linux validation. The registered CI comparison
continues to gate on the existing declared metrics.

## Verification plan

Run the registered focused test command, changed-scope coverage command, and registered
probe locally on Linux. Compare the registered probe against `origin/main` and the branch
before pushing. GitHub Actions PR-scoped performance remains the merge gate.

## Acceptance criteria

- Focused tests pass.
- Changed-scope coverage for the touched Python scope is at least 95%.
- The registered probe reports unchanged `embed_text_calls_mean` and a non-regressing or
  improved `elapsed_ms_mean`; the additional local `peak_bytes_mean` diagnostic should move
  down or remain stable.
- PR-scoped performance CI selects and completes the registered probe successfully.
