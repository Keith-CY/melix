# Training dataset canonical JSON encoder cache

## Scope

This Python-only performance slice is limited to canonical sample digesting in
`services/mlx-worker-python/worker/model_ops/training_dataset.py`, used by the
deterministic validation/test split helpers.

The public canonical key remains unchanged: sorted JSON keys with
`ensure_ascii=False`, encoded as UTF-8 before SHA-256 digesting.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe
`training-dataset-validation-split-nsmallest` in
`infra/perf/pr_scoped_probes.json`. That entry includes focused
`test_command`, `coverage_command`, and `probe_command` entries for this Python
path, its focused tests, and the PR-scoped performance selection test.

Primary local metrics:

- `elapsed_ms_mean` lower is better.
- `peak_bytes_mean` lower is better.
- `validation_count` and `checksum` must remain unchanged.

## Implementation plan

1. Add a module-level canonical `json.JSONEncoder(...).encode` binding for the
   existing canonical JSON options.
2. Use that encoder from `_canonical_sample_digest(...)` to avoid constructing a
   new JSON encoder for each split-ranking sample.
3. Add a regression assertion that digest bytes still match
   `_canonical_sample_key(sample).encode("utf-8")`.
4. Run the registered focused tests, changed-scope coverage, and registered
   local Linux probe before pushing.

## Acceptance criteria

- Focused training dataset and PR-scoped performance tests pass.
- Changed-scope coverage for touched files remains at or above 95%.
- Local registered probe reports unchanged validation sample count/checksum and
  non-regressed lower-is-better metrics.
- Hosted PR-scoped performance probe completes successfully before merge.
