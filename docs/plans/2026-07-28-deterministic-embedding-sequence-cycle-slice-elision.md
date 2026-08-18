# Deterministic embedding sequence cycle slice elision

## Scope

This Python performance slice is limited to repeated-cycle detection and replay in
`worker.runtime.deterministic_embedding_runtime.DeterministicEmbeddingRuntime`.
List and tuple inputs keep the existing CPython slice-comparison fast path, while
non-list `Sequence[str]` inputs validate repeated multi-input cycles by direct
index comparison so request-backed sequences do not allocate temporary cycle
slices.

## Registered Probe

The affected path is covered by the registered PR-scoped probe
`deterministic-embedding-duplicate-input-cache` in
`infra/perf/pr_scoped_probes.json`. This slice extends the existing probe with
non-list sequence cycle-detection metrics:

- `sequence_cycle_detection_elapsed_ms_mean` (informational)
- `sequence_cycle_detection_slices_mean`

The existing duplicate-input and single-cycle metrics remain in place to guard
list-backed probe behavior.

## Verification Plan

1. Add regression coverage proving repeated multi-input cycle detection can run
   on a non-list sequence without invoking slice access.
2. Run the registered focused test command locally on Linux.
3. Run the registered changed-scope coverage command locally on Linux.
4. Run the registered probe locally and compare the new non-list sequence slice
   metric against the pre-change failing regression evidence.
5. Let GitHub Actions run the registered PR-scoped performance workflow before
   merge.

## Expected Impact

For request-backed or other custom sequence inputs, the repeated-cycle detector
avoids all temporary slice allocations in the multi-input validation path, and
cycle replay embeds the first cycle by index instead of materializing a slice.
List and tuple inputs keep the prior slice comparison path to avoid regressing
the existing list-backed probe workload.

## 2026-08-18 Single-cycle iterator-count slice

This follow-up Python-only slice keeps the same registered probe and narrows the
single-input repeated-cycle replay path. The path still embeds the repeated text
once and returns independent vector copies for every duplicate input, but the
copy generator now iterates over `itertools.repeat(None, input_count - 1)` instead
of `range(input_count - 1)`. The intended effect is to avoid building and
stepping an integer range for the hot single-cycle copy loop while preserving the
low-memory generator-based `list.extend(...)` behavior.

Additional local verification for this slice:

1. Run `services/mlx-worker-python/tests/test_embedding_runtime.py` and the
   registered PR-scoped performance tests from the probe's `test_command`.
2. Run the registered `coverage_command` and confirm changed-scope coverage stays
   above 95%.
3. Run `scripts/deterministic_embedding_duplicate_probe.py` locally on Linux and
   compare the single-cycle metrics against the pre-change baseline.
