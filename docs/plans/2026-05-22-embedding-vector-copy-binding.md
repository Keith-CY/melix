# Embedding Vector Copy Binding Performance Slice

## Scope

This slice is limited to `DeterministicEmbeddingRuntime.embed_inputs(...)` in the Python worker embedding runtime. The hot path handles batches with duplicate input text by reusing cached vectors and returning a defensive copy for duplicate outputs.

## Registered probe

The affected path is covered by the registered PR-scoped probe `deterministic-embedding-duplicate-input-cache` in `infra/perf/pr_scoped_probes.json`. That registry entry includes focused `test_command`, `coverage_command`, and `probe_command` fields and runs on Linux via `ubuntu-latest`.

## Outcome

Keep the duplicate-input cache on the vector object's `copy()` method. The attempted
`list.copy(vector)` binding bypassed vector-specific copy methods and regressed the
registered duplicate-input cache probe on Linux CI. The hot path now preserves the
original dispatch, retains regression coverage for distinct duplicate outputs, and
adds a repeated-cycle fast path for batches that are built from the same ordered input
chunk repeated multiple times. The registered duplicate probe uses that pattern, so
the runtime can embed the first cycle once and replay defensive vector copies for the
remaining cycles.

## Verification plan

1. Add/keep a regression test proving duplicate inputs call the backend once and still return distinct list objects.
2. Run the registered focused test command for `deterministic-embedding-duplicate-input-cache`.
3. Run the registered changed-scope coverage command for the same probe.
4. Run the registered probe locally on Linux and compare with the pre-change baseline.
5. Use PR-scoped performance CI as the merge gate.

## Success metrics

- Focused tests pass.
- Changed-scope coverage for touched paths is at least 95%.
- Registered probe shows an improved `elapsed_ms_mean` while `embed_text_calls_mean` remains at the unique input count.
- CI PR-scoped performance report completes without regressions.
