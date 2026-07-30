# Dataset quality completion sentinel lookup

## Scope

This Python-only performance slice is limited to output-length accounting in
`worker.productization.dataset_preparation._append_rows_output_lengths()`.

The hot path computes dataset quality summary lengths for prompt/completion and
message-shaped generated rows. Completion rows currently perform a key-presence
check and then a second dictionary lookup to read the completion value.

## Registered probe

The affected path is already covered by the registered PR-scoped probe
`dataset-quality-lengths-chain` in `infra/perf/pr_scoped_probes.json`. The probe
has focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/productization/dataset_preparation.py`
- dataset preparation focused tests
- `scripts/dataset_quality_lengths_probe.py`

## Plan

1. Keep output-length behavior unchanged for string, non-string, missing, and
   message rows.
2. Replace the completion-row key-presence check plus item lookup with a single
   sentinel-backed `row.get("completion", missing)` lookup.
3. Update the focused regression tripwire so completion rows avoid
   `__contains__` instead of forbidding `get()`.
4. Run focused tests, changed-scope coverage, and the registered local probe on
   Linux before opening the PR.
5. Use GitHub Actions PR-scoped performance as the final registered probe and
   merge gate.

## Expected metrics

The registered probe should report a lower or stable `elapsed_ms_mean` for the
quality-summary output-length workload. Failed-segment partition metrics are
reported by the same probe but are not expected to change because this slice
does not alter `_partition_failed_segments()`.
