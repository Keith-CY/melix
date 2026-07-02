# Dataset Quality Completion Lookup Fast Path

## Scope

This performance slice targets the registered Python path covered by the
`dataset-quality-lengths-chain` PR-scoped probe in
`infra/perf/pr_scoped_probes.json`.

Affected code:

- `services/mlx-worker-python/worker/productization/dataset_preparation.py`
- `services/mlx-worker-python/tests/test_dataset_preparation_versioning.py`
- `scripts/dataset_quality_lengths_probe.py`

## Current Behavior

Dataset quality scoring derives output-length statistics for generated sample
rows. Most training rows in the registered probe use a top-level `completion`
field. The existing loop checks membership and then performs a second dictionary
lookup for `completion` before falling back to message aggregation.

## Proposed Slice

Use a single guarded `row["completion"]` lookup for the completion fast path and
fall back to the existing message semantics only on `KeyError`. For already-string
completion/message content values, use direct `len()` and only call `str()` for
non-string compatibility cases. This keeps the same behavior for completions,
message rows, malformed message containers, and non-mapping message items while
reducing dictionary and coercion work on the dominant completion-row path.

## Probe and Validation

The affected path is already registered as `dataset-quality-lengths-chain` with
focused `test_command`, `coverage_command`, and `probe_command` entries. This
slice will run:

1. The registered focused test command.
2. The registered changed-scope coverage command.
3. The registered local probe on Linux before and after the change.

## Acceptance

Accept only if focused tests and coverage pass and the registered probe shows a
clear elapsed-time improvement without semantic drift.
