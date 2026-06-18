# Evaluation JSON Equal-Value Scoring Fast Path Performance Slice

## Scope

Optimize one Python hot path in `services/mlx-worker-python/worker/productization/evaluation_final_result.py`: `score_final_result()` now handles schema-free JSON scoring directly on the public entry path before falling back to `_score_json_result()` for schema validation.

The behavior is unchanged because the direct path calls the same cached schema-free scorer and preserves the existing invalid-extracted-JSON recovery branch. Schema-backed JSON scoring still uses `_score_json_result()` so validation behavior remains unchanged.

## Registered Probe

The affected path is covered by the registered PR-scoped probe `evaluation-final-result-json-typed-score-aggregate` in `infra/perf/pr_scoped_probes.json`.

The probe includes:

- focused tests through `test_command`
- changed-scope coverage through `coverage_command`
- local/CI performance measurement through `probe_command` (`scripts/evaluation_json_typed_score_probe.py`)

## Implementation Plan

1. Branch on `profile.output_schema` in `score_final_result()` after confirming `result_kind == "json"`.
2. Call `_cached_schema_free_json_scoring_outcome()` directly for schema-free JSON profiles.
3. Preserve the existing `json.JSONDecodeError` handling by validating the target payload before returning `parse_failed` for invalid extracted JSON.
4. Verify with focused evaluation final-result tests, changed-scope coverage, and the registered probe on Linux.

## Success Metric

`scripts/evaluation_json_typed_score_probe.py` should report lower `elapsed_ms_mean` for the synthetic repeated schema-free JSON scoring workload while preserving `score_checksum` and validation behavior.
