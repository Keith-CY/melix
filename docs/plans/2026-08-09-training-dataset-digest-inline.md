# Training dataset canonical digest inline JSON encoding

## Scope

This Python-only performance slice is limited to the canonical sample digest helper used by deterministic training/validation holdout splitting in `services/mlx-worker-python/worker/model_ops/training_dataset.py`.

The behavior stays identical: canonical sample JSON still uses sorted keys and `ensure_ascii=False`, and the digest remains SHA-256 over the UTF-8 canonical payload.

## Registered probe

The affected path is already covered by the registered PR-scoped performance probe `training-dataset-validation-split-nsmallest` in `infra/perf/pr_scoped_probes.json`. The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries for the training dataset split helper and related tests.

Primary local metrics:

- `elapsed_ms_mean` lower is better.
- `peak_bytes_mean` lower is better.
- `validation_count` and `checksum` must remain unchanged.

## Implementation plan

1. Keep the public `_canonical_sample_key(...)` helper unchanged for callers that need the canonical string.
2. Inline the digest helper's JSON serialization with local default bindings for `json.dumps` and `hashlib.sha256`, avoiding the extra helper call on the validation split hot path.
3. Run the focused registered tests, changed-scope coverage, and the registered local Linux probe before pushing.
4. Use GitHub Actions PR-scoped performance as the merge gate after the PR is opened.

## Acceptance criteria

- Focused training dataset and PR-scoped performance tests pass.
- Changed-scope coverage for touched files remains at or above 95%.
- Local registered probe reports unchanged validation sample count/checksum and non-regressed lower-is-better metrics.
- Hosted PR-scoped performance probe completes successfully before merge.
